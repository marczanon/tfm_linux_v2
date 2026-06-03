# Fase 8 - Memoria RAG avanzada M3: modeler inicial y gobierno transversal

Fecha: 2026-06-03.

## Objetivo

El hito M3 inicia el uso de memoria antes de la decision principal del
`modeler`, no solo durante reintentos o post-mortems. El cambio se plantea como
transversal: la memoria no pertenece al modelador, sino al sistema multiagente.
Cada agente conserva su coleccion propia y puede recibir contexto RAG bajo los
mismos guardarrailes de trazabilidad.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Permitir memoria inicial para agentes y gobernar recuerdos desde API/frontend,
sin duplicar el backend RAG ni crear un pipeline paralelo.
```

Inventario revisado:

- `codigo/app/services/vector_memory.py`;
- `codigo/app/services/memory_registry.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/agents/modeler.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/app/api/routes.py`;
- `codigo/frontend/src/App.tsx`;
- `codigo/tests/test_vector_memory_store.py`;
- `codigo/tests/test_api_memory.py`;
- `codigo/tests/test_modeler_agent.py`;
- `codigo/tests/test_graph_pipeline.py`.

Decision:

```text
extend
```

Motivo: ya existian contratos de memoria, colecciones por agente, backend JSON
vectorial local, endpoints de consulta, cockpit frontend y observabilidad de
retrieval. La mejora amplia esas piezas en lugar de crear un segundo sistema de
memoria.

## Cambios implementados

### Memoria inicial del modeler

`ModelingDecision` declara ahora los mismos campos de uso de memoria que ya
existian en decisiones temporales de otros agentes:

- `memory_context_id`;
- `used_memory_context`;
- `memory_record_ids`;
- `memory_usage_summary`;
- `memory_record_uses`.

`modeler.py` incorpora `build_modeler_memory_query` y
`retrieve_modeler_memory_context`. La consulta incluye dataset, objetivo,
perfil de supervision, fuente de etiquetas, resumen de features y preguntas
especificas sobre familia de modelo, politica temporal, umbral, falsos avisos,
lead time y F1 auxiliar.

Cuando Qwen recibe memoria, el prompt le muestra:

- recuerdos recuperados;
- similitud, rol, veredicto, metricas, tags y fuente;
- guia derivada de warnings/casos frontera;
- reglas para citar solo recuerdos realmente recuperados.

La validacion rechaza decisiones que inventen IDs de memoria, que declaren uso
sin `memory_usage_summary` o que citen un `warning`/`boundary_case` sin explicar
mitigacion del riesgo.

### Integracion en el grafo

El nodo de modelado recupera memoria antes de llamar al agente. Si hay store de
memoria activo, se persisten:

- `modeler_memory_query`;
- `modeler_retrieved_memory_context`.

Ademas se emiten eventos runtime:

- `retrieval_requested`;
- `retrieval_returned`;
- `retrieval_used`;
- `retrieval_rejected_by_agent`.

Esto permite distinguir dos situaciones diferentes: memoria no disponible y
memoria disponible pero no usada por el agente. Esa segunda situacion es
importante para investigacion, porque Qwen mantiene poder de eleccion: puede
usar, adaptar, contradecir o ignorar memoria dentro del contrato.

### Gobierno manual de memoria

La memoria persistida deja de ser solo consultable. Se anaden acciones de
curacion:

- excluir un recuerdo del RAG sin borrarlo;
- restaurarlo si vuelve a considerarse util;
- borrarlo del indice local.

La exclusion marca:

- `reusable_as_context=false`;
- `exclude_from_context=true`;
- tags de curacion manual.

El borrado se expone en el protocolo del store y en API. El frontend incorpora
controles en el detalle del recuerdo para excluir/restaurar/borrar desde el
cockpit.

## Importancia metodologica

Este hito responde a dos requisitos del TFM:

1. La memoria debe ser multiagente. `modeler_memory` es solo la primera
   aplicacion fuerte; el mismo patron sirve para `cleaner_memory`,
   `structurer_memory`, `evaluator_memory`, `report_writer_memory`,
   `researcher_memory` y `shared_methodology_memory`.
2. Los LLM Qwen siguen siendo protagonistas. La memoria no convierte la run en
   una regla determinista; alimenta el contexto del agente y obliga a declarar
   como se ha usado.

## Benchmarks y limpieza de memoria

La curacion manual prepara el siguiente paso: benchmarks con control de memoria.
Antes de una bateria se podran excluir recuerdos contaminados, no revisados o
demasiado especificos. Tras la bateria, el sistema podra comparar:

- run sin memoria;
- run con memoria completa;
- run con memoria filtrada;
- run con memoria consolidada.

La limpieza automatica queda pendiente para un hito posterior. Debe basarse en
politicas explicitas, por ejemplo:

- excluir recuerdos con bajo rendimiento repetido;
- excluir recuerdos no revisados en benchmarks canonicos;
- caducar recuerdos asociados a modelos o perfiles obsoletos;
- promover a memoria compartida solo lecciones consolidadas.

## Verificacion

Tests anadidos o ampliados:

- borrado en `LocalJsonVectorMemoryStore`;
- API `PATCH /memory/records/{id}/curation`;
- API `DELETE /memory/records/{id}`;
- consulta inicial del `modeler`;
- decision LLM inicial con memoria citada y mitigacion;
- pipeline con artefactos `modeler_memory_query` y
  `modeler_retrieved_memory_context`.

## Siguiente paso

El siguiente paso logico es M4/M4-pre: definir una evaluacion canonica de
retrieval antes de cambiar el backend vectorial. Debe medir si la memoria
recuperada es relevante, si Qwen la usa correctamente, si ignora recuerdos
conflictivos y si el resultado mejora las metricas temporales del perfil
`run_to_failure_degradation`.
