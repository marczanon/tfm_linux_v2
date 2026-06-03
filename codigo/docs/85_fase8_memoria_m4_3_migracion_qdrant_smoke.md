# Fase 8 - Memoria M4.3: migracion JSON -> Qdrant y smoke real

Fecha: 2026-06-03.

## Objetivo

Convertir el backend Qdrant opcional de M4.2 en una pieza operativa:

- migrar colecciones existentes de `LocalJsonVectorMemoryStore` a Qdrant;
- comparar retrieval local frente a Qdrant con el mismo proveedor de embeddings;
- levantar Qdrant como servicio Docker opcional;
- ejecutar un smoke real contra `http://127.0.0.1:6333`.

El objetivo no es sustituir todavia el backend JSON como baseline. JSON sigue
siendo la linea reproducible y Qdrant pasa a ser backend experimental validado.

## Reutilizacion aplicada

Capacidad anadida:

- migracion y comparacion de backends de memoria vectorial.

Revision previa:

- `vector_memory.py` ya exponia `VectorMemoryStore`,
  `LocalJsonVectorMemoryStore`, `QdrantVectorMemoryStore` y
  `get_default_vector_memory_store(...)`;
- `reasoning_memory_index.py` ya generaba la memoria JSON local;
- `benchmark_memory_effect.py` ya media si la memoria recuperada era usada por
  agentes;
- `docker-compose.yml` ya era el propietario de servicios reproducibles.

Decision:

- crear `memory_backend_migration.py` como servicio canonico;
- crear `migrate_memory_to_qdrant.py` como CLI operativo;
- no duplicar indexacion: la migracion lee `ReasoningMemoryRecord` ya
  persistidos;
- no forzar Qdrant en API/frontend todavia;
- anadir Qdrant al compose como profile opcional `memory-qdrant`.

## Implementacion

Nuevo servicio:

- `codigo/app/services/memory_backend_migration.py`.

Funciones principales:

- `migrate_memory_records_between_stores(...)`;
- `migrate_local_json_memory_to_qdrant(...)`;
- `compare_memory_backends(...)`;
- `build_memory_migration_verification_queries(...)`;
- `write_memory_backend_migration_report(...)`.

El wrapper `LocalJson -> Qdrant` crea un espejo local temporal reembebido con el
mismo proveedor usado en Qdrant. Esto evita comparar Qdrant con vectores JSON
persistidos previamente usando otro embedding. La comparacion resultante mide
backend contra backend en igualdad de condiciones.

Nuevo script:

```text
python -m codigo.scripts.migrate_memory_to_qdrant \
  --embedding-provider local_hash \
  --hash-dimension 128 \
  --qdrant-host http://127.0.0.1:6333 \
  --output-dir codigo/reports/memory_backend_migrations/m4_3_qdrant_smoke
```

Variables Docker anadidas:

```text
TFM_MEMORY_BACKEND=json
TFM_QDRANT_HOST=http://qdrant:6333
TFM_QDRANT_PORT=6333
TFM_QDRANT_GRPC_PORT=6334
TFM_QDRANT_TIMEOUT_SECONDS=10
TFM_QDRANT_DISTANCE=Cosine
```

Servicio Docker opcional:

```text
docker compose --env-file codigo/docker/.env.example \
  -f codigo/docker/docker-compose.yml \
  --profile memory-qdrant up -d qdrant
```

## Ajuste de API Qdrant

Se actualiza `QdrantVectorMemoryStore.query(...)` para usar
`/collections/{collection_name}/points/query`, la Query API recomendada por
Qdrant para busqueda actual y futura. Se mantiene fallback a
`/points/search` si un despliegue antiguo devuelve error compatible.

Fuentes:

- Qdrant Query API: https://api.qdrant.tech/api-reference/search/query-points
- Qdrant Search API marcada como deprecated:
  https://api.qdrant.tech/api-reference/search/points

## Smoke real

Se levanto Qdrant con Docker:

```text
docker compose --env-file codigo/docker/.env.example \
  -f codigo/docker/docker-compose.yml \
  --profile memory-qdrant up -d qdrant
```

Comprobacion:

```text
curl -sS http://127.0.0.1:6333/readyz
```

Resultado:

```text
all shards are ready
```

Migracion ejecutada:

```text
python -m codigo.scripts.migrate_memory_to_qdrant \
  --embedding-provider local_hash \
  --hash-dimension 128 \
  --qdrant-host http://127.0.0.1:6333 \
  --output-dir codigo/reports/memory_backend_migrations/m4_3_qdrant_smoke
```

Resultado:

```text
migrated_record_count: 20
collection_counts:
  evaluator_memory: 2
  modeler_memory: 16
  structurer_memory: 2
comparison_query_count: 3
average_overlap_ratio: 1.0
exact_match_count: 3
```

Artefactos:

- `codigo/reports/memory_backend_migrations/m4_3_qdrant_smoke/memory_backend_migration.json`;
- `codigo/reports/memory_backend_migrations/m4_3_qdrant_smoke/memory_backend_migration.md`.

Colecciones creadas en Qdrant:

```text
structurer_memory
evaluator_memory
modeler_memory
```

## Verificacion automatica

Tests ejecutados:

```text
python -m unittest codigo.tests.test_memory_backend_migration codigo.tests.test_vector_memory_store
```

Resultado:

```text
Ran 23 tests in 0.018s
OK
```

Cobertura:

- migracion entre stores;
- comparacion de retrieval por IDs;
- generacion de queries de smoke por agente/dataset;
- wrapper `LocalJson -> Qdrant` con Qdrant parcheado;
- `QdrantVectorMemoryStore` usando `points/query`;
- fallback estructural para store local.

## Limitaciones

- El smoke usa `local_hash_embedding` para validar infraestructura sin depender
  de Ollama;
- falta ejecutar el mismo flujo con `qwen3-embedding:0.6b`;
- falta usar `TFM_MEMORY_BACKEND=qdrant` dentro de una run agentica real;
- falta comparar efecto de memoria JSON vs Qdrant en
  `benchmark_memory_effect.py`;
- no se ha implementado todavia busqueda hibrida, sparse vectors ni reranking.

## Siguiente paso

Actualizacion 2026-06-03: M4.4 queda implementado en
`86_fase8_memoria_m4_4_run_qdrant_retrieval_smoke.md`.

M4.4 cubre:

- adaptar los runners para seleccionar Qdrant por entorno;
- ejecutar una run CWRU real con `TFM_MEMORY_BACKEND=qdrant`;
- persistir en artefactos que el backend de retrieval fue
  `qdrant_vector_memory_store`;
- clasificar la run como `retrieval_only` mediante el benchmark de efecto de
  memoria.

Queda como siguiente paso M4.5:

- ejecutar una run Qwen/LLM con `TFM_MEMORY_BACKEND=qdrant`;
- preferentemente sobre `run_to_failure_degradation`;
- comparar esa run contra JSON local y memoria desactivada.
