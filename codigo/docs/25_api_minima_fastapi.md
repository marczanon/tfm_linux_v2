# API minima con FastAPI

## Objetivo

Implementar la primera version del Hito 6 de la Fase 2: exponer por HTTP la
persistencia local y el registro consultable de ejecuciones.

La version original de Fase 2 era deliberadamente de lectura. En Fase 4 se ha
anadido una primera ejecucion controlada mediante `POST /runs`, manteniendo
`dry_run=true` por defecto y guardarrailes de ruta, politica de dataset y coste
inicial. El detalle de esta ampliacion queda en:

```text
codigo/docs/34_api_ejecucion_controlada_fase4.md
```

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
GET /run-jobs/{job_id}
POST /runs
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

### POST /runs

Planifica o ejecuta una run local usando `ApiRunRequest`.

Por defecto:

```text
dry_run = true
```

En ese modo devuelve un `DatasetPipelinePlan` sin ejecutar. Para ejecutar hay
que enviar `dry_run=false`; la API valida que `raw_path` este dentro de raices
permitidas, que la politica de dataset permita las fases solicitadas y que
`run_id` no exista ya. En esta primera version no se permite ejecutar desde API
con `use_llm=true` ni con memoria RAG activada.

La solicitud tambien acepta `human_review` con los modos `off`, `passive` y
`required`, reutilizando `HumanReviewSettings`. En modo `required`, si hay un
punto de decision que requiere revision y no llega `human_approval.approved=true`,
la ejecucion responde `409`.

Si se envia `background=true` junto con `dry_run=false`, la API acepta la
ejecucion como job local y responde `202`. El job se consulta mediante:

```text
GET /run-jobs/{job_id}
```

Esta primera version usa un registro en memoria del proceso, definido en
`api_run_jobs.py`. La persistencia duradera sigue siendo el snapshot local de la
run cuando la ejecucion termina.

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

- Los endpoints GET no recalculan metricas ni vuelven a ejecutar el pipeline.
- `POST /runs` planifica siempre antes de ejecutar.
- La ejecucion desde API es explicita (`dry_run=false`) y conserva los mismos
  snapshots locales que una ejecucion por script.
- La ejecucion en segundo plano no crea otro runner; envuelve
  `run_dataset_pipeline(...)`.
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

Resultado historico:

```text
Ran 6 tests in 0.049s
OK
```

Suite completa:

```text
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado historico:

```text
Ran 127 tests in 0.335s
OK
```

## Siguientes ampliaciones posibles

`POST /runs` ya existe como version controlada inicial. Quedan para fases
posteriores la ejecucion con LLM, memoria RAG, cola persistida, cancelacion de
trabajos, autenticacion y una interfaz de aprobaciones humanas mas completa.
