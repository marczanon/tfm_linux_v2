# Ejecutor de limpieza CWRU

## Objetivo

Generar senales limpias a partir de `manifest.csv` y `profile.json`:

```text
codigo/data/processed/cwru_bearing/clean_signals/
```

El ejecutor produce un `.npz` comprimido por fichero y un resumen de auditoria:

```text
codigo/data/processed/cwru_bearing/cleaning_summary.json
```

## Implementacion

Archivo principal:

```text
codigo/app/executors/cleaning.py
```

Funciones:

- `clean_dataset(...)`: limpia cada fila del manifiesto.
- `generate_clean_signals(...)`: escribe artefactos y devuelve un
  `CleaningResult`.

## Operaciones

La configuracion por defecto:

```text
strategy_id = cwru_clean_v1
remove_non_finite = true
resample_to_hz = 12000
normalization = none
```

Para cada fichero:

- carga el canal principal indicado en el manifiesto;
- elimina valores no finitos si aparecen;
- remuestrea a 12 kHz si la frecuencia original es distinta;
- guarda la senal limpia en formato `.npz` comprimido;
- registra conteos, rutas y frecuencias en `cleaning_summary.json`.

## Verificacion

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 36 tests
OK
```

Ejecucion real:

```text
status = success
n_files_cleaned = 64
clean_path = codigo/data/processed/cwru_bearing/clean_signals
```

Resumen:

```text
64 ficheros .npz
tamano procesado aproximado = 19 MB
canal limpiado = DE_time
frecuencia final = 12000 Hz
```

## Siguiente paso

La estructuracion temporal ya esta implementada. El siguiente paso es el
modelado base:

```text
codigo/app/executors/modeling.py
codigo/tests/test_modeling_executor.py
```

Debe entrenar los primeros modelos de deteccion de anomalias sobre las features
temporales generadas.
