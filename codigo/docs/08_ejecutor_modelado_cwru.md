# Ejecutor de modelado CWRU

## Objetivo

Entrenar el primer modelo base de deteccion de anomalias sobre las features
temporales:

```text
codigo/data/tensors/cwru_bearing/windows_features.csv
```

El ejecutor produce tres artefactos:

```text
codigo/models/cwru_bearing/isolation_forest.joblib
codigo/models/cwru_bearing/predictions.csv
codigo/models/cwru_bearing/modeling_summary.json
```

## Implementacion

Archivo principal:

```text
codigo/app/executors/modeling.py
```

Funciones:

- `train_anomaly_model(...)`: entrena el modelo y guarda artefactos.
- `generate_model_outputs(...)`: devuelve un `ModelingResult` estructurado.

## Modelo inicial

El primer modelo implementado es `isolation_forest`. La configuracion por
defecto usa:

```text
n_estimators = 200
max_samples = auto
contamination = auto
max_features = 1.0
bootstrap = false
n_jobs = 1
threshold_quantile = 0.99
random_state = 42
```

El entrenamiento usa solo ventanas normales del split `train`. El umbral de
anomalia se estima con el cuantil configurado sobre las ventanas de
`validation` si existen; si no existen, se usa `train`.

## Predicciones

`predictions.csv` conserva trazabilidad por ventana:

```text
window_id
file_id
split
label
target
fault_type
anomaly_score
threshold
predicted_anomaly
```

Las predicciones son la entrada del ejecutor de evaluacion, que mantiene
separadas las responsabilidades de modelado y medicion.

## Verificacion

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 48 tests
OK
```

Ejecucion real:

```text
status = success
model_path = codigo/models/cwru_bearing/isolation_forest.joblib
predictions_path = codigo/models/cwru_bearing/predictions.csv
```

Resumen:

```text
model_name = isolation_forest
train windows = 175
predictions = 7460
threshold = 0.6334401531945375
predicted normal = 403
predicted anomaly = 7057
tamano aproximado = 2.8 MB
```

## Siguiente paso

La evaluacion ya esta implementada. El siguiente paso es montar el grafo minimo:

```text
codigo/app/graph/pipeline.py
codigo/tests/test_graph_pipeline.py
```

Debe encadenar los ejecutores existentes y preparar los puntos donde despues
entraran supervisor y agentes especializados.
