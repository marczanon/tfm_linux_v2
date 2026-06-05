# Fase 9 - Hito 9.1: suite canonica agentica run-to-failure

Fecha: 2026-06-04.

## Objetivo

Crear la base reproducible de una suite comparativa para el perfil:

```text
run_to_failure_degradation
```

El objetivo de este primer paso no es lanzar todavia una run larga con Qwen y
Qdrant, sino dejar preparada la pieza canonica que permite materializar varias
familias de modelo sobre el mismo protocolo temporal sin crear runners
paralelos.

## Reutilizacion aplicada

Capacidad buscada:

```text
Preparar una suite canonica run-to-failure con PCA, Isolation Forest y
One-Class SVM, reutilizando el protocolo experimental y el runner comun.
```

Inventario previo:

- `codigo/app/services/experiment_protocol.py` ya contenia planes
  experimentales locales para CWRU.
- `codigo/app/services/pipeline_runner.py` ya era el runner comun
  multi-dataset y aplicaba `nasa_ims_temporal_v1`.
- `codigo/app/executors/modeling.py` ya soportaba:
  - `pca_reconstruction_error`;
  - `isolation_forest`;
  - `one_class_svm`.
- `codigo/app/services/run_registry.py` ya comparaba runs con metricas
  `run_to_failure_degradation`.
- `codigo/app/agents/modeler.py` ya declaraba estrategia temporal, herramientas
  y objetivos run-to-failure.

Decision:

```text
extend
```

Motivo: crear un script o runner especifico de NASA IMS duplicaria
responsabilidad. La frontera correcta es extender `experiment_protocol.py` para
que pueda describir y materializar suites run-to-failure usando el runner comun.

## Cambios implementados

### Plan experimental run-to-failure

Se amplia `ExperimentPlan` para admitir:

- `dataset="nasa_ims_bearing"`;
- `adapter_id`;
- `dataset_policy_id`;
- `supervision_profile`.

Se añade:

- `DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR`;
- `DEFAULT_RUN_TO_FAILURE_PLAN_ID`;
- `DEFAULT_RUN_TO_FAILURE_POLICY_ID`;
- `default_run_to_failure_model_suite_plan(...)`.

La suite canonica inicial contenia tres experimentos:

1. `pca_reconstruction_error`;
2. `isolation_forest`;
3. `one_class_svm`.

Los tres usan las configuraciones por defecto ya soportadas por el ejecutor de
modelado y se comparan por metricas temporales.

Nota posterior al Hito 9.4: la suite canonica se amplia con
`autoencoder_dense` cuando PyTorch esta instalado, manteniendo el mismo contrato
de `predictions.csv`.

### Suite desde decision del modeler

Se añade:

- `run_to_failure_model_experiment_plan_from_decision(...)`.

Esta funcion toma una `ModelingDecision` del agente `modeler` y materializa:

- la configuracion elegida;
- sus `comparison_candidates`;
- un `ExperimentPlan` con `supervision_profile=run_to_failure_degradation`.

La funcion reutiliza el mismo helper que ahora usa
`cwru_model_experiment_plan_from_decision(...)`, evitando dos implementaciones
del mismo patron.

### Ejecucion con runner comun

Se añade:

- `run_run_to_failure_experiment_plan(...)`.
- `codigo/scripts/run_run_to_failure_model_suite.py`.

La ejecucion real usa:

- `PipelineRunRequest`;
- `run_dataset_pipeline(...)`;
- `adapter_id=nasa_ims_bearing`;
- `dataset_policy_id=nasa_ims_temporal_v1`;
- agentes del grafo normal, pero con el `modeler` envuelto para materializar la
  configuracion concreta de cada experimento.

El `ModelingDecision` materializado conserva estrategia temporal con:

- `temporal_health_lookup`;
- `degradation_metrics_lookup`;
- objetivos:
  - `detected_before_failure_rate`;
  - `mean_lead_time_to_failure`;
  - `mean_false_alarm_rate_nominal`;
  - `mean_score_trend_spearman`;
- politica de alerta que distingue pico aislado, aviso sostenido, falsas
  alarmas nominales y tendencia.

### Tabla de resultados temporal

`_results_table_markdown(...)` detecta planes `nasa_ims_bearing` o
comparaciones con `degradation_metrics` y genera una tabla centrada en:

- onset confirmado antes de fallo;
- lead time persistente;
- falsa alarma nominal;
- tendencia;
- onsets perdidos;
- F1/FPR solo como auxiliares.

Nota posterior al Hito 9.2: la tabla original de este hito usaba primer aviso y
lead time bruto; tras la politica temporal versionada se priorizan onset
confirmado y lead time persistente, manteniendo las metricas anteriores como
diagnostico compatible.

### CLI canonico

El script `run_run_to_failure_model_suite.py` permite:

- inspeccionar la suite con `--plan-only`;
- lanzar la suite sobre un `raw_path` NASA IMS/preextraido;
- activar `--use-llm` para usar agentes Qwen/Ollama en las fases no
  materializadas por la suite;
- activar `--use-memory` para usar memoria vectorial mediante
  `get_default_vector_memory_store(...)`;
- seleccionar embeddings `local_hash` u `ollama`.

El modo por defecto usa un smoke rapido sin LLM ni memoria:

```bash
python -m codigo.scripts.run_run_to_failure_model_suite \
  --plan-id fase9-hito1-rtf-smoke-001 \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen
```

## Guardarrails mantenidos

- No se crea `run_to_failure_runner.py`.
- No se crea endpoint nuevo.
- No se recalculan metricas en frontend.
- No se permite que Qwen defina codigo ni arquitecturas arbitrarias.
- Las etiquetas proxy siguen declaradas como proxy.
- F1 queda como metrica auxiliar/proxy.
- La suite materializa configuraciones soportadas por contratos y ejecutores.

## Verificacion

Tests añadidos en `codigo/tests/test_experiment_protocol.py`:

- la suite por defecto define `nasa_ims_bearing`,
  `nasa_ims_temporal_v1` y familias de modelo comparables;
- un plan run-to-failure puede derivarse de una `ModelingDecision`;
- la ejecucion de plan con factories fake genera tabla temporal con metricas
  run-to-failure y nota metodologica.

Comando ejecutado:

```bash
python -m unittest codigo.tests.test_experiment_protocol
```

Resultado:

```text
Ran 11 tests in 0.100s
OK
```

Verificacion ampliada:

```bash
python -m unittest codigo.tests.test_experiment_protocol codigo.tests.test_run_registry
python -m unittest discover codigo/tests
git diff --check
```

Resultado:

```text
Ran 18 tests in 0.114s
OK

Ran 340 tests in 1.211s
OK

git diff --check sin incidencias
```

## Smoke operativo

Se ejecuto la suite sobre el raw pequeño:

```text
codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen
```

Comando:

```bash
python -m codigo.scripts.run_run_to_failure_model_suite \
  --plan-id fase9-hito1-rtf-smoke-001 \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen
```

Artefactos:

- `codigo/experiments/run_to_failure/fase9-hito1-rtf-smoke-001/experiment_plan.json`;
- `codigo/experiments/run_to_failure/fase9-hito1-rtf-smoke-001/comparison.json`;
- `codigo/experiments/run_to_failure/fase9-hito1-rtf-smoke-001/results_table.md`.

Runs generadas:

- `fase9-hito1-rtf-smoke-001_pca_reconstruction_error`;
- `fase9-hito1-rtf-smoke-001_isolation_forest`;
- `fase9-hito1-rtf-smoke-001_one_class_svm`.

Resultado resumido:

| Modelo | Aprobado | Deteccion | Lead time | FAR nominal | Tendencia Spearman | F1 aux | FPR aux |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PCA reconstruction error | no | 1.0000 | 1200.9728 | 0.6667 | 0.9167 | 0.6667 | 1.0000 |
| Isolation Forest | no | 1.0000 | 1200.9728 | 0.6667 | 0.4788 | 0.6667 | 1.0000 |
| One-Class SVM | no | 1.0000 | 1200.9728 | 0.6667 | 0.7822 | 0.6667 | 1.0000 |

Interpretacion:

- el circuito de suite funciona end-to-end;
- ninguna run queda aprobada por falsas alarmas nominales altas;
- PCA ofrece la tendencia temporal mas fuerte en este smoke;
- el resultado no debe presentarse como mejora operacional, sino como primera
  validacion de infraestructura comparativa.

## Pendiente para cerrar Hito 9.1 operativo

Queda pendiente una ejecucion mas fuerte de la suite sobre una secuencia NASA
IMS mas larga o sintetica/preextraida ampliada con:

- `raw_path` real;
- `dataset_policy_id=nasa_ims_temporal_v1`;
- preferiblemente `--use-llm`, `--use-memory` y Qdrant si el coste es razonable;
- comparacion final persistida en `codigo/experiments/run_to_failure/...`;
- documento de resultado con metricas reales y cautelas.

Ese paso debe hacerse despues de validar que Qdrant/Ollama estan disponibles y
que la secuencia elegida es suficientemente larga para que las diferencias de
histeresis, tendencia y falsas alarmas sean informativas.
