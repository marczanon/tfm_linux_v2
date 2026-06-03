# Fase 8 - Memoria M4.2: backend Qdrant opcional

Fecha: 2026-06-03.

## Objetivo

Iniciar el salto de la memoria RAG local hacia una base vectorial real sin
romper el baseline reproducible del TFM. El resultado de este hito no es una
migracion obligatoria, sino una segunda implementacion compatible con el
contrato `VectorMemoryStore`:

- `LocalJsonVectorMemoryStore` sigue siendo el backend por defecto para tests,
  reproducibilidad y ejecuciones locales simples;
- `QdrantVectorMemoryStore` queda disponible como backend avanzado para
  experimentos con base vectorial externa;
- los agentes no cambian su contrato: siguen consultando, citando y auditando
  memoria mediante `AgentMemoryQuery` y `RetrievedMemoryContext`.

## Reutilizacion aplicada

Capacidad anadida:

- seleccionar y usar un backend Qdrant para memoria agentica vectorial.

Revision previa:

- `vector_memory.py` ya contenia la interfaz `VectorMemoryStore`,
  `LocalJsonVectorMemoryStore`, `EmbeddingProvider`,
  `OllamaEmbeddingProvider`, `LocalHashEmbeddingModel` y los contratos de
  conversion de recuerdos;
- `reasoning_memory_index.py` ya indexaba recuerdos usando el store JSON local;
- `memory_registry.py` ya exponia gobierno y lectura desde API/frontend;
- `test_vector_memory_store.py` ya era el punto natural para validar el
  contrato vectorial.

Decision:

- extender `codigo/app/services/vector_memory.py`;
- mantener `LocalJsonVectorMemoryStore` sin cambios funcionales;
- crear `QdrantVectorMemoryStore` como backend opcional;
- anadir `get_default_vector_memory_store(...)` para seleccionar backend por
  entorno;
- cubrir Qdrant con tests HTTP mockeados, sin requerir un servidor Qdrant real
  en la suite basica.

## Implementacion

Se anade `QdrantVectorMemoryStore` con estas operaciones:

- `upsert(record)`: calcula embedding, crea la coleccion si no existe y guarda
  un punto Qdrant;
- `rebuild(records)`: opcionalmente borra colecciones conocidas y reindexa;
- `list_records(collection_name)`: usa scroll y reconstruye
  `ReasoningMemoryRecord` desde el payload;
- `delete(memory_record_id)`: localiza el recuerdo y elimina el punto;
- `query(query)`: busca en la coleccion del agente y en
  `shared_methodology_memory`, reconstruye registros, aplica los filtros
  Pydantic existentes y devuelve `RetrievedMemoryContext`.

Cada punto Qdrant contiene:

- vector denso generado por el proveedor de embeddings configurado;
- `memory_record_id` estable;
- `collection_name`;
- `target_agent`;
- `dataset`;
- `source_type`;
- `memory_role`;
- `human_verdict`;
- `reusable_as_context`;
- `exclude_from_context`;
- `run_id`;
- `decision_id`;
- `tags`;
- el `ReasoningMemoryRecord` completo en `payload.record`;
- el texto indexable en `payload.text`.

El identificador de punto se deriva con UUIDv5 a partir de
`memory_record_id`, por lo que los upserts son reproducibles y no dependen de
IDs aleatorios.

## Configuracion

La nueva fabrica `get_default_vector_memory_store(...)` permite elegir backend:

```text
TFM_MEMORY_BACKEND=json
TFM_MEMORY_BACKEND=qdrant
```

Variables relevantes:

```text
TFM_EMBEDDING_PROVIDER=ollama|local_hash
TFM_EMBEDDING_MODEL=qwen3-embedding:0.6b
TFM_EMBEDDING_DIMENSION=128
TFM_QDRANT_HOST=http://127.0.0.1:6333
TFM_QDRANT_API_KEY=
TFM_QDRANT_TIMEOUT_SECONDS=10
TFM_QDRANT_DISTANCE=Cosine
```

Tambien se admiten `QDRANT_URL` y `QDRANT_API_KEY` como nombres alternativos.

## Estado frente a RAG industrial

Este hito cubre la primera frontera: sustituir el indice JSON por un backend
vectorial real manteniendo el mismo contrato agentico. Quedan fuera todavia:

- smoke test con contenedor Qdrant real;
- migracion automatica JSON -> Qdrant para colecciones existentes;
- Docker Compose opcional con servicio Qdrant;
- busqueda hibrida densa+sparse;
- reranking Qwen;
- retrieval grading avanzado tipo CRAG;
- UI para comparar backends;
- benchmarks con memoria JSON frente a Qdrant.

## Fuentes tecnicas

- Qdrant documentation: https://qdrant.tech/documentation/
- Qdrant hybrid queries: https://qdrant.tech/documentation/search/hybrid-queries/

## Verificacion

Tests ejecutados:

```text
python -m unittest codigo.tests.test_vector_memory_store
```

Resultado:

```text
Ran 20 tests in 0.016s
OK
```

Cobertura especifica:

- `QdrantVectorMemoryStore` cumple `VectorMemoryStore`;
- `upsert` envia vector y payload completo;
- `query` consulta memoria del agente y memoria metodologica compartida;
- `list_records` reconstruye registros desde scroll;
- `delete` elimina puntos por ID estable;
- `get_default_vector_memory_store` selecciona JSON por defecto y Qdrant por
  entorno.

## Siguiente paso

Actualizacion 2026-06-03: M4.3 queda implementado en
`85_fase8_memoria_m4_3_migracion_qdrant_smoke.md`.

M4.3 cubre:

- anadir script de migracion `LocalJsonVectorMemoryStore -> Qdrant`;
- levantar Qdrant opcional con Docker Compose o instrucciones de smoke local;
- ejecutar una prueba real de migracion con `local_hash_embedding`;
- comparar retrieval JSON reembebido vs Qdrant con solapamiento 1.0.

Queda como siguiente paso M4.4:

- ejecutar una run agentica real con `TFM_MEMORY_BACKEND=qdrant`;
- repetir con `qwen3-embedding:0.6b` si Ollama esta disponible;
- comparar efecto de memoria JSON vs Qdrant en el benchmark de efecto de
  memoria.
