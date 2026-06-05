# Fase 9 - Hito 9.2: politica temporal y evaluacion por onset confirmado

Fecha: 2026-06-04.

## Objetivo

Elevar la evaluacion del perfil:

```text
run_to_failure_degradation
```

para que no dependa solo del primer pico de alerta. El criterio principal pasa
a distinguir:

- primer pico;
- aviso sostenido;
- onset de degradacion confirmado;
- lead time persistente;
- falsas alarmas nominales;
- tendencia del score.

Las metricas binarias y las metricas temporales anteriores se conservan por
compatibilidad y diagnostico, pero las nuevas runs deben juzgarse por onset
confirmado cuando la metrica esta disponible.

## Respuesta metodologica

Las metricas que ya existian eran utiles, pero no suficientes para este perfil.

Se mantienen:

- `detected_before_failure_rate`;
- `mean_lead_time_to_failure`;
- `mean_false_alarm_rate_nominal`;
- `mean_score_trend_spearman`;
- `missed_runs`.

Problema detectado:

```text
Un unico pico temprano puede producir un lead time excelente sin representar
degradacion sostenida.
```

Por eso se anade una segunda lectura mas robusta:

- `confirmed_degradation_before_failure_rate`;
- `mean_persistent_lead_time_to_failure`;
- `missed_confirmed_degradation_runs`;
- `mean_isolated_alert_points`;
- `mean_alert_episodes`;
- `mean_longest_alert_streak`.

La evaluacion queda asi:

```text
primer pico = evidencia diagnostica
onset confirmado = evidencia principal de degradacion operacional
```

## Reutilizacion aplicada

Capacidad buscada:

```text
Versionar la politica temporal de salud y usarla de forma consistente en
evaluacion, visualizacion, comparacion de runs y herramientas agenticas.
```

Inventario previo:

- `codigo/app/executors/evaluation.py` ya era propietario de metricas
  temporales.
- `codigo/app/services/run_visualization.py` ya calculaba `health_state`,
  avisos persistentes, episodios y rachas para UI/herramientas.
- `codigo/app/schemas/api_visualization.py` ya exponia contratos de serie
  temporal.
- `codigo/app/services/agent_tools.py` ya daba a los agentes evidencia temporal
  read-only.
- `codigo/app/agents/evaluator.py` ya aprobaba runs run-to-failure por
  metricas temporales y no por F1.
- `codigo/app/services/run_registry.py` ya comparaba runs por metricas
  `run_to_failure_degradation`.

Decision:

```text
extend
```

Motivo: habia propietarios claros. Crear un evaluador paralelo o recalcular en
frontend habria duplicado responsabilidades.

Se crea una pieza nueva porque faltaba un propietario compartido de politica:

- `codigo/app/schemas/temporal_health.py`;
- `codigo/app/services/temporal_health_policy.py`.

Frontera de responsabilidad:

- el schema define contratos versionados;
- el service traduce score/umbral/prediccion a salud temporal y rachas;
- evaluacion y visualizacion consumen la misma politica.

## Politica versionada

Se introduce:

```text
temporal_health_policy_v1
alert_persistence_v1
```

Valores iniciales:

- `persistent_alert_min_windows = 3`;
- `nominal_relative_life_limit = 0.40`;
- `early_relative_life_limit = 0.33`;
- `late_relative_life_limit = 0.67`;
- `watch_risk_threshold = 40`;
- `warning_risk_threshold = 70`;
- `critical_risk_threshold = 95`;
- `critical_relative_life_threshold = 0.90`.

La politica devuelve:

- `score_ratio`;
- `risk_index`;
- `health_index`;
- `health_state`;
- `state_reason`;
- `health_policy_id`;
- `alert_policy_id`.

## Cambios implementados

### Evaluacion

`evaluation.py` ahora persiste en `degradation_metrics`:

- `health_policy_id`;
- `alert_policy_id`;
- `persistent_alert_min_windows`;
- `confirmed_degradation_runs`;
- `missed_confirmed_degradation_runs`;
- `confirmed_degradation_before_failure_rate`;
- `median_persistent_lead_time_to_failure`;
- `mean_persistent_lead_time_to_failure`;
- `mean_isolated_alert_points`;
- `mean_alert_episodes`;
- `mean_longest_alert_streak`.

Cada `run_metrics` incluye:

- `first_persistent_alert_time`;
- `first_persistent_alert_relative_life`;
- `time_to_confirmed_degradation`;
- `persistent_lead_time_to_failure`;
- `confirmed_degradation_before_failure`;
- `missed_confirmed_degradation`;
- episodios, picos aislados y racha maxima.

### Visualizacion

`TemporalRunSeries` expone:

- `onset_confirmed`;
- `onset_confirmed_x`;
- `onset_confirmed_time`;
- `onset_confirmed_time_to_failure_seconds`;
- `health_policy_id`;
- `alert_policy_id`.

`TemporalSeriesPoint` expone tambien los ids de politica usados para calcular
su estado.

### Agentes

Las herramientas read-only incorporan nuevas refs citables:

- `temporal:health_policy`;
- `temporal:alert_policy`;
- `temporal:onset_confirmed`;
- `metric:confirmed_degradation_before_failure_rate`;
- `metric:mean_persistent_lead_time_to_failure`.

`degradation_metrics_lookup` devuelve como metricas primarias el onset
confirmado y el lead time persistente.

El evaluador determinista usa:

1. `degradation_confirmed_degradation_before_failure_rate` si existe;
2. `degradation_detected_before_failure_rate` como fallback historico.

Lo mismo aplica a lead time:

1. `degradation_mean_persistent_lead_time_to_failure` si existe;
2. `degradation_mean_lead_time_to_failure` como fallback historico.

### Comparacion y tablas

`run_registry.py` compara nuevas metricas temporales:

- mayor es mejor:
  - `degradation_confirmed_degradation_before_failure_rate`;
  - `degradation_mean_persistent_lead_time_to_failure`;
  - `degradation_mean_longest_alert_streak`;
- menor es mejor:
  - `degradation_missed_confirmed_degradation_runs`;
  - `degradation_mean_isolated_alert_points`;
  - `degradation_mean_alert_episodes`.

La tabla de la suite run-to-failure pasa a mostrar:

- `Onset confirmado`;
- `Lead persistente`;
- `FAR nominal`;
- `Tendencia`;
- `Onsets perdidos`;
- `F1 aux`;
- `FPR aux`.

## Alcance no incluido todavia

No se implementa aun una herramienta nueva `hysteresis_policy_simulator`.

Motivo: el cuello de botella inmediato era cambiar la evaluacion principal y
unificar la politica entre evaluacion/UI/agentes. El simulador queda como
extension natural si se quieren comparar politicas alternativas sin reentrenar.

Tampoco se implementa:

- RUL;
- suavizado avanzado de Health Index;
- autoencoder PyTorch.

## Verificacion

Tests focales:

```bash
python -m unittest \
  codigo.tests.test_evaluation_executor \
  codigo.tests.test_run_visualization \
  codigo.tests.test_agent_tools \
  codigo.tests.test_evaluator_agent \
  codigo.tests.test_run_registry
```

Resultado:

```text
Ran 48 tests in 0.223s
OK
```

Suite completa:

```bash
python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 340 tests in 1.103s
OK
```

Smoke operativo:

```bash
python -m codigo.scripts.run_run_to_failure_model_suite \
  --plan-id fase9-hito2-rtf-policy-smoke-001 \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen
```

Artefactos:

- `codigo/experiments/run_to_failure/fase9-hito2-rtf-policy-smoke-001/experiment_plan.json`;
- `codigo/experiments/run_to_failure/fase9-hito2-rtf-policy-smoke-001/comparison.json`;
- `codigo/experiments/run_to_failure/fase9-hito2-rtf-policy-smoke-001/results_table.md`.

Resultado sintetico:

- los tres modelos alcanzan `Onset confirmado = 1.0000`;
- el `Lead persistente` queda en `601.0240`, frente al primer pico previo mas
  optimista;
- `FAR nominal = 0.6667` y `FPR aux = 1.0000`, por lo que ninguna run queda
  aprobada;
- PCA mantiene la mejor tendencia Spearman (`0.9167`), pero sigue no defendible
  operacionalmente por falsas alarmas.

## Estado

Hito 9.2 implementado en su nucleo de evaluacion y politica compartida.

El siguiente paso recomendado es Hito 9.3: Health Indicator avanzado, usando la
politica versionada como base para suavizado, monotonicidad, robustez y
explicacion de salud.
