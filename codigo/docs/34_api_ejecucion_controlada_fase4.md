# API controlada de ejecucion - Fase 4

Fecha: 2026-05-29.

## Objetivo

Abrir el primer `POST /runs` sin perder los guardarrailes definidos para la
arquitectura multi-dataset. Esta version esta pensada como base para una futura
interfaz grafica: primero muestra un plan auditable y solo ejecuta si la
peticion lo declara explicitamente.

## Endpoints

La API conserva los endpoints de lectura existentes:

```text
GET /health
GET /runs
GET /runs/compare
GET /runs/{run_id}
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/report
GET /run-jobs/{job_id}
```

Y anade:

```text
POST /runs
```

## Contrato de solicitud

El endpoint reutiliza el contrato multi-dataset:

```text
ApiRunRequest extends PipelineRunRequest
```

Campos principales:

```text
run_id
dataset_id
raw_path
adapter_id
dataset_policy_id
execution_mode
requested_stages
use_memory
use_llm
allow_synthetic_labels
dry_run
background
human_review
human_approval
```

Regla clave:

```text
dry_run = true por defecto
```

Con `dry_run=true`, el endpoint solo planifica. Con `dry_run=false`, intenta
ejecutar despues de validar rutas, politica de dataset, coste inicial y
duplicidad de `run_id`.

Con `background=true` y `dry_run=false`, la API acepta la ejecucion como job
local en memoria y responde `202`. La ejecucion queda delegada al mismo
`run_dataset_pipeline(...)`, por lo que no existe un segundo runner paralelo.

## Respuesta

La respuesta devuelve siempre el plan:

```text
ApiRunResponse
  - dry_run
  - executed
  - plan
  - snapshot
  - final_stage
  - approved
  - report_path
  - metrics
  - errors
  - human_approval
  - human_review_reasons
  - job
```

Esto permite a una futura UI mostrar el descriptor, las capacidades, los
bloqueos y las rutas previstas antes de lanzar una ejecucion real.

## Guardarrailes implementados

- `raw_path` debe estar dentro de una raiz permitida por la aplicacion.
- Por defecto, `create_app(...)` solo permite `codigo/data/raw`.
- En tests puede pasarse `allowed_raw_roots=[...]`.
- Si `dataset_id` y `adapter_id` no coinciden, la planificacion falla.
- Si la politica de dataset bloquea fases solicitadas, la ejecucion real
  responde `409`.
- `dry_run=true` puede devolver planes bloqueados sin ejecutar.
- `use_llm=true` no se permite todavia en ejecucion API.
- `use_memory=true` o `requested_stages` con `memory` no se permite todavia en
  ejecucion API.
- Si ya existe `run_id` en el directorio de runs, la API responde `409` para no
  sobrescribir snapshots.
- Si ya existe un job en memoria para el mismo `run_id`, la API responde `409`.

## Jobs locales iniciales

El modo en segundo plano es deliberadamente minimo. No introduce Celery, Redis ni
una cola persistida. Usa:

```text
codigo/app/services/api_run_jobs.py
```

El servicio `ApiRunJobStore` mantiene estados en memoria del proceso:

```text
queued
running
completed
failed
```

La fuente de verdad final sigue siendo el snapshot persistido por
`run_persistence.py`. Si el proceso se reinicia, los jobs en memoria se pierden,
pero las runs completadas siguen disponibles mediante `GET /runs/{run_id}`.

`GET /run-jobs/{job_id}` permite consultar el estado de una ejecucion aceptada
con `background=true`.

## Human Review inicial

La API no introduce un contrato paralelo de revision humana. Reutiliza:

```text
HumanReviewSettings
HumanApproval
```

y centraliza la logica en:

```text
codigo/app/services/human_review.py
```

Modos soportados:

```text
off
passive
required
```

Semantica:

- `off`: no se genera puerta de revision humana.
- `passive`: se devuelve `human_approval` y `human_review_reasons`, pero no
  bloquea la ejecucion.
- `required`: si hay razones de revision y no llega `human_approval.approved=true`,
  la ejecucion responde `409`.
- si `required` llega aprobado, el `HumanApproval` se pasa al estado inicial y
  queda persistido en el snapshot.

Las razones de revision pueden venir de `required_decision_points` declarados
en `HumanReviewSettings` o de capacidades de dataset que marquen
`requires_human_review=true`.

## Ejemplo de preflight

```text
POST /runs
{
  "run_id": "plan-nasa-v1",
  "dataset_id": "nasa_ims_bearing",
  "adapter_id": "nasa_ims_bearing",
  "raw_path": "codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen",
  "dataset_policy_id": "nasa_ims_temporal_v1"
}
```

Resultado esperado:

```text
executed = false
dry_run = true
plan.can_execute_requested_stages = true
```

## Ejemplo de ejecucion

```text
POST /runs
{
  "run_id": "api-nasa-temporal-v1",
  "dataset_id": "nasa_ims_bearing",
  "adapter_id": "nasa_ims_bearing",
  "raw_path": "codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen",
  "dataset_policy_id": "nasa_ims_temporal_v1",
  "dry_run": false
}
```

Resultado esperado si la politica permite la ejecucion:

```text
executed = true
snapshot.run_id = "api-nasa-temporal-v1"
final_stage = "completed" | "failed"
approved = true | false | null
```

Una run con metricas bajas puede terminar como `completed` y
`approved=false`, generando informe igualmente. Esto no se considera fallo de
API ni de infraestructura.

## Ejemplo de ejecucion en segundo plano

```text
POST /runs
{
  "run_id": "api-cwru-background-v1",
  "dataset_id": "cwru_bearing",
  "adapter_id": "cwru_bearing",
  "raw_path": "codigo/data/raw/cwru_bearing/mat",
  "dry_run": false,
  "background": true
}
```

Respuesta esperada:

```text
status_code = 202
executed = false
job.status = "queued" | "running" | "completed" | "failed"
```

Consulta posterior:

```text
GET /run-jobs/api-cwru-background-v1
```

## Implementacion

```text
codigo/app/schemas/api_runs.py
codigo/app/services/api_run_jobs.py
codigo/app/services/human_review.py
codigo/app/api/app.py
codigo/app/api/routes.py
codigo/tests/test_api_runs.py
```

## Validacion

Tests focalizados:

```text
python -m unittest codigo.tests.test_api_runs
```

Cobertura nueva:

- `POST /runs` con `dry_run=true` devuelve plan sin ejecutar;
- `raw_path` fuera de raices permitidas responde `403`;
- ejecucion bloqueada por politica de dataset responde `409`;
- ejecucion permitida persiste snapshot y devuelve estado compacto.
- Human Review `passive` devuelve razones sin bloquear;
- Human Review `required` bloquea sin aprobacion y ejecuta con aprobacion.
- `background=true` devuelve `202`, crea un job observable y persiste snapshot al
  completar;
- errores en background quedan registrados como job `failed`.

Validacion completa:

```text
python -m unittest discover codigo/tests
```

Resultado actual: `241` tests correctos.

## Fuera de alcance de esta version

- ejecucion con LLM desde API;
- ejecucion con memoria RAG desde API;
- cola persistida, workers externos o cancelacion de trabajos;
- autenticacion/autorizacion;
- gestion completa de usuarios, colas o notificaciones para revision humana;
- seleccion de modelos desde una interfaz grafica.
