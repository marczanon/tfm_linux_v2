# API minima con FastAPI

## Objetivo

Implementar la primera version del Hito 6 de la Fase 2: exponer por HTTP la
persistencia local y el registro consultable de ejecuciones.

Esta version es deliberadamente de lectura. No lanza todavia ejecuciones nuevas
ni abre trabajos costosos desde la API. Esa decision evita mezclar la base de
servicio con politicas futuras de aprobacion, colas o control de recursos.

## Modulos implementados

```text
codigo/app/api/__init__.py
codigo/app/api/app.py
codigo/app/api/routes.py
```

La funcion principal es:

```text
create_app(runs_dir=...)
```

Esto permite crear la aplicacion contra `codigo/reports/runs/` en uso real o
contra un directorio temporal durante los tests.

## Endpoints disponibles

```text
GET /health
GET /runs
GET /runs/compare
GET /runs/{run_id}
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/report
```

### GET /health

Devuelve el estado basico de la API y el directorio de runs configurado.

### GET /runs

Lista las ejecuciones persistidas usando el indice local. Soporta filtros
exactos opcionales:

```text
dataset
current_stage
approved
```

Ejemplo:

```text
GET /runs?approved=true
```

### GET /runs/compare

Compara metricas principales entre dos o mas ejecuciones persistidas. Recibe
los identificadores como parametro repetido:

```text
GET /runs/compare?run_ids=run_a&run_ids=run_b
```

Devuelve el contrato `RunComparison`, con una fila por ejecucion y un resumen
de mejor y peor run para precision, recall, F1 y tasa de falsos positivos.

### GET /runs/{run_id}

Devuelve la metadata persistida de una ejecucion concreta.

### GET /runs/{run_id}/artifacts

Devuelve las referencias ligeras a artefactos guardadas para una ejecucion.

### GET /runs/{run_id}/report

Devuelve el informe Markdown asociado al run, si existe en disco. Si el run no
tiene informe o la ruta ya no existe, responde con `404`.

## Ejecucion local

Comando recomendado desde la raiz del repositorio:

```text
conda run -n tfm_v2 python -m uvicorn codigo.app.api:app --host 127.0.0.1 --port 8010
```

Comprobacion:

```text
curl -sS http://127.0.0.1:8010/health
```

## Decisiones de diseno

- La API no recalcula metricas ni vuelve a ejecutar el pipeline.
- Los endpoints leen desde `run_registry.py` y `run_persistence.py`.
- Las respuestas principales reutilizan contratos Pydantic existentes:
  `RunIndexEntry`, `RunSnapshot` y `RunComparison`.
- Los handlers se definen como `async def` para evitar bloqueos del threadpool
  en los tests locales.
- Los tests usan `httpx.AsyncClient` con `ASGITransport`, lo que permite probar
  la API sin abrir sockets reales.

## Validacion

Tests focalizados:

```text
conda run -n tfm_v2 python -m unittest codigo.tests.test_api_runs
```

Resultado:

```text
Ran 6 tests in 0.049s
OK
```

Suite completa:

```text
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 110 tests in 0.350s
OK
```

## Siguientes ampliaciones posibles

El endpoint `POST /runs` queda para una fase posterior, cuando se definan las
politicas de ejecucion, aprobacion humana y control de coste.
