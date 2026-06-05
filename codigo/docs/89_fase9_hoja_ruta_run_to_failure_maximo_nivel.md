# Fase 9 - Hoja de ruta run-to-failure al maximo nivel

Fecha: 2026-06-04.
Estado: cerrada el 2026-06-05.

Documento de cierre: `codigo/docs/95_cierre_fase9_run_to_failure_maximo_nivel.md`.

## Objetivo

Llevar el perfil principal del TFM:

```text
run_to_failure_degradation
```

desde una base agentica ya funcional hacia una plataforma PHM mas ambiciosa:
deteccion de anomalias, confirmacion de degradacion, Health Indicators,
autoencoder PyTorch, RUL experimental con incertidumbre, visualizacion humana y
comparacion agentica de estrategias.

La Fase 8 deja a los agentes Qwen/LLM con herramientas temporales, debate,
recomendacion operacional, memoria Qdrant y citas auditadas. La Fase 9 no debe
quitarles protagonismo; debe darles mejores instrumentos deterministas para que
puedan observar, comparar, decidir y explicar con mas nivel.

## Por que una Fase 9

Se crea una fase nueva en lugar de ampliar indefinidamente la Fase 8 porque el
alcance cambia:

- Fase 8: hacer que Qwen/LLM gobierne runs temporales con herramientas,
  contratos, memoria y guardarrails.
- Fase 9: elevar la capacidad PHM del perfil con politicas de salud,
  histeresis, onset, Health Index avanzado, autoencoder PyTorch y RUL
  experimental.

Esta separacion evita mezclar cierre agentico con investigacion de modelos y
mantiene defendible el relato del TFM.

## Base de conocimiento usada

Documentos de partida:

- `codigo/docs/run_to_failure_state_of_art.md`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- `codigo/docs/88_fase8_memoria_m4_5_qwen_qdrant_citas_agenticas.md`;
- `codigo/docs/87_cierre_sesion_2026_06_03_recap_para_continuar.md`;
- `codigo/docs/66_fase7_perfiles_supervision_binary_run_to_failure.md`;
- `codigo/docs/69_fase7_cierre_base_run_to_failure.md`;
- `codigo/docs/70_fase7_hito9_panel_control_run_to_failure.md`.

Lectura sintetizada:

- Un dataset run-to-failure debe leerse como historia temporal del activo, no
  como clasificacion binaria aislada.
- Conviene separar anomalía, degradacion confirmada, Health Index y RUL.
- Una alerta aislada no implica degradacion sostenida.
- Un RUL sin incertidumbre comunica demasiada certeza.
- Los Health Indicators son una pieza central para prognostics defendible.
- Autoencoders entrenados con tramo sano encajan bien como detector no
  supervisado y Health Indicator aprendido, siempre que se controle leakage y
  coste.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Extender el perfil run-to-failure con politicas temporales versionadas,
Health Indicators, autoencoder PyTorch, RUL experimental y suite agentica
comparativa, sin crear un runner paralelo ni permitir codigo libre generado por
agentes.
```

Inventario previo:

- `codigo/app/schemas/state.py`: `ModelingConfig` ya contempla
  `autoencoder_dense` y `lstm_autoencoder`.
- `codigo/app/executors/modeling.py`: propietario canonico del entrenamiento e
  inferencia de modelos; actualmente soporta Isolation Forest, One-Class SVM y
  PCA reconstruction error.
- `codigo/app/executors/evaluation.py`: propietario canonico de metricas
  binarias y temporales.
- `codigo/app/services/run_visualization.py`: propietario canonico de
  `temporal_series`, `health_index`, `risk_index`, `health_state` y
  recomendacion agentica.
- `codigo/app/services/agent_tools.py`: catalogo canonico de herramientas
  read-only para agentes.
- `codigo/app/agents/modeler.py`: agente que decide familia de modelo,
  estrategia, objetivos y politica de alerta.
- `codigo/app/agents/evaluator.py`: agente que audita defendibilidad
  operacional.
- `codigo/app/services/experiment_protocol.py`: protocolo experimental local
  existente, actualmente orientado a CWRU, reutilizable como patron para
  suites comparables.
- `codigo/app/services/run_registry.py`: comparacion canonica de runs.
- `codigo/frontend/src/App.tsx`: panel visual y comparacion frontend.

Decision:

```text
extend
```

Motivo: ya existen propietarios claros para modelos, metricas, visualizacion,
herramientas, agentes, memoria y comparacion. La Fase 9 debe extender esas
fronteras, no crear `run_to_failure_runner.py`, no crear una API NASA paralela
y no introducir notebooks como via principal de ejecucion.

## Principios no negociables

- Qwen/LLM decide dentro de contratos estrictos; no ejecuta codigo arbitrario.
- PyTorch se usara solo dentro de ejecutores deterministas testeables.
- El autoencoder sera una familia de modelo soportada, no una arquitectura
  generada por el agente.
- El entrenamiento solo puede usar tramo nominal/train definido por la politica.
- No se ajustan normalizadores, umbrales ni modelos usando futuro no disponible.
- RUL experimental no se presenta como RUL industrial validado.
- F1, precision y recall siguen siendo auxiliares/proxy en este perfil.
- Las etiquetas temporales proxy nunca se presentan como oficiales.
- Cada hito debe dejar tests, documentacion y reflejo en la memoria academica.

## Arquitectura objetivo

La lectura principal del perfil debe quedar organizada en cinco capas:

```text
1. Anomaly score
   El modelo dice que tan distinta es una ventana respecto al tramo sano.

2. Confirmacion temporal / onset
   Una politica versionada decide si hay pico aislado, vigilancia o degradacion
   sostenida.

3. Health Index
   Una escala 100 -> 0 resume salud, tendencia, robustez y evidencias tecnicas.

4. RUL experimental
   Solo si hay readiness suficiente, se estima un rango conservador/probable/
   optimista con confianza y advertencias.

5. Recomendacion agentica
   Qwen/evaluator interpreta metricas, memoria, guardarrails y siguiente accion.
```

## Decision sobre PyTorch y autoencoder

Se incorpora PyTorch como dependencia candidata de Fase 9 porque aporta una
implementacion mas profesional, extensible y defendible que un autoencoder
simulado con `MLPRegressor`.

La primera version sera deliberadamente controlada:

- `autoencoder_dense` sobre `windows_features.csv`, no sobre senal cruda.
- Encoder/decoder denso pequeno y cerrado.
- Entrenamiento solo con ventanas normales del split `train`.
- `StandardScaler` o normalizador equivalente ajustado solo con train.
- Loss MSE de reconstruccion.
- `anomaly_score` = error de reconstruccion por ventana.
- `threshold_quantile` calculado sobre train/validation segun politica actual.
- Semillas fijadas y CPU por defecto.
- Guardado reproducible de modelo, scaler, configuracion y resumen.

El agente `modeler` podra elegir `autoencoder_dense` solo dentro de un espacio
cerrado de hiperparametros. No podra proponer capas arbitrarias ni codigo. El
ejecutor validara:

- `hidden_layers`;
- `latent_dim`;
- `learning_rate`;
- `batch_size`;
- `max_epochs`;
- `patience`;
- `weight_decay`;
- `threshold_quantile`;
- `random_state`;
- `device`, inicialmente `cpu` salvo decision explicita.

`lstm_autoencoder` queda fuera de esta primera fase tecnica. Se conserva como
posible Fase 10 o extension posterior, porque requiere secuencias, mayor coste,
mas control de leakage temporal y validacion especifica.

## Hito 9.1: suite canonica agentica run-to-failure

Estado: base implementada en
`codigo/docs/90_fase9_hito1_suite_canonica_run_to_failure.md`.

Objetivo:

- cerrar una suite comparable que demuestre que el perfil no depende de una
  unica run ni de una unica familia de modelo.

Trabajo:

- generalizar el patron de `experiment_protocol.py` para planes
  `run_to_failure_degradation` sin romper CWRU;
- ejecutar o preparar runs comparables sobre el mismo dataset/politica:
  - `pca_reconstruction_error`;
  - `isolation_forest`;
  - `one_class_svm`;
  - `autoencoder_dense` cuando PyTorch este instalado;
- mantener `use_llm=true` y, cuando sea viable, `TFM_MEMORY_BACKEND=qdrant`;
- conservar decisiones, herramientas, memoria, debate, informe y snapshot;
- comparar por metricas temporales, no por F1 principal;
- documentar si la memoria ayuda en deliberacion, configuracion o solo trazas.

Criterio de aceptacion:

- existe una suite reproducible de al menos cuatro modelos sobre el mismo
  protocolo temporal;
- la comparacion muestra lead time, falsas alarmas, tendencia, persistencia y
  aprobacion agentica;
- Qwen cita herramientas temporales y memoria cuando se usa Qdrant.

Avance 2026-06-04:

- `experiment_protocol.py` define la suite canonica inicial
  PCA/Isolation Forest/One-Class SVM para `nasa_ims_bearing` con
  `nasa_ims_temporal_v1`; tras el Hito 9.4 se amplia con
  `autoencoder_dense`;
- `run_run_to_failure_model_suite.py` permite planificar y ejecutar la suite;
- se ejecuto el smoke `fase9-hito1-rtf-smoke-001` sin LLM/memoria sobre
  `preextracted_synthetic_qwen`;
- el smoke valida el circuito end-to-end, pero las tres runs iniciales quedan no
  aprobadas por falsas alarmas nominales altas.

## Hito 9.2: politica versionada de salud, riesgo e histeresis

Estado: nucleo implementado en
`codigo/docs/91_fase9_hito2_politica_temporal_evaluacion_run_to_failure.md`.

Objetivo:

- sacar la logica de estado temporal de reglas embebidas y convertirla en una
  politica versionada, auditable y citable.

Trabajo:

- definir contrato `HealthPolicy` o equivalente;
- definir contrato `AlertPolicy` o equivalente;
- introducir `health_policy_id`;
- declarar umbrales `nominal/watch/warning/critical`;
- declarar persistencia minima para degradacion confirmada;
- separar:
  - primer pico;
  - primer aviso sostenido;
  - onset de degradacion confirmado;
  - estado critico;
  - fallo historico de replay;
- anadir herramienta read-only `hysteresis_policy_simulator` para simular
  politicas sobre `predictions.csv` sin reentrenar modelos.

Avance 2026-06-04:

- se crean los contratos `TemporalHealthPolicy` y `TemporalAlertPolicy`;
- se introduce `temporal_health_policy_v1` y `alert_persistence_v1`;
- `evaluation.py` calcula onset confirmado, lead time persistente, picos
  aislados, episodios y racha maxima;
- `run_visualization.py` reutiliza la misma politica para UI/herramientas;
- `agent_tools.py` expone refs citables de politica y onset confirmado;
- `evaluator.py` aprueba con metricas confirmadas cuando existen y usa las
  antiguas solo como fallback historico;
- `run_registry.py` y las tablas de suite comparan por onset confirmado y lead
  persistente.

Pendiente:

- `hysteresis_policy_simulator` queda diferido como mejora opcional para
  comparar politicas alternativas sin reentrenar.

Criterio de aceptacion:

- dos runs pueden explicar que politica de salud han usado;
- el evaluador puede aprobar o rechazar por onset/histeresis, no por pico
  aislado;
- las metricas temporales incluyen persistencia y cambios espurios.

## Hito 9.3: Health Indicator avanzado

Estado: nucleo implementado en
`codigo/docs/92_fase9_hito3_health_indicator_avanzado.md`.

Objetivo:

- construir un Health Index mas defendible que `100 - risk_index` directo.

Trabajo:

- calcular HI bruto y suavizado;
- versionar la politica de suavizado;
- anadir metricas de HI:
  - monotonicidad;
  - robustez;
  - separacion inicio-final;
  - pendiente;
  - volatilidad nominal;
  - trendability/prognosability cuando haya varias trayectorias;
- traducir evidencias tecnicas a lenguaje humano:
  - mas energia vibracional;
  - mas impulsividad;
  - peor reconstruccion;
  - tendencia sostenida;
  - incertidumbre alta;
- exponer refs citables para agentes:
  - `health:monotonicity`;
  - `health:robustness`;
  - `health:onset_confirmed`;
  - `health:dominant_evidence`.

Criterio de aceptacion:

- el panel y los agentes distinguen score del modelo, Health Index y estado
  operacional;
- el informe puede explicar por que la salud baja sin vender diagnostico causal
  no demostrado.

Avance 2026-06-04:

- se introduce `health_indicator_policy_v1`;
- el HI suavizado usa media movil causal/trailing para evitar leakage;
- `evaluation.py` calcula caida de HI, monotonicidad, robustez, volatilidad
  nominal, slope, Spearman y score compuesto;
- `run_visualization.py` expone HI bruto/suavizado por punto y resumen por run;
- `agent_tools.py` anade refs `health:*` citables;
- `evaluator.py` y `report_writer.py` distinguen score, Health Indicator y
  estado operacional;
- `run_registry.py` y la tabla experimental comparan `HI drop` y `HI mono`.

Pendiente:

- conectar `dominant_evidence` con features fisicas explicitas o con el error
  de reconstruccion del autoencoder; por ahora se mantiene como evidencia del
  detector/score, sin causalidad fisica fuerte.

## Hito 9.4: autoencoder PyTorch denso

Estado: implementado en
`codigo/docs/94_fase9_hito4_autoencoder_pytorch_denso.md`.

Objetivo:

- incorporar `autoencoder_dense` como familia de modelo no supervisada
  reproducible para score de reconstruccion y Health Indicator aprendido.

Trabajo:

- anadir dependencia PyTorch con documentacion de entorno;
- implementar ejecutor determinista dentro de `modeling.py` o modulo auxiliar
  canonico llamado desde `modeling.py`;
- validar hiperparametros cerrados;
- entrenar con split nominal/train;
- guardar:
  - `autoencoder_dense.pt`;
  - scaler/preprocesador;
  - `predictions.csv`;
  - `modeling_summary.json`;
  - curva de entrenamiento en JSON;
- anadir tests pequenos con dataset sintetico/tabular;
- extender `modeler` para permitir elegir `autoencoder_dense`;
- extender memoria y comparacion para registrar tradeoffs frente a PCA.

Avance 2026-06-05:

- `modeling.py` soporta `autoencoder_dense` con PyTorch, CPU por defecto,
  arquitectura densa cerrada y error MSE de reconstruccion;
- el ejecutor guarda `autoencoder_dense.pt`, scaler joblib, curva de
  entrenamiento JSON, `predictions.csv` y `modeling_summary.json`;
- `modeler.py` permite seleccionar `autoencoder_dense` solo dentro del perfil
  run-to-failure y exige refs `readiness:*` y la herramienta
  `temporal_model_readiness_assessor`;
- `experiment_protocol.py` incorpora `autoencoder_dense` a la suite canonica;
- `requirements.txt` declara `torch>=2.3`; en entornos sin PyTorch el ejecutor
  devuelve un error claro;
- se instalo PyTorch localmente y se ejecuto el smoke
  `fase9-hito4-autoencoder-smoke-001` sobre `preextracted_synthetic_qwen`;
- el autoencoder genera `.pt`, scaler, curva de entrenamiento y `predictions.csv`;
- en el smoke, `autoencoder_dense` lidera lead persistente, tendencia e
  `HI drop`, pero la run sigue rechazada por falsas alarmas nominales/FPR.
- la readiness del smoke queda bloqueada por solo 3 ventanas train nominales;
  se considera validacion tecnica del circuito, no evidencia metodologica
  suficiente para preferir autoencoder.

Criterio de aceptacion:

- una run temporal puede elegir o materializar `autoencoder_dense`;
- el output conserva el mismo contrato `predictions.csv`;
- el evaluador juzga al autoencoder con las mismas metricas temporales;
- si mejora sensibilidad pero aumenta falsas alarmas, puede quedar rechazado
  con cautelas.

## Hito 9.5: herramienta de readiness para autoencoder y RUL

Estado: implementado en
`codigo/docs/93_fase9_hito5_readiness_modelos_temporales_avanzados.md`.

Objetivo:

- evitar que Qwen use modelos mas complejos sin evidencia suficiente.

Trabajo:

- anadir herramienta read-only `temporal_model_readiness_assessor`;
- evaluar:
  - numero de ventanas train nominales;
  - numero de runs/activos;
  - continuidad temporal;
  - presencia de `time_to_failure_seconds`;
  - calidad de splits;
  - riesgo de leakage;
  - coste estimado;
- devolver decision estructurada:
  - `autoencoder_ready`;
  - `rul_ready`;
  - `blocked_reasons`;
  - `recommended_next_experiment`.

Criterio de aceptacion:

- el `modeler` no puede elegir autoencoder o RUL experimental sin citar
  readiness;
- el `evaluator` puede bloquear una conclusion si se ignora readiness.

Avance 2026-06-05:

- se crea `TemporalModelReadinessPolicy` con `temporal_model_readiness_v1`;
- se implementa `assess_temporal_model_readiness(...)`;
- `agent_tools.py` expone `temporal_model_readiness_assessor`;
- la herramienta evalua ventanas train nominales, features, splits,
  continuidad, cobertura de `time_to_failure_seconds`, leakage y coste;
- devuelve refs `readiness:*` citables por agentes;
- `modeler.py` exige readiness cuando se propongan modelos temporales
  avanzados;
- `evaluator.py` puede usar readiness para bloquear conclusiones de
  autoencoder/RUL no justificadas.

## Hito 9.6: RUL experimental con incertidumbre

Objetivo:

- introducir una primera frontera de RUL sin presentarla como prediccion
  industrial final.

Trabajo:

- definir contrato opcional `RULPrediction` o equivalente:
  - `available`;
  - `method`;
  - `predicted_rul_seconds`;
  - `conservative_rul_seconds`;
  - `probable_rul_seconds`;
  - `optimistic_rul_seconds`;
  - `predicted_failure_time`;
  - `confidence`;
  - `uncertainty_warning`;
  - `readiness`;
- empezar por baseline simple:
  - extrapolacion de tendencia del Health Index;
  - tiempo hasta umbral critico;
  - bandas por sensibilidad de pendiente;
- anadir metricas si existe fallo historico:
  - error relativo;
  - early/late bias;
  - cobertura de intervalo;
  - penalizacion asimetrica experimental;
- mostrar en frontend como "RUL experimental".

Criterio de aceptacion:

- el usuario distingue deteccion, salud y RUL;
- Qwen no puede afirmar RUL si `available=false`;
- el informe declara metodo, incertidumbre y limitaciones.

## Hito 9.7: visualizacion industrial avanzada

Objetivo:

- convertir la pestaña `Visualizacion` y la comparacion en una lectura PHM
  humana, no solo grafica tecnica.

Trabajo:

- linea de vida del activo:
  - sano;
  - vigilar;
  - degradacion confirmada;
  - critico;
  - fallo historico;
- tarjeta de salud:
  - estado;
  - HI bruto/suavizado;
  - riesgo;
  - onset;
  - RUL experimental si existe;
  - confianza;
  - accion recomendada;
- small multiples por modelo;
- cola de runs/activos por riesgo;
- evidencias traducidas a lenguaje normal;
- capa experta plegable con score, features y diagnostico 2D.

Criterio de aceptacion:

- una persona puede entender el estado del activo sin abrir JSON;
- el panel muestra claramente si hay RUL no soportado, replay historico o RUL
  experimental.

## Hito 9.8: memoria y aprendizaje metodologico de Fase 9

Objetivo:

- que los aciertos y errores de histeresis, HI, autoencoder y RUL experimental
  alimenten la memoria agentica.

Trabajo:

- enriquecer `DecisionEpisode` con:
  - `health_policy_id`;
  - `alert_policy_id`;
  - `onset_result`;
  - `hi_metrics`;
  - `autoencoder_tradeoffs`;
  - `rul_readiness`;
  - `rul_warning`;
- anadir quality gate especifico para recuerdos de autoencoder/RUL;
- evitar que una run experimental se convierta en receta general si esta
  marcada como `caution` o `boundary_case`.

Criterio de aceptacion:

- una run posterior puede recuperar lecciones sobre falsas alarmas, HI inestable
  o autoencoder sobredimensionado;
- el agente cita memoria sin convertir cautelas en aprobaciones.

## Hito 9.9: extension de datasets run-to-failure

Objetivo:

- preparar el sistema para que el perfil no dependa solo de NASA IMS.

Orden recomendado:

1. XJTU-SY, por tener 15 trayectorias completas y condiciones operativas
   separables.
2. PRONOSTIA/FEMTO-ST, por su relevancia para RUL y scoring asimetrico.
3. C-MAPSS/N-CMAPSS, como extension multivariante/turbofan posterior.

Criterio de aceptacion:

- el contrato temporal comun absorbe un segundo dataset sin crear runner
  paralelo;
- se mantiene separacion por run/activo para evitar leakage;
- los agentes declaran diferencias de dominio, condicion operativa y validez.

## Riesgos principales

- Leakage temporal por mezclar ventanas de la misma trayectoria.
- Normalizacion con futuro.
- Autoencoder demasiado potente para pocos datos.
- RUL comunicado con falsa precision.
- Qwen usando memoria cautelar como permiso para aprobar.
- Frontend mostrando fallo historico como prediccion.
- Dependencias PyTorch rompiendo reproducibilidad Docker/local.

Mitigacion:

- contratos cerrados;
- readiness previo;
- tests pequeños;
- ejecuciones comparables;
- `device=cpu` por defecto;
- advertencias visibles;
- evaluador operacional con guardarrails;
- memoria con quality gate.

## Orden recomendado

1. Hito 9.1: suite canonica PCA/IF/OCSVM.
2. Hito 9.2: politica de salud e histeresis versionada.
3. Hito 9.3: Health Indicator avanzado.
4. Hito 9.5: readiness para modelos temporales avanzados.
5. Hito 9.4: autoencoder PyTorch denso.
6. Hito 9.6: RUL experimental con incertidumbre.
7. Hito 9.7: visualizacion industrial avanzada.
8. Hito 9.8: memoria metodologica de Fase 9.
9. Hito 9.9: segundo dataset run-to-failure.

Nota: el readiness se implementa antes del autoencoder completo para que Qwen
aprenda a justificar por que un modelo avanzado procede o no procede.

## Verificacion minima por hito

- tests de contratos Pydantic;
- tests de ejecutores deterministas;
- tests de herramientas agenticas;
- tests de agentes con LLM fake;
- run local pequena;
- comparacion persistida cuando aplique;
- build frontend si cambia UI;
- documentacion tecnica;
- actualizacion de memoria academica;
- smoke Docker si cambian dependencias, backend, frontend o variables.

## Criterio final de cierre de Fase 9

La Fase 9 queda cerrada operativamente con el siguiente alcance:

1. Suite run-to-failure comparable con PCA, Isolation Forest, One-Class SVM y
   autoencoder PyTorch.
2. Politica temporal versionada con onset confirmado, aviso sostenido,
   falsas alarmas nominales y lead persistente.
3. Health Indicator avanzado con caida, monotonicidad, robustez, volatilidad y
   score de calidad.
4. Readiness agentico para autoencoder/RUL, citables mediante refs
   `readiness:*`.
5. Autoencoder PyTorch denso ejecutable, reproducible y condicionado por
   readiness.
6. Run agentica real con Qwen donde el `modeler` conserva protagonismo y elige
   PCA, manteniendo autoencoder como candidato comparable.
7. Hardening de salidas LLM: reparacion JSON, reintento de contrato y
   distincion entre `Guardrail correction` y fallback tecnico.
8. Memoria academica actualizada con metodologia, implementacion,
   experimentos, resultados y conclusiones de Fase 9.

Quedan fuera de esta fase, de forma deliberada:

- RUL industrial o experimental completo con incertidumbre;
- LSTM autoencoder o entrenamiento sobre senal cruda;
- segundo dataset run-to-failure real;
- smoke Docker completo tras incorporar PyTorch.

Con esto, `run_to_failure_degradation` pasa de perfil temporal defendible a
caso fuerte de mantenimiento predictivo agentico local. Las lineas excluidas se
trasladan a trabajo futuro.
