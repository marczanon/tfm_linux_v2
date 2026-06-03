# Fase 8 - Hito 8.6 post-mortem y memoria temporal

Fecha: 2026-06-03.

## Objetivo

Adaptar el post-mortem y la memoria agentica existentes al perfil
`run_to_failure_degradation`, de forma que las decisiones sobre degradacion
temporal dejen aprendizaje reutilizable para futuras runs.

El objetivo no es crear otra memoria paralela, sino hacer que los episodios ya
existentes capturen:

- estrategia temporal del `modeler`;
- politica de alerta;
- evidencia y herramientas temporales;
- metricas de degradacion;
- guardarrails del `evaluator`;
- cautelas sobre etiquetas proxy, picos aislados y RUL no estimado.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Convertir decisiones run-to-failure en episodios/candidatos de memoria
reutilizables por agentes, sin duplicar el sistema de post-mortem existente.
```

Inventario revisado:

- `codigo/app/schemas/reasoning.py`;
- `codigo/app/services/decision_memory.py`;
- `codigo/app/services/vector_memory.py`;
- `codigo/app/services/reasoning_memory_index.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/tests/test_decision_memory.py`;
- `codigo/tests/test_graph_pipeline.py`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- `codigo/docs/76_fase8_hito5_recomendacion_agentica_frontend.md`.

Decision:

```text
extend
```

Motivo: `DecisionEpisode` y `MemoryCandidate` ya son los contratos canonicos
para post-mortem operativo y memoria reutilizable. Crear un
`RunToFailurePostMortem` separado duplicaria responsabilidad y obligaria a otro
indexador. El hito se implementa enriqueciendo esos contratos mediante el
servicio canonico `decision_memory.py`.

## Cambios implementados

### Episodio del modelador

Se anaden:

- `build_modeling_decision_episode`;
- `build_modeling_memory_candidate`.

El episodio del `modeler` registra:

- modelo elegido;
- `decision_strategy`;
- hipotesis;
- herramientas usadas;
- referencias de evidencia;
- objetivos de optimizacion;
- politica de alerta;
- alternativas comparadas;
- riesgos de reutilizar la politica fuera de contexto.

Para `run_to_failure_degradation`, el episodio incorpora lecciones como:

- `run_to_failure_modeling_requires_temporal_metrics`;
- `f1_is_auxiliary_for_temporal_profile`;
- `temporal_alert_policy_must_be_explicit`;
- `score_trend_over_binary_f1`.

### Memoria temporal del evaluador

La memoria del `evaluator` conserva ahora metricas temporales en
`after_metrics` cuando aparecen en `MetricsReport.extra`, por ejemplo:

- `degradation_detected_before_failure_rate`;
- `degradation_mean_lead_time_to_failure`;
- `degradation_mean_false_alarm_rate_nominal`;
- `degradation_mean_score_trend_spearman`;
- `degradation_missed_runs`.

Una aprobacion temporal con limitaciones se considera `partially_supported`,
no `supported` puro. Asi, una run defendible con cautelas queda indexada como
caso de frontera y no como receta positiva directa.

### Contenido indexable

`memory_candidate_from_decision_episode` ya era el conversor canonico. Se
mantiene, pero el contenido textual que alimenta la memoria vectorial incluye
ahora metricas before/after y los tags incluyen tradeoffs observados. Esto
permite recuperar recuerdos por consultas sobre:

- `rul_not_estimated`;
- `mean_lead_time_to_failure`;
- `false_alarm_rate_nominal`;
- `isolated_spike_not_failure`;
- `sustained_alert_required`;
- `score_trend_over_binary_f1`.

### Grafo

Cuando `PipelineMemoryConfig.generate_decision_memory` esta activo, el grafo ya
generaba memoria de `structurer` y `evaluator`. Ahora tambien genera:

- `modeler_decision_episode`;
- `modeler_decision_episode_report`;
- `modeler_memory_candidate`;
- `modeler_memory_candidate_report`.

Esto ocurre despues del ejecutor de modelado, cuando existen artefactos de
modelo y predicciones. Las runs sin `memory_config` no cambian comportamiento.

## Alcance y limites

Este hito deja la memoria temporal generada, persistida e indexable. El
`evaluator` ya dispone de recuperacion RAG normal en el grafo y el `modeler`
mantiene recuperacion para reintentos. La recuperacion RAG del `modeler` en la
primera decision de modelado queda como posible extension siguiente, porque
requiere ampliar `ModelingDecision` con declaracion normal de uso de memoria.

## Verificacion

Tests ejecutados durante el hito:

```bash
python -m unittest codigo.tests.test_decision_memory codigo.tests.test_graph_pipeline
python -m unittest codigo.tests.test_decision_memory codigo.tests.test_graph_pipeline codigo.tests.test_reasoning_memory_index codigo.tests.test_vector_memory_store codigo.tests.test_transversal_memory_audit
python -m unittest discover codigo/tests
npm run build
git diff --check
```

Resultados: OK.

## Siguiente paso logico

El siguiente paso natural es cerrar el ciclo de recuperacion para el
`modeler`: permitir que la decision inicial de modelado, no solo los reintentos,
recupere memoria temporal indexada y declare su uso mediante contrato
estructurado. Si se prefiere avanzar hacia capacidad analitica, el siguiente
bloque puede empezar con histeresis/RUL experimental usando esta memoria como
contexto de decision.
