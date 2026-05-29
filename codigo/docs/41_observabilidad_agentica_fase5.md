# Observabilidad agentica Fase 5

Fecha: 2026-05-29.

## Objetivo

Hacer visible durante una ejecucion que agentes intervienen, que decisiones
estructuradas toman, que memoria recuperan, que ejecutores responden y como
progresa el supervisor, sin exponer datos pesados ni inventar razonamiento no
observable.

## Inventario previo

Busquedas realizadas:

```text
rg -n "agent_memory|vector_memory|reasoning_memory|decision_memory|memory|trace|event|messages|LangGraph|supervisor|agent" codigo/app codigo/tests codigo/docs
rg -n "ApiRunJobStatus|PipelineMemoryConfig|run_dataset_pipeline|run_cwru_pipeline|PipelineAgents" codigo/app codigo/tests
```

Piezas encontradas:

- `PipelineAgents`: propietario de las funciones agenticas del grafo.
- `pipeline.py`: propietario de la orquestacion LangGraph y de los mensajes.
- `ApiRunJobStore`: propietario del estado vivo de jobs `background=true`.
- `agent_decisions.py`: contratos de decisiones con `rationale`, confianza,
  alternativas, memoria citada y configuraciones.
- `agent_memory.py`, `vector_memory.py` y contratos de `reasoning.py`:
  propietarios de memoria RAG y uso declarado de recuerdos.

Decision: `new` para el contrato de eventos runtime; `extend` para grafo,
runner, jobs API y frontend.

Motivo: no existia una pieza responsable de telemetria viva durante la
ejecucion. La nueva pieza solo observa y resume eventos; no decide, no modifica
datos y no sustituye snapshots, mensajes ni memoria.

Impacto en compatibilidad: los parametros nuevos son opcionales y
`ApiRunJobStatus` anade `events` con lista vacia por defecto.

## Implementacion backend

Se anaden:

- `AgentRuntimeEvent` en `codigo/app/schemas/agent_runtime.py`;
- `AgentRuntimeRecorder` en `codigo/app/services/agent_runtime.py`;
- campo `events` en `ApiRunJobStatus`;
- `GET /run-jobs/{job_id}/events` con filtro `after_sequence`;
- parametro opcional `runtime_recorder` en `run_dataset_pipeline(...)` y en la
  ejecucion del grafo.

El grafo emite eventos de:

- `supervisor_decision`: decision del supervisor, siguiente fase y siguiente
  nodo;
- `agent_decision`: decision JSON del agente, `rationale`, confianza,
  configuracion propuesta y memoria citada si existe;
- `memory_retrieval`: contexto RAG recuperado o ausencia de contexto;
- `executor_result`: respuesta del ejecutor determinista, estado, artefactos y
  actualizaciones de estado;
- `job_status` y `error`: ciclo de vida del job API.

La telemetria es best-effort: un fallo al emitir eventos no debe romper la
ejecucion del pipeline.

## Implementacion frontend

La aplicacion incorpora una pestaña `Agentes`.

La vista muestra:

- jerarquia visual con supervisor y agentes especializados;
- contador de eventos por agente;
- estado del job y ultimo evento recibido;
- timeline de comunicacion entre job, supervisor, agentes, memoria y
  ejecutores;
- detalle clicable por agente con `decision_id`, confianza, fase, siguiente
  nodo, `rationale`, memoria citada y payload JSON.

Esta primera version usa el polling existente de `GET /run-jobs/{job_id}`. El
endpoint dedicado de eventos queda disponible para optimizaciones posteriores.

## Limites metodologicos

La vista no muestra cadena de pensamiento privada del LLM. Muestra razonamiento
observable y auditable: decisiones estructuradas, justificacion declarada,
memoria recuperada, uso declarado de recuerdos, configuraciones propuestas y
respuestas de ejecutores.

## Verificacion

Comandos ejecutados:

```text
python -m py_compile codigo/app/schemas/agent_runtime.py codigo/app/services/agent_runtime.py codigo/app/services/api_run_jobs.py codigo/app/graph/pipeline.py codigo/app/services/pipeline_runner.py codigo/app/api/routes.py
python -m unittest codigo.tests.test_graph_pipeline codigo.tests.test_api_runs
python -m unittest codigo.tests.test_api_runs codigo.tests.test_graph_pipeline codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
npm run build
pdflatex -interaction=nonstopmode main.tex
```

Resultado:

- los modulos backend modificados compilan correctamente;
- las pruebas de grafo y API cubren eventos runtime en grafo y jobs;
- la suite focal de API, grafo, adaptadores y runner completa 47 tests
  correctamente;
- el frontend compila correctamente con la nueva pestaña `Agentes`.
- la memoria LaTeX compila correctamente.

## Siguiente paso

Conectar la vista de agentes con memoria indexada persistida: resumen de
colecciones, consulta por agente/dataset y apertura de registros
`memory_record_id`.
