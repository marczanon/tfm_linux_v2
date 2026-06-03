# Fase 8 - Memoria M1: cockpit frontend de memoria

Fecha: 2026-06-03.

## Objetivo

Implementar el primer hito de la hoja de ruta de memoria RAG avanzada:
convertir la memoria persistida en una vista mas intuitiva, operable y
auditable desde el frontend, sin cambiar todavia el backend vectorial local.

## Inventario previo

Capacidad buscada:

```text
Mostrar el ciclo de memoria candidato -> indexado -> recuperado -> usado ->
auditado en la pestana de agentes, reutilizando la API read-only existente.
```

Busquedas realizadas:

```text
rg -n "memory|memoria|Memory|collections|memory_record|RetrievedMemory|memory_usage|memory_candidate|DecisionEpisode" codigo/app codigo/frontend/src codigo/tests codigo/docs
rg -n "memory/collections|memory/records|MemoryCollection|MemoryRecord|memoryRecords|selectedMemory|memoria" codigo/frontend/src/App.tsx codigo/frontend/src/types.ts codigo/frontend/src/styles.css
rg -n "@router.*memory|memory_records|memory_record|list_memory|MemoryCollectionSummary|MemoryRecordSummary" codigo/app/api codigo/tests/test_api_memory.py codigo/app/api/routes.py
```

Piezas encontradas:

- `codigo/app/schemas/api_memory.py`:
  - `MemoryCollectionSummary`;
  - `MemoryRecordSummary`;
- `codigo/app/services/memory_registry.py`:
  - `list_memory_collections`;
  - `list_memory_records`;
  - `get_memory_record`;
- `codigo/app/api/routes.py`:
  - `GET /memory/collections`;
  - `GET /memory/records`;
  - `GET /memory/records/{memory_record_id}`;
- `codigo/frontend/src/App.tsx`:
  - `AgentMemoryPanel`;
  - `MemoryRecordList`;
  - `MemoryRecordDetail`;
- `codigo/docs/42_memoria_persistida_frontend_fase5.md`;
- `codigo/docs/78_fase8_hoja_ruta_memoria_rag_avanzada.md`.

Decision:

```text
extend
```

Motivo: la memoria, API, contratos y vista basica ya existian. El hito M1 no
necesita un endpoint paralelo ni un nuevo store; necesita reinterpretar la
informacion existente como cockpit de control.

## Cambios implementados

### Carga de registros

La vista de memoria deja de pedir solo recuerdos reutilizables. Ahora recupera
todos los recuerdos del agente seleccionado para poder mostrar:

- reutilizables;
- excluidos;
- frontera;
- warnings;
- auditorias;
- candidatos indexados.

Esto no cambia la API ni modifica la memoria persistida; solo amplia la lectura
del frontend.

### Cockpit de memoria

`AgentMemoryPanel` pasa de una lista tecnica a un cockpit compacto con:

- total de recuerdos;
- recuerdos reutilizables;
- datasets cubiertos;
- recuerdos excluidos;
- ciclo visual:
  - candidatos;
  - indexados;
  - recuperados en runtime;
  - usados/citados por agentes;
  - auditorias;
- distribucion por rol de memoria;
- distribucion por tipo de origen;
- bloque de runtime con eventos de recuperacion/cita de memoria;
- listado de recuerdos con badges de `reutilizable`, `excluido` y `citado`.

### Navegacion desde eventos runtime

Los `memory_record_id` citados por eventos agenticos dejan de mostrarse como
texto pasivo. Ahora son botones que abren el detalle completo del recuerdo.

### Detalle enriquecido del recuerdo

El detalle de `ReasoningMemoryRecord` muestra:

- estado operativo (`recuperable`, `indexado`, `excluido`);
- veredicto humano;
- `run_id`;
- `decision_id`;
- origen;
- resultado;
- modelo de embedding;
- dimension del embedding;
- `vector_id`;
- tags;
- metricas asociadas;
- contenido indexable;
- ruta de origen si existe.

### Responsive

Se anaden estilos para que el cockpit sea legible en escritorio y movil. En
pantallas estrechas el ciclo pasa a una columna y se ocultan las flechas
laterales para evitar solapes.

## Limites conscientes

Este hito no implementa todavia:

- persistencia explicita de `memory_query.json`;
- persistencia de `retrieved_memory_context.json`;
- backend Qdrant;
- reranking Qwen;
- hybrid search;
- quality gate de retrieval;
- consolidacion/reflexion de memoria;
- candidatos pendientes no indexados.

La vista muestra candidatos ya convertidos en memoria indexada mediante
`source_type="memory_candidate"`. Los candidatos pendientes como artefactos de
run se abordaran en hitos posteriores, probablemente al enlazar snapshots,
artefactos y memoria en una linea temporal comun.

## Validacion

Validacion ejecutada:

```text
npm run build
```

Resultado:

- TypeScript compila sin errores;
- Vite genera build de produccion correctamente.

## Siguiente paso recomendado

Continuar con M2:

```text
observabilidad de retrieval
```

Para ello habra que persistir y exponer cada consulta RAG y cada contexto
recuperado, de forma que el cockpit pueda distinguir no solo recuerdos
existentes, sino consultas concretas, scores, filtros, backend, modelo de
embeddings y recuerdos descartados por el agente.
