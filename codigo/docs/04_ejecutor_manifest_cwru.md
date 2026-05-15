# Ejecutor de manifiesto CWRU

## Objetivo

Generar el primer artefacto reproducible del pipeline:

```text
codigo/data/interim/cwru_bearing/manifest.csv
```

El manifiesto tiene una fila por fichero `.mat` y conserva los metadatos
necesarios para perfilado, limpieza, estructuracion temporal y evaluacion.

## Implementacion

Archivo principal:

```text
codigo/app/executors/dataset_manifest.py
```

Funciones:

- `build_cwru_manifest(raw_dir, manifest_path=None)`: construye y valida un
  `DatasetManifest` a partir de los `.mat` presentes.
- `generate_cwru_manifest(raw_dir, output_path)`: escribe el CSV y devuelve un
  `ManifestResult`.

El ejecutor no carga senales ni arrays. Solo inspecciona nombres de fichero y
aplica el mapeo oficial CWRU de carga, RPM, tipo de fallo, diametro y posicion
de fallo exterior.

## Decisiones

- Fila por fichero `.mat`.
- Canal principal inicial: `DE_time`.
- Frecuencia objetivo: 12 kHz.
- Normales CWRU: `source_sample_rate_hz = 48000`.
- Fallos descargados de la pagina 12k drive-end:
  `source_sample_rate_hz = 12000`.
- Etiquetado binario inicial:
  - `normal`;
  - `fault`.

## Verificacion

Tests:

```text
codigo/tests/test_dataset_manifest_executor.py
```

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 27 tests
OK
```

Ejecucion real:

```bash
conda run -n tfm_v2 python -c "from codigo.app.executors.dataset_manifest import generate_cwru_manifest; print(generate_cwru_manifest())"
```

Resultado resumido:

```text
status = success
n_rows = 64
label_counts = {'normal': 4, 'fault': 60}
manifest_path = codigo/data/interim/cwru_bearing/manifest.csv
```

El fichero generado tiene 65 lineas contando cabecera.

## Siguiente paso

Implementar el perfilador de datos, que debe leer `manifest.csv`, inspeccionar
los canales reales de cada `.mat` y generar:

```text
codigo/data/interim/cwru_bearing/profile.json
```
