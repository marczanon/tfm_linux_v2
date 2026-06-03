# Cierre de sesion - 2026-06-03

## Para retomar el 2026-06-04

Este documento resume el punto exacto en el que queda el proyecto al final de
la sesion del 2026-06-03. La idea es que una nueva conversacion pueda continuar
sin reconstruir contexto.

## Recapitulacion corta

El proyecto ha seguido esta secuencia:

1. Se dejo una base solida del nuevo perfil principal
   `run_to_failure_degradation`.
2. Se abrio una linea transversal para llevar la memoria RAG agentica al maximo
   defendible: cockpit, observabilidad, gobierno, benchmark, quality gate,
   Qdrant y comprobaciones reales.
3. Queda como siguiente paso inmediato terminar la comprobacion Qdrant con
   Qwen/LLM en una run real, idealmente sobre `run_to_failure_degradation`.
4. Despues se retomara el perfil run-to-failure para llevarlo al maximo:
   histeresis, RUL experimental, autoencoder, vistas industriales y mas control
   agentico.
5. Una vez memoria y run-to-failure esten muy maduros, la siguiente fase
   probable sera limpiar y elevar la aplicacion web: frontend mas funcional,
   original, industrial y con elementos diferenciales.

## Estado del perfil run-to-failure

El perfil `run_to_failure_degradation` ya no es una idea secundaria. Es el
centro de investigacion del TFM.

Lo que ya esta asentado:

- cambio metodologico desde CWRU/NASA como datasets historicos hacia perfiles
  `binary_fault_classification` y `run_to_failure_degradation`;
- panel de control temporal con estado de motor, salud, riesgo, lead time,
  alertas, criticos y tira de ventanas;
- separacion conceptual entre pico aislado, aviso sostenido y fallo historico;
- metricas temporales primarias frente a metricas binarias auxiliares;
- herramientas agenticas temporales:
  - `evidence_lookup` enriquecida;
  - `temporal_health_lookup`;
  - `degradation_metrics_lookup`;
- `modeler` como estratega temporal;
- `evaluator` como auditor operacional;
- recomendacion agentica visible en frontend;
- post-mortem y memoria adaptados al perfil temporal.

Documentos clave:

- `codigo/docs/66_fase7_perfiles_supervision_binary_run_to_failure.md`
- `codigo/docs/69_fase7_cierre_base_run_to_failure.md`
- `codigo/docs/70_fase7_hito9_panel_control_run_to_failure.md`
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`
- `codigo/docs/72_fase8_hito1_evidence_pack_temporal_agentes.md`
- `codigo/docs/73_fase8_hito2_herramientas_temporales_agenticas.md`
- `codigo/docs/74_fase8_hito3_modeler_estratega_run_to_failure.md`
- `codigo/docs/75_fase8_hito4_evaluador_operacional_debate_temporal.md`
- `codigo/docs/76_fase8_hito5_recomendacion_agentica_frontend.md`
- `codigo/docs/77_fase8_hito6_postmortem_memoria_temporal.md`

## Decision metodologica importante

Los agentes Qwen/LLM siguen siendo el centro del TFM.

La memoria, Qdrant, benchmarks, quality gates y herramientas deterministas no
sustituyen a los agentes. Su funcion es:

- darles evidencia;
- hacer sus decisiones trazables;
- controlar riesgos;
- medir si usan bien la memoria;
- permitir comparar variantes;
- hacer viable el uso de LLM pequenos en entornos industriales.

La linea de investigacion sigue siendo intentar llegar lo mas lejos posible con
Qwen/LLM locales. Al final se evaluara su viabilidad real, pero no se abandona
esa apuesta antes de exprimirla.

## Estado de memoria RAG avanzada

La linea de memoria se ha llevado mucho mas lejos. Documentos principales:

- `codigo/docs/78_fase8_hoja_ruta_memoria_rag_avanzada.md`
- `codigo/docs/79_fase8_memoria_m1_cockpit_frontend.md`
- `codigo/docs/80_fase8_memoria_m2_observabilidad_retrieval.md`
- `codigo/docs/81_fase8_memoria_m3_modeler_transversal_gobierno.md`
- `codigo/docs/82_fase8_memoria_m4_pre_benchmark_efecto_memoria.md`
- `codigo/docs/83_fase8_memoria_m4_1_quality_gate_benchmark_controlado.md`
- `codigo/docs/84_fase8_memoria_m4_2_qdrant_backend_opcional.md`
- `codigo/docs/85_fase8_memoria_m4_3_migracion_qdrant_smoke.md`
- `codigo/docs/86_fase8_memoria_m4_4_run_qdrant_retrieval_smoke.md`

### Hitos completados

M1:

- cockpit frontend de memoria persistida;
- ciclo candidato -> indexado -> recuperado -> usado -> auditado.

M2:

- persistencia de `memory_query.json`;
- enriquecimiento de `retrieved_memory_context.json`;
- eventos runtime de retrieval.

M3:

- memoria en la primera decision del `modeler`;
- memoria transversal por agente;
- curacion manual: excluir, restaurar, borrar.

M4-pre:

- benchmark offline para medir si la memoria hace algo;
- clasificacion de retrieval, citas, uso invalido y deltas frente a baseline.

M4.1:

- quality gate de memoria;
- recuerdos clasificados como `pass`, `caution` o `exclude_candidate`;
- variantes `memory_off`, `memory_full`, `memory_filtered`,
  `memory_conflict_excluded`, `retrieval_only`.

M4.2:

- `QdrantVectorMemoryStore`;
- `get_default_vector_memory_store(...)`;
- seleccion por entorno:
  - `TFM_MEMORY_BACKEND=json`;
  - `TFM_MEMORY_BACKEND=qdrant`;
- tests mockeados de Qdrant.

M4.3:

- migracion JSON -> Qdrant;
- script `codigo/scripts/migrate_memory_to_qdrant.py`;
- profile Docker `memory-qdrant`;
- smoke real contra `http://127.0.0.1:6333`;
- 20 recuerdos migrados;
- colecciones:
  - `evaluator_memory`: 2;
  - `modeler_memory`: 16;
  - `structurer_memory`: 2;
- comparativa con solapamiento medio 1.0 frente a baseline reembebido.

M4.4:

- los runners ya usan `get_default_vector_memory_store(...)`;
- run real CWRU con `TFM_MEMORY_BACKEND=qdrant`;
- run: `cwru-memory-qdrant-m4-4-smoke-001`;
- resultado: completed, approved, sin errores;
- artefactos con `retrieval_backend=qdrant_vector_memory_store`;
- benchmark clasificado como `retrieval_only`.

Artefactos clave de M4.4:

- `codigo/reports/cwru_bearing/cwru-memory-qdrant-m4-4-smoke-001/agent_memory/structurer/retrieved_memory_context.json`
- `codigo/reports/cwru_bearing/cwru-memory-qdrant-m4-4-smoke-001/agent_memory/modeler/retrieved_memory_context.json`
- `codigo/reports/cwru_bearing/cwru-memory-qdrant-m4-4-smoke-001/agent_memory/evaluator/retrieved_memory_context.json`
- `codigo/reports/memory_benchmarks/m4_4_qdrant_smoke/memory_effect_benchmark.json`
- `codigo/reports/memory_benchmarks/m4_4_qdrant_smoke/memory_effect_benchmark.md`

## Punto exacto donde queda la sesion

La ultima comprobacion completa fue:

```text
python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 336 tests in 1.116s
OK
```

Qdrant quedo levantado al cerrar la sesion:

```text
http://127.0.0.1:6333
```

Contenedor:

```text
tfm-fase6-qdrant-1
```

Si al retomar no esta levantado:

```text
docker compose --env-file codigo/docker/.env.example \
  -f codigo/docker/docker-compose.yml \
  --profile memory-qdrant up -d qdrant
```

Comprobar:

```text
curl -sS http://127.0.0.1:6333/readyz
```

Debe devolver:

```text
all shards are ready
```

## Siguiente paso exacto

El siguiente paso es M4.5:

```text
Run Qwen/LLM + Qdrant con memoria real y citas agenticas.
```

Objetivo:

- ejecutar una run donde `retrieval_backend=qdrant_vector_memory_store`;
- activar agentes Qwen/LLM;
- comprobar que los agentes no solo recuperan memoria, sino que pueden citarla
  y declarar su uso;
- medirlo con `benchmark_memory_effect.py`;
- compararlo contra JSON o memoria desactivada si el coste lo permite.

Preferencia metodologica:

- hacerlo sobre `run_to_failure_degradation`;
- si resulta demasiado lento o inestable, hacer primero una run CWRU Qwen+Qdrant
  como smoke y despues pasar a run-to-failure.

## Propuesta de orden para el 2026-06-04

1. Verificar que Qdrant y Ollama estan activos.
2. Verificar que existe memoria Qdrant indexada con el embedding elegido.
3. Decidir si M4.5 usa:
   - `local_hash_embedding` para smoke Qwen rapido;
   - `qwen3-embedding:0.6b` para comprobacion mas fiel al TFM.
4. Ejecutar una run Qwen/LLM con `TFM_MEMORY_BACKEND=qdrant`.
5. Revisar:
   - `retrieval_backend`;
   - `embedding_model`;
   - `memory_record_ids`;
   - `memory_record_uses`;
   - `memory_usage_summary`;
   - benchmark de memoria.
6. Documentar M4.5.

## Horizonte despues de M4.5

Una vez memoria con Qdrant + Qwen este validada:

1. Retomar `run_to_failure_degradation` como bloque principal.
2. Llevar ese perfil al maximo:
   - histeresis y alertas sostenidas;
   - RUL experimental con mucho cuidado metodologico;
   - autoencoder;
   - comparacion de modelos temporales;
   - vistas de activos/motores;
   - monitorizacion operacional mas rica;
   - decision agentica con debate y memoria.
3. Despues, abrir una fase de aplicacion web:
   - frontend mas limpio;
   - UX mas industrial;
   - vistas mas originales;
   - paneles mas funcionales;
   - elementos visuales que destaquen el TFM frente a una app generica.

## Frase guia

La memoria ya no es solo un indice local: ahora tiene observabilidad, gobierno,
benchmark y Qdrant operativo. El siguiente salto es demostrar que Qwen usa esa
memoria en decisiones reales, y despues volver al perfil run-to-failure para
convertirlo en una experiencia industrial completa.
