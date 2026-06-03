# Fase 8 - Hito 8.3 modeler como estratega run-to-failure

Fecha: 2026-06-03.

## Objetivo

Convertir al agente `modeler` en estratega del perfil
`run_to_failure_degradation`. A partir de este hito, el modelador no solo elige
un `model_name` y unos hiperparametros: debe declarar herramientas usadas,
evidencia temporal, objetivos de optimizacion y politica de alerta.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Hacer que el modeler decida una estrategia temporal run-to-failure citando
herramientas, evidencia, objetivos y alternativas de modelo.
```

Inventario revisado:

- `codigo/app/agents/modeler.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/services/agent_tools.py`;
- `codigo/tests/test_modeler_agent.py`;
- `codigo/tests/test_agent_decisions_schema.py`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- `codigo/docs/73_fase8_hito2_herramientas_temporales_agenticas.md`.

Decision:

```text
extend
```

Motivo: `ModelingDecisionStrategy` ya representaba la hipotesis, evidencia y
riesgos de la decision del modelador. Crear un contrato paralelo
`RunToFailureModelingStrategy` en este momento habria duplicado responsabilidad.
Se extiende el contrato existente con campos opcionales compatibles.

## Cambios de contrato

`ModelingDecisionStrategy` incorpora:

- `tool_names`: herramientas que el agente declara haber usado o elegido como
  evidencia;
- `optimization_targets`: objetivos que guian la estrategia;
- `alert_policy`: politica textual de alerta, persistencia y umbral auxiliar.

Los campos son opcionales por compatibilidad, pero el `modeler` los exige cuando
el perfil es `run_to_failure_degradation`.

## Reglas nuevas para run-to-failure

En `run_to_failure_degradation`, una `ModelingDecision` valida debe cumplir:

- no usar `threshold_calibration` como estrategia principal;
- incluir `temporal_health_lookup`;
- incluir `degradation_metrics_lookup`;
- citar `tool:temporal_health_lookup`;
- citar `tool:degradation_metrics_lookup`;
- citar al menos una evidencia temporal o metrica de degradacion;
- incluir estos objetivos:
  - `detected_before_failure_rate`;
  - `mean_lead_time_to_failure`;
  - `mean_false_alarm_rate_nominal`;
  - `mean_score_trend_spearman`;
- declarar una `alert_policy` que distinga pico aislado y aviso sostenido;
- mantener F1 como metrica auxiliar, nunca como objetivo principal.

## Fallback temporal enriquecido

El fallback determinista para este perfil sigue escogiendo
`pca_reconstruction_error`, pero ahora declara:

- herramientas temporales;
- refs citables;
- objetivos run-to-failure;
- politica de alerta sostenida;
- alternativas comparables con `isolation_forest` y `one_class_svm`.

Asi, incluso si Qwen falla, la run conserva trazabilidad y se etiqueta como
fallback sin perder el marco metodologico.

## Prompt LLM

El prompt del `modeler` ahora incluye un catalogo compacto de herramientas
disponibles:

- `evidence_lookup`;
- `temporal_health_lookup`;
- `degradation_metrics_lookup`;
- `threshold_analysis`.

Para el perfil temporal, el prompt exige que Qwen rellene `tool_names`,
`evidence_refs`, `optimization_targets` y `alert_policy`.

## Verificacion

Tests ejecutados durante el hito:

```bash
python -m unittest codigo.tests.test_modeler_agent
python -m unittest codigo.tests.test_agent_decisions_schema codigo.tests.test_modeler_agent codigo.tests.test_agent_tools
```

Resultados: OK.

## Continuacion

El Hito 8.4 queda implementado en
`75_fase8_hito4_evaluador_operacional_debate_temporal.md`. Con el `modeler`
declarando estrategia, herramientas y objetivos, el `evaluator` ya audita si la
decision es defendible operacionalmente y valida guardarrails temporales.
