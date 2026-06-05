# Fase 9 - Hito 9.4: Autoencoder PyTorch denso

Fecha: 2026-06-05

## Objetivo

Incorporar `autoencoder_dense` como familia de modelo no supervisada para
`run_to_failure_degradation`, manteniendo la metodologia del proyecto:

- el LLM no entrena ni ejecuta codigo;
- el agente `modeler` elige entre familias soportadas con evidencia;
- el ejecutor `modeling.py` entrena de forma determinista y reproducible;
- el evaluador juzga el resultado con el mismo contrato `predictions.csv` y las
  mismas metricas temporales ya existentes.

## Reutilizacion

No se crea un ejecutor paralelo. El propietario canonico sigue siendo:

- `codigo/app/executors/modeling.py` para entrenamiento/prediccion;
- `codigo/app/agents/modeler.py` para decision estructurada;
- `codigo/app/services/experiment_protocol.py` para suites comparables;
- `codigo/app/executors/evaluation.py` y servicios temporales para evaluacion.

La salida se integra en el contrato comun:

- `model_path`;
- `predictions.csv`;
- `modeling_summary.json`;
- artefactos `model`, `predictions` y `log`.

## Implementacion

`modeling.py` anade:

- `DEFAULT_AUTOENCODER_DENSE_CONFIG`;
- `AUTOENCODER_DENSE_PARAMS`;
- validacion cerrada de hiperparametros;
- entrenamiento PyTorch CPU;
- escalado con `StandardScaler` ajustado solo en ventanas normales de `train`;
- arquitectura densa encoder/decoder cerrada;
- loss MSE de reconstruccion;
- `anomaly_score` como error medio de reconstruccion por ventana;
- threshold por `threshold_quantile` usando la politica comun;
- guardado de `autoencoder_dense.pt`;
- guardado de `autoencoder_dense_scaler.joblib`;
- guardado de `autoencoder_dense_training_curve.json`.

Hiperparametros permitidos:

- `hidden_layers`: entero o string CSV, por ejemplo `"32,16"`;
- `latent_dim`;
- `learning_rate`;
- `batch_size`;
- `max_epochs`;
- `patience`;
- `weight_decay`;
- `threshold_quantile`;
- `device`, actualmente `cpu`.

No se permite:

- capas arbitrarias;
- codigo generado por el agente;
- entrenamiento sobre senal cruda;
- GPU por defecto;
- `lstm_autoencoder` en este hito.

## Integracion agentica

El `modeler` puede elegir `autoencoder_dense` solo cuando:

- el perfil es `run_to_failure_degradation`;
- la estrategia cita `temporal_model_readiness_assessor`;
- `evidence_refs` contiene `tool:temporal_model_readiness_assessor`;
- `evidence_refs` contiene al menos una ref `readiness:*`;
- la configuracion usa hiperparametros cerrados;
- `expected_model_path` termina en `autoencoder_dense.pt`.

Esto preserva el protagonismo del LLM: el agente decide si merece la pena
probar el autoencoder, pero no inventa arquitectura ni sustituye la evaluacion.

## Suite comparable

`default_run_to_failure_model_suite_plan()` incorpora ahora cuatro familias:

- `pca_reconstruction_error`;
- `isolation_forest`;
- `one_class_svm`;
- `autoencoder_dense`.

El autoencoder queda como candidato comparable frente a PCA. Si mejora
sensibilidad pero aumenta falsas alarmas nominales, el evaluador puede
rechazarlo con cautelas igual que cualquier otra familia.

## Dependencia

`requirements.txt` declara:

```text
torch>=2.3
```

En la retomada del 2026-06-05 se instalo PyTorch en el entorno local:

```text
torch 2.12.0+cu130
torch.cuda.is_available() = False
```

El ejecutor sigue devolviendo un error claro si se selecciona
`autoencoder_dense` en un entorno sin PyTorch. El test de entrenamiento real
queda marcado como `skip` solo cuando falta la dependencia.

## Verificacion

Pruebas focales ejecutadas:

```bash
python -m unittest codigo.tests.test_modeling_executor codigo.tests.test_modeler_agent codigo.tests.test_experiment_protocol
python -m codigo.scripts.run_run_to_failure_model_suite --plan-only
python -m codigo.scripts.run_run_to_failure_model_suite \
  --plan-id fase9-hito4-autoencoder-smoke-001 \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen
```

Resultado:

- `39 tests OK`;
- `1 skipped`, correspondiente al test del camino de dependencia ausente, no al
  entrenamiento real;
- `--plan-only` lista cuatro experimentos:
  `pca_reconstruction_error`, `isolation_forest`, `one_class_svm` y
  `autoencoder_dense`.
- smoke real `fase9-hito4-autoencoder-smoke-001` ejecutado con cuatro runs;
- artefactos de autoencoder generados:
  - `autoencoder_dense.pt`;
  - `autoencoder_dense_scaler.joblib`;
  - `autoencoder_dense_training_curve.json`;
  - `predictions.csv`;
  - `modeling_summary.json`.

Resumen del smoke:

- los cuatro modelos mantienen `Onset confirmado = 1.0000`;
- `autoencoder_dense` obtiene el mejor `Lead persistente = 1200.9216`;
- `autoencoder_dense` obtiene la mejor tendencia Spearman `0.9667`;
- `autoencoder_dense` obtiene el mayor `HI drop = 83.0853`;
- todos siguen no aprobados porque `FAR nominal = 0.6667` y `FPR aux = 1.0000`;
- PCA conserva mejor `HI mono = 1.0000` y mejor score global de Health
  Indicator `0.8698`;
- Isolation Forest conserva la mejor robustez HI y menor volatilidad nominal.

Readiness del smoke:

- `temporal_model_readiness_v1` devuelve `readiness_level = blocked`;
- `autoencoder_ready = false`;
- motivo: `insufficient_train_nominal_windows`;
- el smoke tiene `n_train_nominal_windows = 3`, por debajo del minimo de la
  politica;
- por tanto, el smoke valida integracion tecnica y artefactos, pero no debe
  presentarse como evidencia suficiente para preferir autoencoder en una run
  agentica real.

Smoke ligero con readiness:

- Se genero `synthetic_autoencoder_readiness_lite` con 24 ficheros sinteticos
  NASA IMS-like para no invertir esfuerzo extra en un benchmark nuevo.
- Run: `fase9-hito4b-ae-readiness-lite-001`.
- Readiness: `autoencoder_ready = true`, `readiness_level = caution`,
  `n_train_nominal_windows = 35`, `rul_ready = false` por una sola run.
- Resultado: `autoencoder_dense` queda aprobado en la suite ligera y lidera
  `HI drop`, monotonicidad HI y score global HI, pero One-Class SVM lidera lead
  persistente y tendencia. La lectura correcta es que el autoencoder ya es una
  alternativa defendible para que el agente la considere, no una eleccion fija.

Smoke agentico con Qwen:

- Run libre: `fase9-agentic-modeler-readiness-lite-llm-001`.
- Comando base: `python -m codigo.scripts.run_dataset_pipeline_with_memory`
  con `--use-llm` sobre `synthetic_autoencoder_readiness_lite`.
- La ejecucion finaliza en `completed` y `approved = true`.
- El `modeler` responde con LLM real y selecciona
  `pca_reconstruction_error`, priorizando interpretabilidad del score temporal
  frente a optimizacion de F1 sobre etiquetas proxy.
- La decision cita las herramientas `temporal_health_lookup`,
  `degradation_metrics_lookup` y `temporal_model_readiness_assessor`.
- El autoencoder queda en `comparison_candidates` como alternativa
  `autoencoder_dense_temporal`, condicionada a readiness suficiente, no como
  seleccion forzada.
- Metricas principales: `Onset confirmado = 1.0000`,
  `Lead persistente = 7200.7680`, `FAR nominal = 0.0952`,
  `HI drop = 76.4453`, `HI monotonicidad = 0.5214`,
  `tendencia Spearman = 0.7967`, `F1 proxy = 0.8602`.
- El evaluador aprueba con politica run-to-failure. En esta primera prueba,
  reporting deja una cautela operativa: el redactor cae a fallback por JSON
  invalido y el debate recomienda revision humana aunque el verificador final
  no lista correcciones pendientes. Se registra como fleco menor de robustez de
  salida LLM, no como fallo del modelado, y queda corregido en el hardening
  posterior.

Hardening de fallbacks visibles:

- Se detecto que las caidas a fallback dejan mala trazabilidad en un proyecto
  donde los agentes deben tener protagonismo real.
- `OllamaJSONClient` incorpora ahora una reparacion JSON estructurada antes de
  devolver error cuando existe esquema.
- `supervisor`, `evaluator`, `report_writer` y `report_verifier` hacen un
  reintento de contrato ante salidas validables pero incorrectas.
- Las correcciones por contrato se registran como `Guardrail correction`,
  reservando `Fallback after LLM failure` para fallos tecnicos del proveedor o
  JSON irrecuperable.
- El limite de salida JSON de Ollama sube a `4096` tokens y queda configurable
  con `TFM_LLM_NUM_PREDICT`.
- Se compacto el template de `report_writer` para reducir truncados JSON.
- Validacion real posterior:
  `fase9-agentic-modeler-readiness-lite-llm-guardrail-001` finaliza
  `completed`, `approved = true`; `modeler`, `evaluator` y `report_writer`
  inicial responden con LLM real y confianza alta.
- Tras el cambio semantico final, la suite completa queda en `352 tests OK`,
  `1 skipped`.

## Limitaciones

- La arquitectura es densa sobre `windows_features.csv`, no LSTM ni senal cruda.
- El autoencoder no aprueba por si mismo una run; solo produce un score que
  debe pasar evaluacion temporal, Health Indicator y guardarrails del agente.
