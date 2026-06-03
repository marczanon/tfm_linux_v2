# Fase 8 - Memoria M2: observabilidad de retrieval

Fecha: 2026-06-03.

## Objetivo

Implementar el segundo hito de la hoja de ruta de memoria RAG avanzada:
hacer auditable cada recuperacion de memoria usada por los agentes, sin cambiar
todavia el backend `LocalJsonVectorMemoryStore`.

## Inventario previo

Capacidad buscada:

```text
Persistir y mostrar consultas RAG concretas, contextos recuperados, backend,
modelo de embeddings, scores, recuerdos citados y recuerdos ignorados.
```

Busquedas realizadas:

```text
rg -n "AgentMemoryQuery|RetrievedMemoryContext|retrieve_memory|memory_context|memory_record_ids|memory_retrieval|runtime.*memory|AgentRuntimeEvent|memory_query" codigo/app codigo/tests codigo/docs/78_fase8_hoja_ruta_memoria_rag_avanzada.md
rg -n "retrieve_modeler_retry|modeler_retry|memory_context" codigo/app/graph codigo/app/services codigo/scripts
rg -n "memory/collections|memory/records|MemoryCollection|MemoryRecord|memoryRecords|selectedMemory|memoria" codigo/frontend/src/App.tsx codigo/frontend/src/types.ts codigo/frontend/src/styles.css
```

Piezas encontradas:

- `AgentMemoryQuery` y `RetrievedMemoryContext` ya son contratos canonicos.
- `LocalJsonVectorMemoryStore.query(...)` ya devuelve contexto con backend,
  embedding model, items, ranks y similitudes.
- `pipeline.py` ya escribia `retrieved_memory_context.json` para
  `structurer` y `evaluator`.
- `pipeline.py` ya emitia eventos `memory_retrieval`.
- `AgentMemoryPanel` ya habia sido convertido en cockpit en M1.

Decision:

```text
extend
```

Motivo: la responsabilidad ya existia en grafo, contratos y cockpit frontend.
M2 no necesita crear una API nueva; necesita hacer mas rica la traza generada y
visible.

## Cambios implementados

### Artefactos RAG separados

El grafo escribe ahora dos artefactos por recuperacion de memoria:

- `{agent}_memory_query`;
- `{agent}_retrieved_memory_context`.

En disco:

```text
agent_memory/<agent>/memory_query.json
agent_memory/<agent>/retrieved_memory_context.json
```

`memory_query.json` conserva:

- `query_id`;
- `target_agent`;
- `query_text`;
- `dataset`;
- `run_id`;
- `decision_id`;
- `decision_context`;
- roles permitidos;
- veredictos excluidos;
- `top_k`;
- `min_similarity`;
- modo de revision humana.

`retrieved_memory_context.json` conserva el contexto completo ya existente:

- `context_id`;
- query embebida;
- items recuperados;
- rank;
- similitud;
- uso previsto;
- record completo;
- backend;
- modelo de embeddings;
- fecha de generacion.

### Eventos runtime enriquecidos

Cada recuperacion genera eventos observables con `payload.retrieval_event`:

- `retrieval_unavailable`: memoria desactivada o sin store;
- `retrieval_requested`: consulta RAG construida;
- `retrieval_returned`: contexto recuperado con items, scores, backend y
  embedding;
- `retrieval_used`: el agente cito recuerdos recuperados en su decision;
- `retrieval_rejected_by_agent`: el agente recibio recuerdos pero no declaro
  uso.

Se mantiene `kind="memory_retrieval"` para no romper contratos frontend/API.

### Metadatos visibles

Los eventos `retrieval_returned` incluyen por item:

- rank;
- similitud;
- `retrieval_use`;
- `memory_record_id`;
- coleccion;
- agente objetivo;
- `source_type`;
- dataset;
- `source_path`;
- modelo/dimension de embedding del recuerdo;
- `vector_id`;
- rol;
- veredicto humano;
- outcome;
- run historica;
- summary;
- tags.

Los eventos de uso conservan:

- recuerdos recuperados;
- recuerdos citados;
- recuerdos ignorados;
- `memory_usage_summary`;
- `memory_record_uses`.

### Cockpit frontend

El cockpit de memoria muestra ahora, en el bloque `Runtime`:

- tipo de evento de retrieval;
- hora y contexto;
- backend;
- modelo de embedding;
- `top_k`;
- `min_similarity`;
- dataset;
- extracto de la query;
- items recuperados con rank, similitud, rol, origen y dataset;
- chips de recuerdos usados e ignorados.

Esto permite reconstruir una decision con memoria desde la UI sin abrir
manualmente los JSON.

## Limites conscientes

Este hito no implementa todavia:

- evaluacion de calidad de retrieval;
- reranking;
- hybrid search;
- benchmark canonico de memoria;
- Qdrant;
- recuperacion inicial del `modeler`;
- persistencia equivalente en scripts historicos de reintento fuera del grafo.

La observabilidad se centra en la app/grafo principal y en los agentes que ya
recuperan memoria dentro de ese flujo: `structurer` y `evaluator`.

## Validacion

Validaciones ejecutadas:

```text
python -m py_compile codigo/app/graph/pipeline.py
python -m unittest codigo.tests.test_graph_pipeline
npm run build
```

Resultado:

- el grafo escribe `structurer_memory_query` y `evaluator_memory_query`;
- el grafo mantiene `*_retrieved_memory_context`;
- los eventos runtime incluyen `retrieval_requested`, `retrieval_returned` y
  `retrieval_used`;
- TypeScript y Vite compilan correctamente.

## Siguiente paso recomendado

El siguiente hito logico es M3:

```text
RAG inicial para modeler
```

Una vez que la recuperacion es observable, el `modeler` puede empezar a usar
memoria antes de su primera decision de modelo/politica, no solo en reintentos
o en memorias generadas al final de la run.
