# Protocolo de reutilizacion y anti-duplicacion

Fecha: 2026-05-29.

## Objetivo

Evitar que la Fase 4 crezca con piezas paralelas que hacen lo mismo. A partir de
este punto, cualquier cambio tecnico debe empezar por una busqueda de capacidades
existentes y una decision explicita de reutilizacion, adaptacion, extension o
creacion.

Este protocolo no anade codigo de aplicacion. Es una puerta metodologica para
trabajar con mas disciplina antes de tocar la API, el grafo, los agentes o los
ejecutores.

## Checklist previa obligatoria

Antes de implementar:

1. Describir la capacidad buscada en una frase.
2. Buscar si ya existe algo equivalente en:
   - `codigo/app/schemas/`;
   - `codigo/app/services/`;
   - `codigo/app/executors/`;
   - `codigo/app/agents/`;
   - `codigo/app/graph/`;
   - `codigo/app/api/`;
   - `codigo/scripts/`;
   - `codigo/tests/`;
   - `codigo/docs/`.
3. Revisar si el nombre existente es historico pero la responsabilidad ya es
   generalizable.
4. Elegir una decision:
   - `reuse`: usar la pieza existente sin cambios;
   - `adapt`: ajustar una pieza existente sin cambiar su contrato publico;
   - `extend`: ampliar contrato o servicio manteniendo compatibilidad;
   - `new`: crear una pieza nueva porque no hay propietario claro.
5. Si la decision es `new`, documentar:
   - por que lo existente no sirve;
   - que responsabilidad tendra la nueva pieza;
   - que no debe hacer para no solaparse con otras capas.

## Comandos de busqueda recomendados

Plantilla general:

```text
rg -n "concepto|sinonimo|nombre_probable" codigo/app codigo/scripts codigo/tests codigo/docs
rg --files codigo/app codigo/scripts codigo/tests codigo/docs | sort
```

Para cambios de API:

```text
rg -n "ApiRun|PipelineRun|run_dataset|plan_dataset|human_review|RunSnapshot" codigo/app codigo/tests codigo/docs
```

Para cambios multi-dataset:

```text
rg -n "dataset_id|adapter_id|DatasetPipelinePlan|DatasetRunPolicy|nasa_ims|cwru" codigo/app codigo/tests codigo/docs
```

Para cambios de memoria agentica:

```text
rg -n "Memory|memory|RetrievedMemory|ReasoningMemory|VectorMemory|agent_memory" codigo/app codigo/tests codigo/docs
```

Para cambios de ejecutores:

```text
rg -n "generate_|Executor|Result|Config|artifact" codigo/app/executors codigo/app/schemas codigo/tests
```

## Mapa canonico actual

| Responsabilidad | Pieza canonica | Notas |
| --- | --- | --- |
| Planificar/ejecutar pipelines multi-dataset | `codigo/app/services/pipeline_runner.py` | Usar antes de crear scripts o endpoints por dataset. |
| Contrato comun de ejecucion | `codigo/app/schemas/pipeline_run.py` | Base para CLI, API y futura UI. |
| Contrato de `POST /runs` | `codigo/app/schemas/api_runs.py` | Extiende `PipelineRunRequest`; no duplicar campos multi-dataset. |
| API de runs | `codigo/app/api/routes.py` | Debe delegar en servicios; no ejecutar logica pesada en la ruta. |
| Jobs API locales | `codigo/app/services/api_run_jobs.py` | Estado en memoria para ejecuciones `background=true`; no sustituye snapshots. |
| Persistencia de snapshots | `codigo/app/services/run_persistence.py` | Fuente de verdad para snapshots locales. |
| Consulta/comparacion de runs | `codigo/app/services/run_registry.py` | Reutilizar para endpoints de lectura y comparaciones. |
| Adaptadores de dataset | `codigo/app/services/dataset_adapters.py` | Resolver `dataset_id`, `adapter_id` y descriptor. |
| Lectura de senales/tablas | `codigo/app/services/signal_adapters.py` | Frontera de formatos `.mat`, CSV, TXT, NPZ y tablas IMS. |
| Politica temporal NASA IMS | `codigo/app/services/nasa_ims_temporal_policy.py` | No inferir etiquetas proxy en otros modulos. |
| Revision humana ligera | `codigo/app/services/human_review.py` | Reutiliza `HumanReviewSettings` y `HumanApproval`. |
| Memoria vectorial | `codigo/app/services/vector_memory.py` | Backend local y proveedores de embeddings. |
| Memoria para prompts de agentes | `codigo/app/services/agent_memory.py` | Serializacion, declaracion y validacion de uso. |
| Episodios/candidatos de memoria | `codigo/app/services/decision_memory.py` | Destilacion de decisiones en memoria reutilizable. |
| Auditorias de razonamiento/memoria | `reasoning_audit.py`, `memory_usage_audit.py`, `transversal_memory_audit.py` | No mezclar con evaluacion de metricas. |
| Grafo LangGraph | `codigo/app/graph/pipeline.py` | Orquestacion; los ejecutores siguen siendo deterministas. |
| Estado inicial y validacion | `codigo/app/graph/state.py`, `codigo/app/schemas/state.py` | No cargar datos pesados en estado. |

## Criterios para crear una pieza nueva

Crear algo nuevo solo esta justificado si:

- no existe propietario claro de la responsabilidad;
- reutilizar una pieza actual mezclaria capas que deben seguir separadas;
- el contrato existente quedaria mas confuso o menos seguro al extenderlo;
- la nueva pieza se puede nombrar con una responsabilidad unica y verificable;
- incluye tests o documentacion proporcional al riesgo.

No esta justificado crear algo nuevo si:

- solo cambia el dataset y ya existe `PipelineRunRequest` o adaptador;
- solo cambia el punto de entrada y ya existe un servicio reutilizable;
- solo cambia el modo de ejecucion y se puede expresar con politica o config;
- el nombre historico contiene `cwru`, pero la funcion puede generalizarse sin
  romper compatibilidad;
- ya existe un contrato Pydantic que representa el mismo concepto.

## Plantilla para registrar la decision

En la documentacion del hito o en el resumen final de la tarea debe quedar algo
equivalente a:

```text
Inventario previo:
- Busquedas realizadas: ...
- Piezas encontradas: ...
- Decision: reuse | adapt | extend | new
- Motivo: ...
- Impacto en compatibilidad: ...
```

Esta plantilla no tiene que convertirse en burocracia pesada. Su objetivo es
hacer visible que se miro antes de escribir.

## Aplicacion inmediata

Para los proximos pasos de API:

- antes de ampliar jobs API, revisar `api_run_jobs.py`, `run_persistence.py`,
  `run_registry.py` y `pipeline_runner.py`;
- antes de exponer LLM o memoria por API, revisar `PipelineMemoryConfig`,
  `agent_memory.py`, `vector_memory.py` y `human_review.py`;
- antes de crear scripts por dataset, comprobar si
  `run_dataset_pipeline_with_memory.py` puede parametrizarse o envolver la
  ejecucion;
- antes de introducir nuevos contratos, comprobar si `pipeline_run.py`,
  `api_runs.py`, `reasoning.py` o `state.py` ya expresan el concepto.
