# Fase 7 - Hito 7: perfiles de supervision binaria y run-to-failure

Fecha: 2026-06-01.

## Objetivo

Definir una hoja de ruta implementable para que la aplicacion soporte dos
familias de problema sin duplicar runners ni convertir NASA IMS en un caso
especial:

- `binary_fault_classification`: datasets con etiquetas directas por fichero o
  ventana, como CWRU;
- `run_to_failure_degradation`: datasets industriales temporales donde existe
  una secuencia de vida hasta fallo, como NASA IMS, PRONOSTIA/FEMTO-ST o
  XJTU-SY.

CWRU se mantiene en el proyecto como benchmark de regresion tecnica y prueba de
contratos. El perfil `run_to_failure_degradation` pasa a ser la linea principal
de investigacion industrial, porque se parece mas al problema real de
monitorizacion de salud y mantenimiento predictivo.

## Principio rector agentico

Este hito no convierte la aplicacion en un sistema puramente determinista de
monitorizacion. La tesis de investigacion sigue siendo agentica: evaluar si
agentes LLM locales, en la practica Qwen/Ollama, pueden dirigir una aplicacion
industrial de deteccion de anomalias con decisiones utiles, trazables y
defendibles.

Las metricas temporales, indices de riesgo, estados de salud, visualizaciones y
herramientas read-only se introducen para aumentar el campo de observacion y
accion de los agentes, no para reemplazarlos. Los ejecutores calculan,
persisten y validan; los agentes interpretan, comparan, justifican, debaten,
redactan, recomiendan siguientes pasos y deciden dentro de contratos estrictos.

La apuesta por modelos pequenos forma parte del alcance investigador. En una
maquina local pueden ser lentos, pero su interes esta precisamente en estudiar
si, con buenas herramientas deterministas de apoyo y evidencia compacta, pueden
llegar a ser viables en entornos industriales reales con servidores locales,
restricciones de privacidad, costes controlados y necesidad de auditoria. Si la
linea encuentra limites, se documentaran como resultado; hasta entonces, las
siguientes implementaciones deben intentar maximizar la capacidad agentica sin
romper reproducibilidad ni seguridad.

## Pregunta metodologica principal

NASA IMS no trae en cada fichero una etiqueta oficial por ventana del tipo
`normal` / `fault`. Los ficheros son snapshots temporales de vibracion. Lo que
si se conoce es que el experimento es run-to-failure, el orden temporal de los
snapshots y el fallo final documentado a nivel de ensayo/rodamiento.

Por tanto:

- no se debe evaluar NASA IMS real como si tuviera ground truth binario por
  ventana;
- no se deben presentar las etiquetas temporales proxy como oficiales;
- si se calculan metricas binarias, deben declarar explicitamente
  `label_source=temporal_proxy`;
- la evaluacion principal para NASA y datasets similares debe ser temporal:
  alerta temprana, falsas alarmas nominales, tendencia del indicador de salud y
  comportamiento hacia el fallo.

## Referencias tecnicas revisadas

- NASA/Data.gov cataloga IMS Bearings como dataset de `bearings`,
  `degradation`, `diagnostics`, `phm` y `prognostics`, con distribucion
  publica `IMS.zip`: https://catalog.data.gov/dataset/ims-bearings
- NASA Metrics Library for Prognostics Performance Evaluation incluye metricas
  alpha-lambda y beta para comparar RUL real frente a predicciones:
  https://software.nasa.gov/software/ARC-17898-1
- XJTU-SY declara datos completos run-to-failure de 15 rodamientos obtenidos en
  ensayos de degradacion acelerada:
  https://github.com/WangBiaoXJTU/xjtu-sy-bearing-datasets
- La documentacion publica del IEEE PHM 2012 Challenge sobre PRONOSTIA/FEMTO-ST
  describe ensayos run-to-failure de rodamientos y estimacion de RUL:
  https://raw.githubusercontent.com/wkzs111/phm-ieee-2012-data-challenge-dataset/master/IEEEPHM2012-Challenge-Details.pdf

Estas referencias no obligan a implementar esos datasets ahora. Sirven para
disenar contratos generales que puedan absorber NASA IMS y futuros datasets
run-to-failure sin reescribir la aplicacion.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Anadir soporte general para perfiles de supervision binaria y run-to-failure,
manteniendo el runner comun, los adaptadores, los ejecutores deterministas y la
UI existentes.
```

Inventario previo:

- `codigo/app/schemas/dataset.py`: `DatasetDescriptor`.
- `codigo/app/schemas/state.py`: `ProjectContext`, `ModelingConfig`,
  `MetricsReport`, `ArtifactRef`.
- `codigo/app/services/dataset_adapters.py`: adaptadores CWRU, NASA IMS y
  tabular generico.
- `codigo/app/services/pipeline_runner.py`: politica multi-dataset y
  `nasa_ims_temporal_v1`.
- `codigo/app/executors/structuring.py`: ventanas, features, splits y
  preservacion de metadatos.
- `codigo/app/executors/modeling.py`: modelos no supervisados que ya producen
  `anomaly_score`.
- `codigo/app/executors/evaluation.py`: metricas binarias actuales.
- `codigo/app/services/run_visualization.py`: datos derivados para graficas de
  runs.
- `codigo/frontend/src/App.tsx`: vistas `Pipeline`, `Agentes` y
  `Visualizacion`.

Decision: `extend`.

Motivo: las piezas canonicas ya existen. Hay que extender contratos y
artefactos para declarar el perfil experimental y evaluar temporalmente, no
crear otro pipeline ni otro frontend para NASA.

Impacto de compatibilidad:

- CWRU debe seguir funcionando igual;
- las metricas binarias actuales siguen siendo validas para
  `binary_fault_classification`;
- NASA IMS y futuros run-to-failure deben poder producir nuevas metricas y
  visualizaciones temporales sin bloquear la visualizacion PCA existente.

## Perfil 1: binary_fault_classification

Este perfil representa datasets con etiquetas directas por fichero o ventana.

Ejemplos:

- CWRU;
- futuros datasets tabulares o de vibracion con etiquetas `normal` / `fault`;
- datasets multiclass si mas adelante se extiende el contrato.

Unidad de evaluacion:

- ventana o fichero etiquetado.

Ground truth:

- `label` oficial o curado;
- granularidad `file` o `window`;
- `label_source=official` o equivalente.

Metricas principales:

- precision;
- recall;
- F1;
- false positive rate;
- ROC-AUC;
- PR-AUC;
- matriz de confusion;
- por clase si se activa multiclass.

Visualizacion principal:

- barras de metricas;
- PCA/UMAP 2D coloreado por clase/prediccion;
- frontera aproximada del detector;
- distribucion de `anomaly_score` por etiqueta;
- comparacion de runs/modelos.

## Perfil 2: run_to_failure_degradation

Este perfil representa series temporales de vida hasta fallo. No exige etiqueta
por ventana. La unidad natural no es una muestra aislada, sino la trayectoria
completa de un activo.

Ejemplos:

- NASA IMS;
- PRONOSTIA/FEMTO-ST;
- XJTU-SY;
- logs industriales de sensores con un evento de fallo o sustitucion.

Unidad de evaluacion:

- `run_id` + `asset_id`;
- ventanas ordenadas temporalmente dentro de cada run;
- evento final de fallo, si existe.

Ground truth posible:

- `failure_event_time` conocido;
- `failure_mode` conocido;
- fin de vida por ultimo timestamp;
- RUL real si la secuencia llega al fallo;
- etiqueta proxy solo si se declara explicitamente.

Ground truth que normalmente no existe:

- frontera oficial exacta entre normalidad y degradacion;
- etiqueta oficial `normal/fault` por cada ventana.

## Estructura recomendada del dataframe de ventanas

El dataframe de features debe seguir siendo comun, pero con columnas temporales
normalizadas que todos los perfiles puedan usar:

```text
window_id
dataset
run_id
asset_id
condition_id
source_path
timestamp_start
timestamp_end
window_index
time_since_start_seconds
time_to_failure_seconds
relative_life
split
label
label_detail
label_source
label_granularity
supervision_profile
failure_event_time
failure_mode
primary_channel
feature_*
```

Notas:

- `time_to_failure_seconds` solo se rellena si hay evento de fallo conocido.
- `relative_life` va de 0 a 1 cuando la duracion total es conocida.
- `label` puede ser `unknown` en run-to-failure real.
- `label_source` debe distinguir `official`, `curated`, `temporal_proxy`,
  `synthetic`, `none`.
- `supervision_profile` no debe deducirse por nombre de dataset dentro de los
  ejecutores; debe venir del descriptor, la politica o el manifiesto.

## Contratos propuestos

Nuevos literales o campos:

```text
SupervisionProfile =
  "binary_fault_classification"
  "run_to_failure_degradation"
  "unlabeled_diagnostic"

LabelGranularity =
  "window"
  "file"
  "run"
  "event"
  "none"
  "proxy_temporal"

LabelSource =
  "official"
  "curated"
  "temporal_proxy"
  "synthetic"
  "none"
```

Extensiones candidatas:

- `DatasetDescriptor.supervision_profile`;
- `DatasetDescriptor.label_granularity`;
- `ProjectContext.supervision_profile`;
- `CommonManifestRecord.metadata_json` con `failure_event_time`,
  `failure_mode`, `end_of_life_policy`, `label_source`,
  `label_granularity`;
- `MetricsReport.extra["degradation_metrics"]` como primer paso compatible;
- mas adelante, un contrato Pydantic dedicado `DegradationMetrics`.

## Modelado sobre run-to-failure

El modelado debe poder reutilizar modelos existentes sin convertirlos en
clasificadores binarios falsos.

### Familia A: novelty / anomaly detection

Uso:

- entrenar con tramo nominal inicial;
- inferir `anomaly_score` en toda la trayectoria;
- buscar crecimiento del score hacia el fallo.

Modelos actuales aplicables:

- Isolation Forest;
- One-Class SVM;
- PCA reconstruction error;
- autoencoder denso cuando exista;
- LSTM/temporal autoencoder en fase futura.

### Familia B: health indicator

Uso:

- fusionar features o scores en un indicador de salud continuo;
- suavizar la trayectoria;
- comprobar monotonicidad, tendencia y separacion inicial/final.

Opciones:

- RMS, kurtosis, crest factor y energia como indicadores basicos;
- PCA/KPCA sobre features;
- reconstruccion de autoencoder;
- score normalizado 0-1;
- smoothing con rolling median, EWMA o Savitzky-Golay.

### Familia C: alerta temprana

Uso:

- declarar un primer punto de alerta;
- medir anticipacion al fallo y falsas alarmas.

Opciones:

- umbral fijo calibrado en tramo nominal;
- rolling z-score;
- EWMA/CUSUM;
- cambio persistente durante `k` ventanas para evitar alertas aisladas.

### Familia D: RUL prediction

Uso:

- solo cuando haya suficientes trayectorias completas o una particion por runs.

Modelos:

- Random Forest / XGBoost sobre features agregadas;
- regresion sobre health indicator;
- LSTM/GRU/TCN;
- transformers temporales;
- metodos de similitud de trayectorias.

Esta familia no debe ser el primer paso de implementacion. Primero hay que
consolidar score temporal, alerta y metricas de degradacion.

## Metricas para run-to-failure

### Metricas minimas para alerta

Estas son las primeras que deberia implementar la app:

- `n_runs`: numero de trayectorias evaluadas;
- `n_windows`: numero total de ventanas;
- `first_alert_time`: primer timestamp donde el modelo alerta;
- `time_to_detection`: tiempo desde inicio hasta primera alerta;
- `lead_time_to_failure`: tiempo entre primera alerta y fallo;
- `detected_before_failure`: booleano por run;
- `false_alarm_rate_nominal`: proporcion de alertas en tramo nominal;
- `alert_persistence`: numero maximo de ventanas consecutivas en alerta;
- `missed_failure`: true si no hay alerta antes del fallo.

### Metricas de tendencia del score

- `score_trend_spearman`: correlacion Spearman entre tiempo y score;
- `score_slope`: pendiente robusta del score suavizado;
- `initial_final_separation`: diferencia entre score final e inicial;
- `initial_final_ratio`: ratio final/inicial cuando sea estable;
- `monotonicity`: consistencia del signo de incrementos del health indicator;
- `score_volatility_nominal`: ruido del indicador en tramo nominal.

### Metricas de health indicator entre runs

Estas son utiles cuando haya varias trayectorias:

- `trendability`: similitud de tendencia entre runs;
- `prognosability`: convergencia o dispersion del indicador cerca del fallo;
- `separability`: separacion entre tramo inicial y final;
- `condition_robustness`: estabilidad por condicion operativa.

### Metricas RUL futuras

Solo si hay prediccion explicita de RUL:

- MAE/RMSE de RUL;
- error relativo;
- prognostic horizon;
- alpha-lambda;
- beta metric;
- coverage de intervalos de incertidumbre.

## Visualizaciones recomendadas

### Vista temporal principal

Debe ser la visualizacion central para `run_to_failure_degradation`:

- eje X: tiempo, timestamp o `relative_life`;
- eje Y: `anomaly_score` o `health_index`;
- linea suavizada;
- umbral;
- punto de primera alerta;
- fallo final conocido;
- bandas de `train`, `validation`, `test`;
- banda nominal/proxy si existe;
- tooltip por ventana con `run_id`, `window_id`, timestamp, score, canal y
  metadatos.

### Vista de features temporales

Series por run:

- RMS;
- kurtosis;
- crest factor;
- energia;
- frecuencia dominante;
- bandas de frecuencia si se anaden features espectrales.

### Vista PCA/UMAP temporal

La PCA actual debe mantenerse, pero para run-to-failure debe colorearse por:

- tiempo relativo;
- score;
- alerta;
- run_id;
- condicion operativa.

No debe presentarse como clasificacion si no hay etiquetas oficiales.

### Vista espectral

Fase posterior:

- waterfall FFT por snapshots;
- espectrograma compacto;
- energia por bandas;
- comparacion inicio vs final.

### Vista comparativa de modelos

Para cada modelo:

- score temporal;
- primera alerta;
- lead time;
- falsas alarmas nominales;
- tabla de degradacion;
- small multiples por run.

## Encaje en la app

### Backend

Piezas a extender:

- `dataset_adapters.py`: declarar `supervision_profile` y metadatos de fallo
  cuando existan;
- `pipeline_runner.py`: planificar segun perfil, no solo por dataset;
- `structuring.py`: preservar timestamps, orden temporal, `run_id`,
  `asset_id`, `relative_life` y `time_to_failure_seconds`;
- `modeling.py`: seguir generando `predictions.csv` con `anomaly_score`;
- `evaluation.py`: enrutar a evaluacion binaria o degradacion;
- `run_visualization.py`: anadir series temporales ademas de PCA.

### Frontend

Piezas a extender:

- `types.ts`: nuevos campos de visualizacion temporal;
- `App.tsx`: en `Visualizacion`, si el perfil es run-to-failure, mostrar
  primero la vista temporal;
- `styles.css`: layout para grafica temporal, bandas y leyenda;
- mantener la vista PCA como secundaria.

### Agentes

El perfil debe entrar en los prompts de:

- `modeler`: no optimizar F1 si el perfil es run-to-failure;
- `evaluator`: juzgar temporalidad, falsas alarmas y lead time;
- `report_writer`: declarar limitaciones y tipo de ground truth;
- `report_verifier`: bloquear frases que llamen oficiales a etiquetas proxy.

La herramienta `evidence_lookup` debe exponer:

- supervision profile;
- label source;
- label granularity;
- failure metadata;
- split policy;
- metric family used.

## Hoja de ruta de implementacion

### Paso 1: contrato de perfil de supervision

Objetivo:

- anadir `supervision_profile`, `label_source` y `label_granularity` al
  descriptor/contexto sin romper CWRU.

Responsables:

- `schemas/dataset.py`;
- `schemas/state.py`;
- `dataset_adapters.py`;
- tests de schemas y adaptadores.

Criterio de aceptacion:

- CWRU declara `binary_fault_classification`;
- NASA IMS declara `run_to_failure_degradation`;
- generic tabular puede declarar `unlabeled_diagnostic` o inferirlo
  conservadoramente;
- todos los tests existentes siguen pasando.

Estado 2026-06-01:

- implementado en `DatasetDescriptor` y `ProjectContext` con literales
  cerrados y valores por defecto compatibles con CWRU;
- los adaptadores CWRU, NASA IMS y tabular generico declaran explicitamente su
  perfil, fuente y granularidad de etiquetas;
- `pipeline_runner.py` propaga el perfil NASA IMS al contexto de ejecucion y
  distingue `temporal_proxy`, `synthetic` y ausencia de labels oficiales;
- el preflight del frontend muestra el perfil y la relacion
  `label_source`/`label_granularity`;
- se actualizan tests de schemas, adaptadores, estado y runner.

### Paso 2: manifiesto temporal comun

Objetivo:

- asegurar que el manifiesto comun puede transportar metadatos temporales y de
  fallo sin depender del nombre NASA.

Responsables:

- `dataset_adapters.py`;
- `nasa_ims_temporal_policy.py`;
- tests de NASA IMS y adaptador generico.

Criterio de aceptacion:

- NASA conserva timestamp por snapshot;
- `metadata_json` puede incluir `failure_event_time`, `failure_mode`,
  `end_of_life_policy`, `official_window_labels=false`;
- no se generan etiquetas oficiales falsas.

Estado 2026-06-01:

- implementado mediante extension de `CommonManifestRecord.metadata_json` en el
  manifiesto NASA IMS base, sin anadir columnas especificas ni crear otro
  formato de manifiesto;
- se extrae la lectura/escritura CSV del manifiesto comun a
  `codigo/app/services/common_manifest.py` para reutilizarla desde adaptadores,
  politica temporal y benchmarks sinteticos; esta pieza nueva queda limitada a
  serializacion/deserializacion validada y evita mantener tres copias privadas
  del mismo codigo;
- NASA IMS base conserva `timestamp_start`/`timestamp_end` por snapshot y anade
  `failure_event_time`, `failure_mode`, `end_of_life_policy`,
  `official_window_labels=false`, `label_source=none` y
  `label_granularity=event`;
- la politica `nasa_ims_temporal_v1` conserva esos metadatos y solo cambia la
  fuente a `label_source=temporal_proxy`, con
  `label_granularity=proxy_temporal` y `label_policy_id` versionado;
- el benchmark sintetico NASA-like declara `label_source=synthetic` y
  `official_window_labels=false`.

### Paso 3: ventanas con tiempo relativo

Objetivo:

- propagar columnas temporales desde manifiesto hasta `windows_features.csv`.

Responsables:

- `structuring.py`;
- tests de estructuracion.

Criterio de aceptacion:

- `windows_features.csv` contiene `run_id`, `timestamp_start`,
  `timestamp_end`, `window_index`, `relative_life` cuando sea calculable;
- CWRU no pierde columnas ni metricas existentes.

Estado 2026-06-01:

- implementado extendiendo la ruta existente manifiesto -> limpieza ->
  estructuracion; no se crea otro generador de ventanas;
- `cleaning.py` preserva en cada `.npz` limpio `source_path`, `condition_id`,
  `asset_id`, `run_id`, `timestamp_start` y `timestamp_end`;
- `structuring.py` escribe por ventana `source_path`, `condition_id`,
  `asset_id`, `run_id`, `timestamp_start`, `timestamp_end`,
  `time_since_start_seconds`, `time_to_failure_seconds` y `relative_life`;
- `relative_life` se calcula solo cuando existe `failure_event_time` en
  `metadata_json` y timestamps suficientes dentro del run;
- `modeling.py` y `run_visualization.py` tratan esas columnas como metadatos,
  evitando que entren como features de entrenamiento o proyeccion;
- las predicciones conservan los metadatos temporales para la futura evaluacion
  de degradacion.

### Paso 4: evaluacion de degradacion minima

Objetivo:

- anadir una rama de evaluacion para run-to-failure usando el mismo
  `predictions.csv`.

Responsables:

- `evaluation.py`;
- `schemas/state.py` o `schemas/api_visualization.py` si se crea un contrato
  auxiliar;
- tests de evaluacion.

Metricas minimas:

- `first_alert_time`;
- `lead_time_to_failure`;
- `false_alarm_rate_nominal`;
- `score_trend_spearman`;
- `initial_final_separation`;
- `detected_before_failure`;
- `missed_failure`.

Criterio de aceptacion:

- NASA produce metricas de degradacion aunque no exista etiqueta oficial por
  ventana;
- la evaluacion binaria solo se calcula si hay labels suficientes y declara su
  `label_source`;
- el informe no confunde ambas familias.

Estado 2026-06-01:

- inventario previo:
  - busquedas realizadas: `label_source`, `metrics_by_split`,
    `degradation_metrics`, `false_alarm_rate_nominal`,
    `lead_time_to_failure`;
  - piezas encontradas: `evaluation.py` como propietario canonico de metricas,
    `degradation_diagnostics.py` como diagnostico no supervisado auxiliar y
    `pipeline.py` como extractor de resumen hacia `MetricsReport`;
  - decision: `extend`;
  - motivo: la capacidad nueva reutiliza el mismo `predictions.csv` y no
    justifica un evaluador paralelo;
  - impacto en compatibilidad: las metricas binarias previas se mantienen y se
    anade `degradation_metrics` como bloque opcional en `metrics.json`.
- `evaluation.py` calcula metricas temporales cuando existen
  `relative_life`, `anomaly_score` y `predicted_anomaly`;
- las metricas minimas implementadas son:
  - `first_alert_time`;
  - `time_to_detection`;
  - `lead_time_to_failure`;
  - `detected_before_failure`;
  - `missed_failure`;
  - `false_alarm_rate_nominal`;
  - `alert_persistence`;
  - `score_trend_spearman`;
  - `score_slope`;
  - `initial_final_separation`;
  - `initial_final_ratio`;
  - `monotonicity`.
- `metrics.json` declara `metric_families` y conserva una seccion binaria
  separada de la seccion `run_to_failure_degradation`;
- si `label_source` no llega en `predictions.csv`, el evaluador deja una
  advertencia en `binary_metric_context` para que las metricas binarias se
  interpreten con el contexto de la run y no como verdad oficial aislada;
- el fragmento `evaluation_summary.md` incluye una tabla compacta por run con
  primera alerta, lead time, falsas alarmas nominales, tendencia y fallo
  perdido;
- `pipeline.py` copia al estado un resumen plano de degradacion en
  `MetricsReport.extra` sin meter estructuras anidadas en el contrato actual.

### Paso 5: visualizacion temporal

Objetivo:

- ampliar `GET /runs/{run_id}/visualization` para devolver series temporales.

Responsables:

- `schemas/api_visualization.py`;
- `run_visualization.py`;
- `frontend/src/types.ts`;
- `frontend/src/App.tsx`;
- `frontend/src/styles.css`.

Criterio de aceptacion:

- para NASA, la primera vista muestra score/health index vs tiempo;
- se ve umbral, primer aviso y fallo final si existe;
- PCA sigue disponible;
- si faltan metadatos temporales, el endpoint degrada con warnings claros.

Estado 2026-06-01:

- inventario previo:
  - busquedas realizadas: `RunVisualizationData`, `ProjectionPoint`,
    `projection_available`, `run_visualization`, `visualization-panel`,
    `projection-panel`;
  - piezas encontradas: `schemas/api_visualization.py` como contrato API,
    `services/run_visualization.py` como derivador read-only de visualizaciones,
    `frontend/src/types.ts` como espejo TypeScript y `App.tsx`/`styles.css`
    como pestaña de visualizacion existente;
  - decision: `extend`;
  - motivo: la serie temporal usa los mismos artefactos `predictions.csv` y
    `features.csv`; crear otro endpoint o vista paralela duplicaria
    responsabilidad;
  - impacto en compatibilidad: la respuesta mantiene PCA y metricas existentes,
    y anade `temporal_series` como bloque opcional.
- `RunVisualizationData` incluye `TemporalSeriesData`, `TemporalRunSeries` y
  `TemporalSeriesPoint`;
- `run_visualization.py` construye la serie temporal desde `predictions.csv`
  usando como eje, por prioridad, `relative_life`,
  `time_since_start_seconds` o `window_index`;
- cada run temporal declara score, umbral, primer aviso, lead time hasta fallo,
  marcador de fallo estimado y conteo de puntos muestreados;
- si faltan predicciones o metadatos temporales, `temporal_series.available`
  queda en `false` con advertencias humanas;
- el frontend muestra un panel `Degradacion / Serie temporal` antes del PCA,
  con curva de score, linea de umbral, primer aviso y fallo;
- el PCA sigue disponible en el mismo endpoint y en la misma pestana.

### Paso 6: agentes conscientes del perfil

Objetivo:

- que el razonamiento agentico use el perfil para elegir modelos, juzgar
  metricas y redactar limitaciones.

Responsables:

- `agents/modeler.py`;
- `agents/evaluator.py`;
- `agents/report_writer.py`;
- `agents/report_verifier.py`;
- `services/agent_tools.py`;
- tests de agentes.

Criterio de aceptacion:

- `modeler` puede decir que optimiza tendencia/alerta, no solo F1;
- `evaluator` no suspende NASA por no tener labels oficiales si hay metricas
  temporales;
- `report_verifier` marca como incidencia cualquier frase que atribuya labels
  oficiales a una politica proxy.

Estado 2026-06-02:

- inventario previo:
  - busquedas realizadas: `supervision_profile`, `label_source`, `F1`,
    `degradation`, `lead_time`, `false_alarm`, `official`, `proxy`;
  - piezas encontradas: `agents/modeler.py`, `agents/evaluator.py`,
    `agents/report_writer.py`, `agents/report_verifier.py` y
    `services/agent_tools.py`;
  - decision: `extend`;
  - motivo: los agentes ya tienen contratos Pydantic estrictos y prompts
    controlados; crear agentes paralelos por perfil duplicaria la orquestacion;
  - impacto en compatibilidad: CWRU conserva la politica binaria recall/FPR y
    el perfil run-to-failure usa reglas adicionales cuando el contexto lo
    declara.
- `modeler` recibe `supervision_profile`, `label_source` y
  `label_granularity` en su contexto; en run-to-failure el fallback usa
  `pca_reconstruction_error` como health indicator interpretable y no permite
  `threshold_calibration` como estrategia principal;
- `evaluator` mantiene los umbrales binarios para
  `binary_fault_classification`, pero en `run_to_failure_degradation` aprueba o
  rechaza con metricas temporales: deteccion antes de fallo, falsa alarma
  nominal y tendencia del score; `min_recall_required` y
  `max_false_positive_rate` quedan en `null` para ese perfil;
- `report_writer` prioriza lead time, falsa alarma nominal y tendencia en la
  seccion de metricas cuando el perfil es temporal, dejando F1 como auxiliar o
  proxy si existe;
- `report_verifier` bloquea afirmaciones de etiquetas oficiales cuando
  `label_source` no es `official`, no solo para NASA IMS;
- `evidence_lookup` expone refs cerradas para `supervision_profile`,
  `label_source`, `label_granularity` y `metric_extra:*`, permitiendo que los
  agentes citen evidencia temporal sin inventar campos.

### Paso 7: run comparativa NASA realista

Objetivo:

- ejecutar una run NASA sobre una secuencia mas larga que la muestra de 3
  ficheros.

Responsables:

- runner comun;
- artefactos de reports;
- visualizacion temporal.

Criterio de aceptacion:

- la run termina con informe;
- produce predicciones, metricas temporales y visualizacion temporal;
- el resultado se interpreta como degradacion run-to-failure, no como benchmark
  binario oficial.

Estado 2026-06-02:

- comprobacion ejecutada con `run_id=fase7-paso7-nasa-common-long-v2` sobre una
  secuencia NASA-like local de 24 snapshots, usando el runner comun y
  `dataset_policy_id=nasa_ims_temporal_v1`;
- resultado: run `completed`, informe en
  `codigo/reports/nasa_ims_bearing/fase7-paso7-nasa-common-long-v2/final_report.md`,
  168 ventanas/predicciones, `metric_families=[
  "binary_classification", "run_to_failure_degradation"]`,
  `degradation_available=true`, lead time medio `13200.9728`, falsa alarma
  nominal media `0.09523809523809523` y tendencia Spearman media `0.6020899873962979`;
- `predictions.csv` conserva `label_source=temporal_proxy` y
  `label_granularity=proxy_temporal`, por lo que `binary_metric_context` ya no
  queda ambiguo;
- el debate controlado queda `approved_without_revision` y la verificacion del
  informe queda `approved`;
- el servicio `build_run_visualization` y una instancia HTTP temporal con el
  codigo actual devuelven `temporal_series.available=true` con 168 puntos;
  el backend que estuviera ya levantado antes de estos cambios debe reiniciarse
  para exponer ese campo por HTTP.

### Paso 8.1: comparacion run-to-failure

Objetivo:

- convertir la comparacion de runs en una primera vista de investigacion
  industrial centrada en degradacion temporal.

Estado 2026-06-03:

- implementado en `codigo/docs/67_fase7_hito8_comparativa_run_to_failure.md`;
- `RunComparisonRow` expone `supervision_profile`, `label_source`,
  `label_granularity`, `model_name`, `metric_families` y resumen de metricas
  temporales;
- `RunComparison` mantiene metricas binarias y anade `degradation_metrics`
  como bloque opcional;
- el frontend muestra primero `Degradacion run-to-failure` cuando existe, con
  lead time, falsas alarmas nominales, tendencia del score, deteccion antes de
  fallo y fallos perdidos;
- las metricas binarias quedan visibles como apoyo/proxy y para mantener
  compatibilidad con CWRU.

### Paso 8.2: monitorizacion de estado de salud

Objetivo:

- traducir la serie temporal de score a estados operacionales por ventana y por
  trayectoria.

Estado 2026-06-03:

- implementado en `codigo/docs/68_fase7_hito8_monitorizacion_estado_salud.md`;
- `TemporalSeriesPoint` incluye ahora `score_ratio`, `risk_index`,
  `health_index`, `health_state` y `state_reason`;
- `TemporalRunSeries` incluye estado actual de la trayectoria, riesgo/salud
  actual, tiempo hasta fallo cuando el replay historico lo trae y conteo de
  puntos en alerta, warning y critico;
- `run_visualization.py` calcula esos campos de forma determinista desde
  `anomaly_score`, `threshold`, `predicted_anomaly` y metadatos temporales;
- el frontend muestra el estado actual en la visualizacion temporal y colorea
  los puntos por `nominal`, `watch`, `warning` o `critical`;
- no se introduce prediccion RUL real: el campo temporal restante solo se usa
  cuando viene del dataset/replay.

## Riesgos y guardarrailes

- No crear un runner `nasa_runner.py`.
- No introducir etiquetas oficiales que no existan.
- No hacer que el frontend lea ficheros internos directamente.
- No eliminar CWRU ni cambiar sus metricas actuales.
- No usar `precision/F1` como metrica principal de NASA salvo en modo proxy
  declarado.
- No saltar a RUL profundo antes de tener series temporales y metricas de
  alerta funcionando.

## Resultado esperado

Al final de este hito, la aplicacion deberia poder decir:

- este dataset es binario supervisado y se evalua con metricas de clasificacion;
- este dataset es run-to-failure y se evalua con metricas de degradacion;
- estas etiquetas son oficiales, proxy, sinteticas o inexistentes;
- esta visualizacion muestra clases, o bien muestra evolucion temporal hacia el
  fallo;
- los agentes razonan dentro de esa frontera metodologica.

Esta separacion convierte NASA IMS en un caso de investigacion serio sin perder
lo que CWRU ya aporta como prueba tecnica reproducible.
