# Ejecutor de perfilado CWRU

## Objetivo

Generar un perfil estadistico ligero a partir del manifiesto:

```text
codigo/data/interim/cwru_bearing/profile.json
```

El perfil resume canales, tamanos, frecuencias, etiquetas y estadisticas
basicas sin guardar senales completas.

## Implementacion

Archivo principal:

```text
codigo/app/executors/data_profiler.py
```

Funciones:

- `build_data_profile(manifest_path)`: lee `manifest.csv`, inspecciona los
  `.mat` y devuelve un diccionario JSON-serializable.
- `generate_data_profile(manifest_path, output_path)`: escribe `profile.json`
  y devuelve un `ProfileResult`.

## Estadisticas por canal

Para cada canal reconocido (`DE_time`, `FE_time`, `BA_time`, `RPM`) se guardan:

```text
source_key
shape
n_samples
non_finite_count
min
max
mean
std
rms
kurtosis
energy
```

No se guardan arrays ni muestras de senal.

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
n_files_profiled = 64
profile_path = codigo/data/interim/cwru_bearing/profile.json
```

Resumen del perfil generado:

```text
n_files = 64
label_counts = {'normal': 4, 'fault': 60}
sample_rate_counts = {'48000': 4, '12000': 60}
channels_detected = ['BA_time', 'DE_time', 'FE_time', 'RPM']
```

## Siguiente paso

El ejecutor de limpieza, la estructuracion temporal, el modelado base y la
evaluacion ya estan implementados. El siguiente paso es el grafo minimo:

```text
codigo/app/graph/pipeline.py
codigo/tests/test_graph_pipeline.py
```

Debe encadenar los ejecutores deterministas y actualizar el estado compartido.
