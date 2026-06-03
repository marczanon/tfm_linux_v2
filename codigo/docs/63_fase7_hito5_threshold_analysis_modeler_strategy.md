# Fase 7 - Hito 5.2: threshold_analysis y estrategia del modelador

Fecha: 2026-06-01.

## Objetivo

Anadir una segunda herramienta read-only al catalogo agentico,
`threshold_analysis`, y ampliar la decision del `modeler` para que declare una
hipotesis de modelado explicita. El objetivo es dar mas evidencia cuantitativa
al agente sin empujarlo a resolver todo moviendo `threshold_quantile`.

## Motivacion

El umbral de anomalia es importante, pero puede volverse una palanca demasiado
dominante. En ejecuciones previas ya se observo que insistir solo en el umbral
puede producir mejoras parciales o sobrecorrecciones. Por eso la herramienta se
disena como diagnostico, no como recomendador.

La regla metodologica queda:

```text
threshold_analysis observa sensibilidad; modeler formula hipotesis y decide.
```

## Inventario previo anti-duplicacion

Piezas revisadas:

- `codigo/app/services/agent_tools.py`;
- `codigo/app/services/iteration_analysis.py`;
- `codigo/app/agents/modeler.py`;
- `codigo/app/executors/modeling.py`;
- `codigo/app/executors/evaluation.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/tests/test_agent_tools.py`;
- `codigo/tests/test_modeler_agent.py`;
- `codigo/tests/test_agent_decisions_schema.py`;
- documentacion historica de Fase 3 y Fase 4 sobre `threshold_quantile`.

Decision:

```text
extend
```

Motivo: ya existe un catalogo de herramientas y ya existen analisis de fallo
para reintentos. La nueva pieza se limita a un diagnostico reusable desde el
catalogo y no crea otro runner ni otro evaluador.

## Herramienta threshold_analysis

La herramienta lee el artefacto `predictions` registrado en el estado y calcula:

- umbral actual, si aparece en `predictions.csv`;
- umbrales candidatos por cuantiles de score;
- precision, recall, F1 y FPR por candidato cuando hay etiquetas;
- matriz de confusion por candidato;
- resumen de scores por target;
- ventanas mas cercanas al umbral actual;
- guardarrail textual indicando que la herramienta no selecciona umbral.

Argumentos soportados:

```text
primary_split
threshold_source_split
quantiles
near_threshold_limit
```

La observacion devuelve referencias citables como:

```text
artifact:model_predictions
metric:recall
tool:threshold_analysis
```

`threshold_analysis` solo esta disponible para `modeler` y `evaluator`.

## Ampliacion de ModelingDecision

Se anade `ModelingDecisionStrategy` con:

- `strategy_type`;
- `hypothesis`;
- `evidence_refs`;
- `risk_notes`.

Tipos de estrategia:

```text
model_family_selection
threshold_calibration
feature_model_fit
data_split_risk
baseline_conservation
needs_more_evidence
```

El contrato mantiene compatibilidad: si una decision antigua no declara
estrategia, se usa `baseline_conservation` por defecto.

## Guardarrail contra tunnel vision del umbral

Si el modelador declara `strategy_type = threshold_calibration`, su
`ModelingDecision` debe incluir al menos una `comparison_candidate` de otra
familia de modelo soportada. No se obliga a elegir esa alternativa; solo se
exige que el agente deje evidencia de que no redujo la deliberacion al umbral.

Esto no hardcodea la decision final. El agente puede seguir eligiendo
`isolation_forest`, `pca_reconstruction_error` o conservar el baseline, pero
debe razonar sobre la hipotesis que esta siguiendo.

## Fronteras

Esta version no:

- conecta automaticamente la herramienta al flujo del `modeler`;
- recalcula ni sobrescribe predicciones;
- cambia metricas oficiales de la run;
- recomienda un `threshold_quantile` cerrado;
- elimina la memoria RAG intrinseca de los agentes.

## Validacion

Validaciones ejecutadas:

```text
python -m py_compile codigo/app/services/agent_tools.py codigo/app/schemas/reasoning.py codigo/app/schemas/agent_decisions.py codigo/app/agents/modeler.py codigo/app/graph/pipeline.py
python -m unittest codigo.tests.test_agent_tools codigo.tests.test_agent_decisions_schema codigo.tests.test_modeler_agent
```

Resultado: la herramienta devuelve sensibilidad reproducible y el contrato del
modelador rechaza decisiones de calibracion de umbral sin comparacion de familia.
