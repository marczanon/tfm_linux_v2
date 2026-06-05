# Fase 9 - Hito 9.5: readiness para modelos temporales avanzados

Fecha: 2026-06-05.

## Objetivo

Anadir una herramienta read-only para que los agentes puedan decidir si procede
subir la complejidad hacia:

- `autoencoder_dense`;
- LSTM/autoencoder secuencial posterior;
- RUL experimental.

La herramienta no entrena modelos, no estima RUL y no reemplaza al LLM. Su
funcion es dar evidencia estructurada para que el `modeler` y el `evaluator`
puedan razonar con mas criterio.

## Principio metodologico

Este hito mantiene el protagonismo agentico:

```text
La herramienta observa y audita readiness.
El agente decide que hacer con esa evidencia.
El ejecutor determinista entrenara solo cuando exista una configuracion valida.
```

Qwen puede elegir entre PCA, Isolation Forest, One-Class SVM y, en el siguiente
hito, autoencoder. Pero si quiere proponer modelos avanzados debe citar
readiness y justificar el tradeoff.

## Reutilizacion aplicada

Capacidad buscada:

```text
Evaluar si una run temporal tiene datos suficientes para autoencoder/RUL sin
crear un runner paralelo ni permitir codigo arbitrario generado por agentes.
```

Inventario previo:

- `codigo/app/services/agent_tools.py` ya es el catalogo canonico de
  herramientas read-only.
- `codigo/app/agents/modeler.py` ya decide familia de modelo dentro de
  contratos cerrados.
- `codigo/app/agents/evaluator.py` ya audita metricas temporales y
  guardarrails.
- `codigo/app/services/run_visualization.py` y `evaluation.py` ya consumen
  predicciones/series temporales.
- `codigo/app/schemas/reasoning.py` ya declara nombres de herramientas
  permitidas.

Decision:

```text
extend
```

Motivo: readiness es una herramienta de observacion para agentes, no un nuevo
ejecutor ni una nueva API. La frontera correcta es `agent_tools.py` con un
servicio determinista auxiliar.

## Contrato

Se introduce:

- `codigo/app/schemas/temporal_readiness.py`;
- `codigo/app/services/temporal_model_readiness.py`;
- herramienta `temporal_model_readiness_assessor`.

Politica:

```text
temporal_model_readiness_v1
```

Campos principales:

- `autoencoder_ready`;
- `rul_ready`;
- `readiness_level`;
- `blocked_reasons`;
- `caution_reasons`;
- `recommended_next_experiment`;
- `estimated_cost_level`;
- `n_train_nominal_windows`;
- `n_feature_columns`;
- `n_runs`;
- `temporal_continuity_ok`;
- `time_to_failure_coverage`;
- `split_quality_ok`;
- `leakage_risk`;
- `finite_feature_ratio`.

## Criterios iniciales

Autoencoder denso requiere:

- features tabulares disponibles;
- al menos 3 columnas numericas;
- al menos 30 ventanas nominales en `train`;
- split `train` y `validation` o `test`;
- ratio de features finitas >= 0.95;
- bajo riesgo de leakage por degradacion en train.

RUL experimental requiere ademas:

- al menos 3 trayectorias/runs;
- cobertura suficiente de `time_to_failure_seconds`;
- continuidad temporal verificable.

## Integracion agentica

La herramienta produce refs citables:

- `tool:temporal_model_readiness_assessor`;
- `readiness:temporal_model_readiness`;
- `readiness:autoencoder_ready`;
- `readiness:autoencoder_blocked`;
- `readiness:rul_ready`;
- `readiness:rul_blocked`;
- `readiness:blocker:*`;
- `readiness:caution:*`;
- `readiness:leakage:*`;
- `readiness:cost:*`.

`modeler.py` queda preparado con una regla:

```text
Si en el futuro se propone autoencoder_dense o LSTM, debe citar
temporal_model_readiness_assessor y refs readiness:*.
```

El fallback determinista sigue usando PCA como baseline, pero ahora incluye la
herramienta de readiness entre sus instrumentos metodologicos.

`evaluator.py` incorpora readiness como evidencia posible para bloquear
conclusiones de autoencoder/RUL si se ignora la herramienta.

## Alcance no incluido

No se implementa todavia PyTorch ni entrenamiento de autoencoder.

No se implementa RUL.

No se cambia la politica de aprobacion temporal de Hito 9.2. Readiness es una
condicion metodologica para modelos avanzados, no una metrica de aprobacion de
runs PCA/IF/OCSVM.

## Verificacion

Tests focales:

```bash
python -m unittest \
  codigo.tests.test_agent_tools \
  codigo.tests.test_modeler_agent \
  codigo.tests.test_evaluator_agent
```

Resultado:

```text
Ran 50 tests in 0.072s
OK
```

`test_agent_tools` cubre:

- catalogo read-only;
- readiness bloqueado sin features;
- readiness con autoencoder permitido pero RUL bloqueado por una sola
  trayectoria.

## Estado

Hito 9.5 implementado como herramienta metodologica previa al autoencoder.

El siguiente paso natural es Hito 9.4: implementar `autoencoder_dense` en
PyTorch dentro del ejecutor determinista, usando esta herramienta como
precondicion agentica.
