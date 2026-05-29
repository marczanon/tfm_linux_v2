# Catalogo de datasets Fase 5

Fecha: 2026-05-29.

## Objetivo

Exponer desde FastAPI un catalogo controlado de adaptadores y un descriptor de
datasets por ruta permitida, para que el frontend deje de depender de una lista
local de datasets soportados.

## Inventario previo

Busquedas realizadas:

```text
rg -n "FastAPI|include_router|allowed_raw_roots|runs_dir|CORSMiddleware|app.state" codigo/app codigo/tests
rg -n "POST /runs|create_run|TestClient|httpx|AsyncClient|/health|/runs|allowed_raw_roots|run_job_store" codigo/tests codigo/app
rg -n "dataset_id|adapter_id|DatasetPipelinePlan|DatasetRunPolicy|nasa_ims|cwru" codigo/app codigo/tests codigo/docs
```

Piezas encontradas:

- `dataset_adapters.py`: propietario canonico de `list_dataset_adapters()` y
  `describe_dataset()`.
- `pipeline_runner.py`: propietario canonico del preflight mediante
  `plan_dataset_pipeline_run()`.
- `api_runs.py`: contrato de ejecucion controlada con `dry_run=true` por
  defecto.
- `routes.py`: punto canonico de FastAPI para rutas de runs y jobs.
- `create_app(...)`: configuracion de `runs_dir`, `allowed_raw_roots` y jobs
  locales.

Decision: `extend`.

Motivo: ya existian adaptadores, descriptor, politica de dataset y preflight de
run. La Fase 5 solo necesitaba exponerlos por API y consumirlos desde la UI,
sin crear otro catalogo ni otro runner.

Impacto en compatibilidad: `POST /runs` sigue siendo la entrada canonica de
preflight y ejecucion. Se anaden endpoints de lectura/descripcion y un guardarrail
mas estricto para rutas no soportadas por el adaptador explicito.

## Implementacion backend

Se ha creado `codigo/app/schemas/api_datasets.py` con:

- `DatasetDescribeRequest`;
- `DatasetDescribeResponse`.

Se han anadido endpoints:

```text
GET /datasets/adapters
POST /datasets/describe
```

`GET /datasets/adapters` devuelve los adaptadores registrados por
`list_dataset_adapters()`.

`POST /datasets/describe`:

- valida que `raw_path` este bajo `allowed_raw_roots`;
- infiere o valida el adaptador con `dataset_adapters.py`;
- rechaza rutas que el adaptador explicito no soporta;
- devuelve `DatasetAdapterInfo`, `DatasetDescriptor`, raices permitidas y
  `uploads_dir`;
- no genera manifiestos ni transforma datos.

La aplicacion FastAPI crea un directorio de staging local bajo:

```text
codigo/data/raw/uploads/
```

Cuando `create_app(...)` se instancia con raices temporales en tests, el staging
se deriva de la primera raiz permitida.

Tambien se ha endurecido `plan_dataset_pipeline_run(...)` para rechazar un
adaptador explicito cuando su `supports(raw_path)` no reconoce la ruta.

## Implementacion frontend

El frontend ahora consume:

```text
GET /datasets/adapters
POST /datasets/describe
GET /health
GET /runs
POST /runs con dry_run=true
```

Cambios principales:

- el selector visible de datasets se construye desde el catalogo backend;
- los defaults locales quedan solo como ayuda de ruta/modo por `dataset_id`;
- antes del dry-run se solicita descriptor controlado con
  `POST /datasets/describe`;
- la vista de plan muestra descriptor, formato, tarea, canales, fases efectivas,
  politica, bloqueos y rutas canonicas.

## Verificacion

Comandos ejecutados:

```text
python -m unittest codigo.tests.test_api_runs codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
npm run build
```

Resultado:

- 42 tests backend correctos;
- build TypeScript/Vite correcto;
- el catalogo devuelve `cwru_bearing`, `nasa_ims_bearing` y
  `generic_tabular_signal`;
- una ruta fuera de raiz permitida se rechaza con `403`;
- un adaptador explicito incompatible con la ruta se rechaza con `400`;
- el frontend compila consumiendo los nuevos tipos.

## Limitaciones

- No se ha anadido subida multipart porque `python-multipart` no forma parte
  todavia del entorno fijado.
- La ingesta inicial queda como ruta local permitida y staging preparado bajo
  `uploads/`.
- `POST /runs` continua siendo el preflight canonico de capacidades antes de
  ejecutar.

## Siguiente paso

Avanzar al Hito 3: lanzar runs reales desde la aplicacion usando
`POST /runs` con `dry_run=false` y `background=true`, seguido de polling sobre
`GET /run-jobs/{job_id}`.
