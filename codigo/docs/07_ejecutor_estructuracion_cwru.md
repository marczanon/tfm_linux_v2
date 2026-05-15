# Ejecutor de estructuracion temporal CWRU

## Objetivo

Generar ventanas, features y particiones reproducibles a partir de las senales
limpias:

```text
codigo/data/processed/cwru_bearing/clean_signals/
```

El ejecutor produce tres artefactos:

```text
codigo/data/tensors/cwru_bearing/windows_features.csv
codigo/data/tensors/cwru_bearing/windows_raw.npz
codigo/data/tensors/cwru_bearing/splits.json
```

## Implementacion

Archivo principal:

```text
codigo/app/executors/structuring.py
```

Funciones:

- `build_temporal_dataset(...)`: genera ventanas, features y splits.
- `generate_temporal_structure(...)`: escribe artefactos y devuelve un
  `StructuringResult`.

## Configuracion por defecto

```text
window_size = 2048
overlap = 0.5
main_channel = DE_time
target_sample_rate_hz = 12000
label_mode = binary_anomaly
```

Features iniciales:

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

## Particiones

La particion se hace a nivel de fichero para evitar mezclar ventanas del mismo
archivo entre train, validation y test. La estrategia inicial es:

- train: ventanas normales de ficheros de entrenamiento;
- validation: ventanas normales retenidas;
- test: ventanas normales retenidas y todas las ventanas con fallo.

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
n_windows = 7460
features_path = codigo/data/tensors/cwru_bearing/windows_features.csv
tensors_path = codigo/data/tensors/cwru_bearing/windows_raw.npz
splits_path = codigo/data/tensors/cwru_bearing/splits.json
```

Resumen:

```text
windows_raw shape = (7460, 2048)
train windows = 175
validation windows = 117
test windows = 7168
tamano aproximado = 22 MB
```

## Siguiente paso

El modelado base y la evaluacion ya estan implementados. El siguiente paso es
el grafo minimo:

```text
codigo/app/graph/pipeline.py
codigo/tests/test_graph_pipeline.py
```

Debe conectar las fases deterministas y preparar los nodos agenticos futuros.
