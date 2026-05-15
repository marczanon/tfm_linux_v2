# Diseno del pipeline de datos

## Objetivo

Definir el flujo reproducible que convierte datos crudos de vibracion en
artefactos listos para perfilado, limpieza, estructuracion temporal,
modelado, evaluacion e informes tecnicos.

El MVP usara CWRU Bearing Dataset como caso principal de deteccion de
anomalias en rodamientos de motores electricos. NASA IMS Bearing Dataset queda
reservado como dataset de validacion/extension para una fase posterior de
degradacion run-to-failure.

## Datasets

### CWRU Bearing Dataset

- Uso: dataset principal del MVP.
- Ruta cruda: `codigo/data/raw/cwru_bearing/mat/`
- Formato original: MATLAB `.mat`.
- Senal principal para el MVP: canal de aceleracion `DE_time` cuando este
  disponible.
- Etiquetado inicial:
  - `normal`: operacion sin fallo.
  - `fault`: cualquier fallo de rodamiento.
- Metadatos que se deben conservar:
  - tipo de fallo: pista interior, bola o pista exterior.
  - diametro de fallo.
  - carga del motor.
  - RPM.
  - frecuencia de muestreo original.
  - canal de sensor usado.

### NASA IMS Bearing Dataset

- Uso: validacion futura.
- Ruta cruda: `codigo/data/raw/nasa_ims_bearing/4.+Bearings.zip`
- Estado actual: conservar comprimido hasta que el MVP local este operativo.
- Papel previsto: evaluar degradacion progresiva y robustez temporal del flujo.

## Flujo objetivo

```text
datos .mat crudos
-> manifiesto del dataset
-> extraccion de senales
-> normalizacion de frecuencia de muestreo
-> perfilado estadistico
-> limpieza determinista
-> generacion de ventanas temporales
-> features tabulares y tensores
-> particiones train/validation/test
-> modelos base de anomalias
-> evaluacion de metricas
-> informe tecnico
```

## Artefactos

Los datos crudos se mantienen inmutables. Cualquier salida generada por el
pipeline debe guardarse fuera de `codigo/data/raw/`.

```text
codigo/data/interim/cwru_bearing/manifest.csv
codigo/data/interim/cwru_bearing/profile.json
codigo/data/interim/cwru_bearing/extracted_signals/
codigo/data/processed/cwru_bearing/clean_signals/
codigo/data/tensors/cwru_bearing/windows_features.csv
codigo/data/tensors/cwru_bearing/windows_raw.npz
codigo/data/tensors/cwru_bearing/splits.json
codigo/reports/cwru_bearing/
codigo/models/cwru_bearing/
```

## Manifiesto

El primer artefacto implementable debe ser `manifest.csv`. Debe tener una fila
por fichero `.mat` y actuar como contrato entre datos crudos, ejecutores,
agentes y memoria academica.

Columnas recomendadas:

```text
file_id
dataset
source_path
label
fault_type
fault_diameter_inch
load_hp
rpm
sensor_channel
source_sample_rate_hz
target_sample_rate_hz
source_format
notes
```

Criterios:

- `label` sera `normal` o `fault` para el MVP.
- `fault_type` sera `null` en datos normales.
- `target_sample_rate_hz` sera `12000` en el MVP.
- Las rutas deben ser relativas al repositorio cuando sea posible.

## Extraccion de senales

Cada fichero `.mat` debe convertirse en una representacion tabular o array
controlada por ejecutores deterministas.

Reglas iniciales:

- Priorizar `DE_time` como canal principal.
- Registrar si un fichero no contiene el canal esperado.
- No modificar el fichero `.mat` original.
- Guardar senales extraidas en `codigo/data/interim/cwru_bearing/`.
- Mantener identificador de fichero y metadatos en cada salida.

## Perfilado

El perfilado no debe cargar datos completos en el estado de LangGraph. El
ejecutor genera `profile.json` con resumenes:

```text
numero de ficheros
numero de muestras por fichero
canales detectados
valores nulos o no finitos
minimo, maximo, media y desviacion tipica
RMS
curtosis
factor de cresta
energia
frecuencias de muestreo detectadas
conteo por etiqueta, carga y tipo de fallo
```

## Limpieza

La limpieza debe ser reproducible y configurada mediante esquemas estrictos.
Para el MVP:

- Validar que la senal es numerica y finita.
- Eliminar o marcar ficheros corruptos.
- Corregir diferencias de frecuencia de muestreo mediante una configuracion
  explicita.
- Aplicar normalizacion estadistica despues de definir particiones para evitar
  fuga de informacion.
- Registrar todas las operaciones en un log o artefacto de auditoria.

## Estructuracion temporal

Configuracion inicial recomendada:

```text
target_sample_rate_hz = 12000
window_size = 2048 o 4096 muestras
overlap = 0.5
main_channel = DE_time
label_mode = binary_anomaly
```

Salidas:

- `windows_features.csv`: una fila por ventana con features estadisticas.
- `windows_raw.npz`: tensores de ventanas crudas para modelos posteriores.
- `splits.json`: definicion reproducible de particiones.

## Features iniciales

Para los modelos base se usaran features de bajo coste y trazables:

```text
mean
std
rms
min
max
peak_to_peak
skewness
kurtosis
crest_factor
energy
```

En una fase posterior se podran anadir features frecuenciales, como potencia
por bandas, frecuencia dominante o energia espectral.

## Particiones

Evitar particiones aleatorias ingenuas por ventana, porque ventanas vecinas
pueden compartir informacion.

Estrategia inicial:

```text
train: ventanas normales
validation: ventanas normales retenidas para calibrar umbral
test: ventanas normales retenidas + ventanas con fallo
```

Estrategia posterior:

```text
leave-one-load-out
leave-one-fault-type-out
```

## Modelado inicial

Modelos base para el MVP:

```text
Isolation Forest
One-Class SVM
Local Outlier Factor
PCA reconstruction error
```

Modelos posteriores:

```text
autoencoder denso
LSTM autoencoder
```

## Evaluacion

Metricas iniciales:

```text
precision
recall
f1_score
roc_auc
pr_auc
false_positive_rate
confusion_matrix
```

Criterio industrial:

- Priorizar recall alto en fallos.
- Controlar falsos positivos.
- Mantener trazabilidad entre ventanas, fichero original, carga y tipo de
  fallo.

## Encaje con LangGraph

El grafo no debe transportar senales completas. El estado compartido debe usar
rutas y resumenes:

```text
raw_path
manifest_path
profile_path
clean_path
tensor_path
metrics
artifacts
errors
```

Los agentes propondran configuraciones validadas con Pydantic. Los ejecutores
aplicaran esas configuraciones y devolveran rutas, metricas y logs.

## Siguiente entrega implementable

Los ejecutores de manifiesto, perfilado, limpieza, estructuracion temporal,
modelado base y evaluacion ya estan implementados. La siguiente tarea tecnica
deberia ser montar el grafo LangGraph minimo:

```text
codigo/app/graph/pipeline.py
codigo/tests/test_graph_pipeline.py
```

Este grafo debe encadenar los ejecutores deterministas y preparar los puntos
donde despues entraran los agentes.

## Fuentes

- CWRU Bearing Data Center: https://engineering.case.edu/bearingdatacenter/welcome
- CWRU normal baseline data:
  https://engineering.case.edu/bearingdatacenter/normal-baseline-data
- CWRU 12k drive-end fault data:
  https://engineering.case.edu/bearingdatacenter/12k-drive-end-bearing-fault-data
- NASA PCoE Data Set Repository:
  https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
