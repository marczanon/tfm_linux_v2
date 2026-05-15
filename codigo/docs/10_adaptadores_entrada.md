# Adaptadores de entrada

## Objetivo

Separar el formato fisico del fichero de la logica del pipeline. Los ejecutores
de perfilado y limpieza ya no cargan `.mat` directamente; piden canales
numericos a:

```text
codigo/app/services/signal_adapters.py
```

Esto permite incorporar nuevos origenes creando o ampliando adaptadores, sin
reescribir perfilado, limpieza, estructuracion, modelado ni evaluacion.

## Formatos soportados inicialmente

```text
.mat
.csv
.txt
.tsv
.npz
```

Reglas actuales:

- `.mat`: reconoce claves CWRU `DE_time`, `FE_time`, `BA_time` y `RPM`.
- `.csv`, `.txt`, `.tsv`: toma columnas numericas como canales.
- `.npz`: usa `signal` y `channel` si existen, o arrays numericos por clave.

## Uso desde ejecutores

Perfilado:

```text
read_signal_channels(path)
```

Limpieza:

```text
load_signal_channel(path, channel)
```

El manifiesto sigue indicando `source_path`, `sensor_channel`,
`source_sample_rate_hz` y `source_format`. El adaptador solo resuelve como leer
el fichero fisico.

## Como anadir un formato

Para soportar otro origen, por ejemplo NASA IMS, el camino recomendado es:

1. Crear un manifiesto especifico del dataset.
2. Anadir la lectura del formato en `signal_adapters.py` si no existe.
3. Hacer que el adaptador devuelva canales numericos normalizados.
4. Mantener igual el resto del pipeline.

La meta es que cada dataset tenga un adaptador de entrada pequeno y que el
pipeline comun trabaje siempre con canales, rutas y artefactos estandarizados.

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

Los tests cubren lectura de `.mat`, `.csv`, uso del adaptador desde perfilado y
limpieza, y rechazo de formatos no soportados.
