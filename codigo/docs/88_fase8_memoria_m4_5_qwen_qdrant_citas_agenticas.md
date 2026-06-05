# Fase 8 - Memoria M4.5: Qwen/LLM + Qdrant con citas agenticas

Fecha: 2026-06-04.

## Objetivo

Validar que Qdrant no solo recupera memoria dentro del pipeline, sino que una
run con agentes Qwen/LLM puede:

- usar `QdrantVectorMemoryStore` como backend real de retrieval;
- consultar memoria vectorial indexada con `qwen3-embedding:0.6b`;
- citar recuerdos recuperados dentro de la decision agentica;
- declarar como influyeron esos recuerdos en la decision;
- medir el resultado con `benchmark_memory_effect.py`.

La comprobacion se hace sobre `nasa_ims_bearing` con perfil
`run_to_failure_degradation`, usando la politica temporal
`nasa_ims_temporal_v1`. Las etiquetas siguen siendo proxy temporal, no ground
truth oficial de NASA IMS.

## Reutilizacion aplicada

Capacidad anadida:

```text
Ejecutar una run Qwen/LLM con memoria Qdrant y embeddings Qwen reales.
```

Revision previa:

- `codigo/app/services/vector_memory.py` ya contenia
  `QdrantVectorMemoryStore` y `get_default_vector_memory_store(...)`;
- `codigo/scripts/migrate_memory_to_qdrant.py` ya migraba JSON -> Qdrant;
- `codigo/scripts/run_dataset_pipeline_with_memory.py` ya era el runner comun
  multi-dataset con memoria, pero no exponia `use_llm`;
- `PipelineRunRequest` ya tenia el campo `use_llm`;
- `benchmark_memory_effect.py` ya media retrieval, citas, uso declarado e
  invalid usage.

Decision:

- `extend` el runner comun para exponer `--use-llm`;
- no crear runner nuevo para M4.5;
- remigrar Qdrant con `qwen3-embedding:0.6b`;
- mantener Qdrant como backend opcional seleccionado por entorno.

## Preparacion de Qdrant con Qwen embeddings

Primero se confirmo que Ollama y Qdrant estaban activos:

```text
curl -sS http://127.0.0.1:6333/readyz
curl -sS http://127.0.0.1:11434/api/tags
```

Qdrant estaba listo y Ollama tenia disponibles:

- `qwen3.5:4b`;
- `qwen3-embedding:0.6b`.

La prueba directa del embedding Qwen devolvio dimension `1024`, por lo que las
colecciones heredadas de M4.4, indexadas con `local_hash_embedding` de 128
dimensiones, no eran validas para una comprobacion fiel.

Se remigro la memoria:

```text
python -m codigo.scripts.migrate_memory_to_qdrant \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b \
  --qdrant-host http://127.0.0.1:6333 \
  --embedding-timeout-seconds 60 \
  --output-dir codigo/reports/memory_backend_migrations/m4_5_qwen_embedding_prep
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

Las tres colecciones quedaron en dimension `1024`:

- `structurer_memory`: 2 puntos;
- `modeler_memory`: 16 puntos;
- `evaluator_memory`: 2 puntos.

Artefactos:

- `codigo/reports/memory_backend_migrations/m4_5_qwen_embedding_prep/memory_backend_migration.json`;
- `codigo/reports/memory_backend_migrations/m4_5_qwen_embedding_prep/memory_backend_migration.md`.

## Ajuste de CLI

Se actualiza `codigo/scripts/run_dataset_pipeline_with_memory.py` para exponer
`--use-llm` y trasladarlo a `PipelineRunRequest.use_llm`.

Motivo: `pipeline_runner.py` ya sabia crear agentes Ollama cuando
`request.use_llm=true`, pero el CLI comun no permitia activar ese campo.

Test anadido:

- `codigo/tests/test_memory_backend_script_selection.py`;
- caso `test_dataset_runner_request_from_args_keeps_use_llm`.

Verificacion:

```text
python -m unittest codigo.tests.test_memory_backend_script_selection
python -m unittest codigo.tests.test_pipeline_runner codigo.tests.test_api_runs
python -m unittest discover codigo/tests
```

Resultado final:

```text
Ran 337 tests in 1.105s
OK
```

## Run M4.5 ejecutada

Preflight:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --adapter-id nasa_ims_bearing \
  --dataset-policy-id nasa_ims_temporal_v1 \
  --run-id m4-5-qwen-qdrant-nasa-smoke-001 \
  --use-memory \
  --use-llm \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b \
  --plan-only
```

El plan permitio las fases completas y declaro:

- `dataset_id=nasa_ims_bearing`;
- `supervision_profile=run_to_failure_degradation`;
- `dataset_policy_id=nasa_ims_temporal_v1`;
- `use_memory=true`;
- `use_llm=true`;
- sin bloqueos de politica.

Ejecucion:

```text
env TFM_MEMORY_BACKEND=qdrant \
  TFM_QDRANT_HOST=http://127.0.0.1:6333 \
  TFM_LLM_MODEL=qwen3.5:4b \
  TFM_LLM_TIMEOUT_SECONDS=180 \
  python -m codigo.scripts.run_dataset_pipeline_with_memory \
    --dataset-id nasa_ims_bearing \
    --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
    --adapter-id nasa_ims_bearing \
    --dataset-policy-id nasa_ims_temporal_v1 \
    --run-id m4-5-qwen-qdrant-nasa-smoke-001 \
    --use-memory \
    --use-llm \
    --embedding-provider ollama \
    --embedding-model qwen3-embedding:0.6b \
    --embedding-timeout-seconds 60
```

Resultado de la run:

```text
run_id: m4-5-qwen-qdrant-nasa-smoke-001
final_stage: completed
approved: false
errors: []
model_name: pca_reconstruction_error
precision: 0.5
recall: 1.0
f1_score: 0.6667
false_positive_rate: 1.0
```

Metricas temporales:

```text
degradation_detected_before_failure_rate: 1.0
degradation_mean_lead_time_to_failure: 1200.9728
degradation_mean_false_alarm_rate_nominal: 0.6667
degradation_mean_score_trend_spearman: 0.9167
```

Interpretacion: la run valida memoria/citas, pero no valida calidad operacional
del modelo. La no aprobacion es coherente con el FPR alto y no debe ocultarse.

## Evidencia de memoria usada

Artefactos clave:

- `codigo/reports/nasa_ims_bearing/m4-5-qwen-qdrant-nasa-smoke-001/agent_memory/modeler/retrieved_memory_context.json`;
- `codigo/reports/nasa_ims_bearing/m4-5-qwen-qdrant-nasa-smoke-001/agent_memory/modeler/memory_candidate.md`;
- `codigo/reports/runs/m4-5-qwen-qdrant-nasa-smoke-001/decisions.json`.

El contexto recuperado por `modeler` declara:

```text
retrieval_backend: qdrant_vector_memory_store
embedding_model: ollama:qwen3-embedding:0.6b
retrieved_count: 3
```

El `modeler` declara:

```text
used_memory_context: true
memory_record_uses: 3
```

Recuerdos citados:

- `nasa-ims-synth-agentic-qwen-fase4-coherence-audit-attempt-01:decision_episode:001:candidate:modeler:memory:modeler`;
- `nasa-ims-synth-agentic-qwen-fase4-model-family-attempt-01:decision_episode:001:candidate:modeler:memory:modeler`;
- `nasa-ims-synth-agentic-qwen-fase4-pca-execute-attempt-01:decision_episode:001:candidate:modeler:memory:modeler`.

Resumen declarado por el agente:

```text
Los recuerdos recuperados indican que el umbral anterior fue peligrosamente
bajo, causando FPR=1.0. Se evita repetir este error ajustando el umbral a 0.99
y priorizando familias de modelos mas estables (PCA) sobre las hiper-sensibles
(Isolation Forest) sin evidencia de mejora en recall.
```

## Benchmark de efecto de memoria

Comando:

```text
python -m codigo.scripts.benchmark_memory_effect \
  --run-id m4-5-qwen-qdrant-nasa-smoke-001 \
  --output-dir codigo/reports/memory_benchmarks/m4_5_qwen_qdrant_smoke \
  --variant m4-5-qwen-qdrant-nasa-smoke-001=memory_full
```

Resultado:

```text
retrieval_run_count: 1
memory_used_run_count: 1
invalid_usage_run_count: 0
quality_gate_warning_run_count: 1
agent_usage_counts:
  modeler: 1
variant_counts:
  memory_full: 1
```

El benchmark clasifica la run como:

```text
memory_mode: memory_used
modeler: used_aligned
retrieved: 3
cited: 3
gate pass/caution/exclude: 0/3/0
```

Artefactos:

- `codigo/reports/memory_benchmarks/m4_5_qwen_qdrant_smoke/memory_effect_benchmark.json`;
- `codigo/reports/memory_benchmarks/m4_5_qwen_qdrant_smoke/memory_effect_benchmark.md`.

## Limitaciones

- El dataset usado es pequeno y sintetico/preextraido; sirve como smoke
  agentico, no como resultado industrial final.
- La memoria usada por `modeler` fue clasificada como `caution` por el quality
  gate, no como `pass`, porque procede de casos parcialmente soportados o
  rechazados. Su uso fue valido como frontera/advertencia, pero debe tratarse
  con cuidado.
- La run termino `approved=false` por falsas alarmas altas. Esto refuerza que
  el evaluador no debe aprobar por presencia de memoria.
- No hay comparativa causal con `memory_off` o JSON en esta comprobacion.
- No se implementa todavia reranking Qwen, hybrid search ni retrieval grading
  avanzado.

## Conclusiones

M4.5 queda validado: existe una run Qwen/LLM sobre
`run_to_failure_degradation` que recupera memoria desde Qdrant, usando
`qwen3-embedding:0.6b`, y el `modeler` cita recuerdos recuperados con uso
declarado y auditado.

La memoria ya no queda en `retrieval_only`: pasa a `memory_used` sin uso
invalido. El resultado operacional del modelo sigue siendo insuficiente, lo que
abre el siguiente bloque de trabajo sobre mejora temporal del perfil
run-to-failure.

## Siguiente paso

Opciones razonables:

1. Ejecutar una variante controlada `memory_off` o JSON para comparar causalidad.
2. Repetir M4.5 sobre una run NASA IMS mas larga.
3. Retomar el perfil `run_to_failure_degradation` y mejorar histeresis,
   alertas sostenidas y reduccion de falsas alarmas.
4. Abrir M5: reranking Qwen sobre los recuerdos recuperados antes de inyectarlos
   al prompt.
