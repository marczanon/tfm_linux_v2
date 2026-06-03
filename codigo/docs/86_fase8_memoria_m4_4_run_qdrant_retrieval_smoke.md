# Fase 8 - Memoria M4.4: run con backend Qdrant y comprobacion de retrieval

Fecha: 2026-06-03.

## Objetivo

Comprobar que Qdrant no solo sirve para migrar memoria, sino que puede ser
seleccionado por una run real del pipeline mediante `TFM_MEMORY_BACKEND=qdrant`.

Este hito valida la conexion entre:

- scripts de ejecucion;
- `get_default_vector_memory_store(...)`;
- `PipelineMemoryConfig`;
- artefactos `memory_query.json` y `retrieved_memory_context.json`;
- benchmark de efecto de memoria.

## Cambio aplicado

Los scripts que antes construian `LocalJsonVectorMemoryStore` directamente pasan
a usar la fabrica configurable:

- `codigo/scripts/run_dataset_pipeline_with_memory.py`;
- `codigo/scripts/run_cwru_pipeline_with_memory.py`;
- `codigo/scripts/run_nasa_ims_agentic_retry.py`.

Con ello, el backend se selecciona por entorno:

```text
TFM_MEMORY_BACKEND=json
TFM_MEMORY_BACKEND=qdrant
TFM_QDRANT_HOST=http://127.0.0.1:6333
```

Esta es la comprobacion importante: los agentes y el grafo siguen usando el
mismo contrato `VectorMemoryStore`, pero ahora el store concreto puede ser
Qdrant.

## Smoke ejecutado

Se ejecuta una run CWRU con memoria activa y backend Qdrant:

```text
TFM_MEMORY_BACKEND=qdrant \
TFM_QDRANT_HOST=http://127.0.0.1:6333 \
python -m codigo.scripts.run_cwru_pipeline_with_memory \
  --run-id cwru-memory-qdrant-m4-4-smoke-001 \
  --embedding-provider local_hash \
  --hash-dimension 128 \
  --skip-decision-memory
```

Resultado:

```text
run_id: cwru-memory-qdrant-m4-4-smoke-001
dataset: cwru_bearing
final_stage: completed
approved: true
precision: 0.9991497803599263
recall: 1.0
f1_score: 0.9995747093847462
false_positive_rate: 0.05128205128205128
errors: []
```

Artefactos relevantes:

- `codigo/reports/cwru_bearing/cwru-memory-qdrant-m4-4-smoke-001/agent_memory/structurer/retrieved_memory_context.json`;
- `codigo/reports/cwru_bearing/cwru-memory-qdrant-m4-4-smoke-001/agent_memory/modeler/retrieved_memory_context.json`;
- `codigo/reports/cwru_bearing/cwru-memory-qdrant-m4-4-smoke-001/agent_memory/evaluator/retrieved_memory_context.json`.

Los tres contextos declaran:

```text
retrieval_backend: qdrant_vector_memory_store
embedding_model: local_hash_embedding:v1
```

Items recuperados:

- `structurer`: 2 recuerdos CWRU;
- `modeler`: 0 recuerdos CWRU, esperado porque la memoria Qdrant migrada no
  contiene todavia candidatos CWRU del modelador;
- `evaluator`: 2 recuerdos CWRU.

## Benchmark de efecto de memoria

Se ejecuta el benchmark sobre la run Qdrant:

```text
python -m codigo.scripts.benchmark_memory_effect \
  --run-id cwru-memory-qdrant-m4-4-smoke-001 \
  --output-dir codigo/reports/memory_benchmarks/m4_4_qdrant_smoke \
  --variant cwru-memory-qdrant-m4-4-smoke-001=retrieval_only
```

Resultado:

```text
retrieval_run_count: 1
memory_used_run_count: 0
invalid_usage_run_count: 0
variant_counts:
  retrieval_only: 1
```

Interpretacion:

- Qdrant se usa realmente dentro del pipeline;
- el retrieval queda persistido y medible;
- al ejecutarse sin LLM, los agentes fallback no declaran uso/cita de memoria;
- no hay uso invalido.

## Verificacion automatica

Se anade `codigo/tests/test_memory_backend_script_selection.py` para impedir
regresiones: los runners deben poder seleccionar Qdrant mediante entorno.

Tests ejecutados:

```text
python -m unittest \
  codigo.tests.test_memory_backend_script_selection \
  codigo.tests.test_vector_memory_store \
  codigo.tests.test_memory_backend_migration \
  codigo.tests.test_memory_effect_benchmark
```

Resultado:

```text
Ran 27 tests in 0.029s
OK
```

## Limitaciones

- La comprobacion usa `local_hash_embedding` para aislar infraestructura;
- no es una run Qwen/LLM, por lo que no valida citas agenticas ni influencia
  deliberativa;
- CWRU se usa como regresion rapida, no como el perfil principal
  run-to-failure;
- el modeler no recupera recuerdos CWRU porque todavia no hay memoria CWRU de
  modelador en Qdrant.

## Siguiente paso

El siguiente paso logico es M4.5:

- ejecutar una run con Qdrant y Qwen/LLM donde los agentes puedan declarar uso
  de memoria;
- preferentemente sobre `run_to_failure_degradation`, no sobre CWRU;
- usar `qwen3-embedding:0.6b` si Ollama esta estable;
- comparar `memory_full/json` frente a `memory_full/qdrant` y, si procede,
  `memory_off`;
- documentar si Qdrant cambia solo la infraestructura de retrieval o tambien
  la deliberacion de los agentes.
