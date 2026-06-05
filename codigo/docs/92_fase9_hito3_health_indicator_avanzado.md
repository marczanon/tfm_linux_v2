# Fase 9 - Hito 9.3: Health Indicator avanzado

Fecha: 2026-06-04.

## Objetivo

Construir un Health Indicator mas defendible para el perfil:

```text
run_to_failure_degradation
```

El punto de partida era:

```text
health_index = 100 - risk_index
```

Eso era util para visualizacion, pero demasiado puntual para una lectura PHM.
Este hito anade una capa temporal causal, versionada y citable por agentes.

## Reutilizacion aplicada

Capacidad buscada:

```text
Derivar Health Index bruto/suavizado y metricas de calidad temporal desde las
predicciones run-to-failure, reutilizando la politica temporal versionada.
```

Inventario previo:

- `codigo/app/services/temporal_health_policy.py` ya era la pieza compartida de
  salud temporal tras Hito 9.2.
- `codigo/app/executors/evaluation.py` ya calculaba metricas temporales.
- `codigo/app/services/run_visualization.py` ya exponia `health_index`,
  `risk_index`, `health_state` y eventos temporales.
- `codigo/app/services/agent_tools.py` ya ofrecia herramientas read-only para
  agentes.
- `codigo/app/services/degradation_diagnostics.py` existe, pero es un
  diagnostico no supervisado auxiliar sobre features; no es el propietario del
  Health Index operacional del pipeline.

Decision:

```text
extend
```

Motivo: el Health Indicator operacional debe salir del mismo contrato temporal
que usan evaluacion, visualizacion y agentes. No se crea un flujo paralelo ni
se recalcula en frontend.

## Politica versionada

Se introduce:

```text
health_indicator_policy_v1
```

Contrato:

- `smoothing_window = 3`;
- `trend_window = 3`;
- `min_drop_for_degradation = 5.0`;
- `nominal_volatility_limit = 15.0`.

El suavizado es causal/trailing:

```text
HI_suavizado(t) = media de HI bruto en [t - window + 1, t]
```

No mira al futuro, por lo que evita leakage temporal y sigue siendo compatible
con uso operacional o replay historico.

## Metricas nuevas

Por punto temporal:

- `health_index_raw`;
- `health_index_smoothed`;
- `risk_index_smoothed`;
- `health_trend`;
- `dominant_evidence`;
- `health_indicator_policy_id`.

Por trayectoria:

- `initial_health_index`;
- `final_health_index`;
- `health_index_drop`;
- `health_index_drop_ratio`;
- `health_slope`;
- `health_trend_spearman`;
- `health_degradation_trend_strength`;
- `health_monotonicity`;
- `health_robustness`;
- `health_nominal_volatility`;
- `health_indicator_score`;
- `health_dominant_evidence`;
- `health_indicator_status`.

Por conjunto de trayectorias:

- `health_trendability`;
- `health_prognosability`.

Estas dos ultimas quedan `null` cuando solo hay una trayectoria, que es el caso
normal de los smokes pequeños.

## Interpretacion

La lectura propuesta es:

```text
score de anomalia -> riesgo puntual
Health Index bruto -> salud puntual invertida
Health Index suavizado -> trayectoria causal de salud
metricas HI -> calidad PHM de esa trayectoria
estado operacional -> interpretacion humana/agentica
```

Se evita afirmar causalidad fisica directa. Por ahora `dominant_evidence`
describe evidencias del detector:

- `score_above_threshold`;
- `model_alert`;
- `health_decline`;
- `late_life_context`;
- `score_near_threshold`;
- `stable_health`.

La explicacion por features fisicas concretas queda como extension posterior,
idealmente cuando se conecte el HI a evidencias de RMS, energia, impulsividad o
reconstruccion del autoencoder.

## Cambios implementados

### Contratos y servicio

En `codigo/app/schemas/temporal_health.py`:

- `TemporalHealthIndicatorPolicy`;
- `DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY`.

En `codigo/app/services/temporal_health_policy.py`:

- `temporal_health_indicator_series(...)`;
- `health_indicator_metrics(...)`;
- `temporal_health_population_metrics(...)`;
- suavizado causal;
- monotonicidad decreciente;
- robustez;
- volatilidad nominal;
- Spearman y slope de HI;
- trendability/prognosability multi-run.

### Evaluacion

`evaluation.py` persiste las metricas HI dentro de `degradation_metrics` y de
cada `run_metrics`.

Se anade al informe Markdown:

- politica HI;
- caida media de Health Index;
- monotonicidad;
- robustez;
- volatilidad nominal.

### Visualizacion

`TemporalSeriesPoint` ahora expone HI bruto/suavizado y evidencia dominante.

`TemporalRunSeries` ahora expone:

- HI actual suavizado;
- tendencia local;
- caida inicio-final;
- monotonicidad;
- robustez;
- volatilidad nominal;
- score compuesto;
- evidencia dominante.

### Agentes y memoria

Las herramientas read-only exponen refs nuevas:

- `health:indicator_available`;
- `health:monotonicity`;
- `health:robustness`;
- `health:onset_confirmed`;
- `health:dominant_evidence`.

`degradation_metrics_lookup` incluye como primarias:

- `mean_health_index_drop`;
- `mean_health_monotonicity`;
- `mean_health_robustness`.

El evaluador y el redactor mencionan Health Indicator como evidencia auxiliar,
sin sustituir todavia los criterios de aprobacion de Hito 9.2.

### Comparacion de runs

`run_registry.py` compara:

- `degradation_mean_health_index_drop` como mayor es mejor;
- `degradation_mean_health_monotonicity` como mayor es mejor;
- `degradation_mean_health_robustness` como mayor es mejor;
- `degradation_mean_health_nominal_volatility` como menor es mejor;
- `degradation_mean_health_indicator_score` como mayor es mejor.

La tabla de suite run-to-failure anade:

- `HI drop`;
- `HI mono`.

## Verificacion

Tests focales:

```bash
python -m unittest \
  codigo.tests.test_evaluation_executor \
  codigo.tests.test_run_visualization \
  codigo.tests.test_agent_tools \
  codigo.tests.test_evaluator_agent \
  codigo.tests.test_run_registry \
  codigo.tests.test_experiment_protocol
```

Resultado:

```text
Ran 59 tests in 0.292s
OK
```

Suite completa:

```bash
python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 340 tests in 1.180s
OK
```

Smoke operativo:

```bash
python -m codigo.scripts.run_run_to_failure_model_suite \
  --plan-id fase9-hito3-hi-smoke-001 \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen
```

Artefactos:

- `codigo/experiments/run_to_failure/fase9-hito3-hi-smoke-001/experiment_plan.json`;
- `codigo/experiments/run_to_failure/fase9-hito3-hi-smoke-001/comparison.json`;
- `codigo/experiments/run_to_failure/fase9-hito3-hi-smoke-001/results_table.md`.

Resultado sintetico:

- las tres runs mantienen `Onset confirmado = 1.0000`;
- ninguna queda aprobada por `FAR nominal = 0.6667` y `FPR aux = 1.0000`;
- PCA obtiene mejor `HI drop = 60.0145`, `HI mono = 1.0000` y score HI
  compuesto `0.8698`;
- Isolation Forest obtiene mejor robustez HI (`0.9862`) y menor volatilidad
  nominal HI (`2.6439`);
- One-Class SVM queda intermedio en caida HI (`37.7778`) y tendencia de score.

Lectura:

```text
PCA parece mas informativo para degradacion visible, Isolation Forest mas
estable en tramo nominal, pero la politica operacional rechaza los tres por
exceso de falsas alarmas.
```

## Estado

Hito 9.3 implementado en su nucleo determinista y agentico.

El siguiente paso recomendado sigue siendo Hito 9.5, readiness para modelos
temporales avanzados, antes de implementar el autoencoder PyTorch completo. Asi
Qwen tendra una herramienta para justificar si procede o no usar un modelo mas
costoso.
