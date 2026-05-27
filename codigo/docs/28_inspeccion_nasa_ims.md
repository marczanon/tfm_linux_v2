# Inspeccion local de NASA IMS Bearing Dataset

## Objetivo

Inspeccionar la copia local de NASA IMS antes de implementar
`build_manifest(...)` para `nasa_ims_bearing`. La inspeccion debe fijar la
estructura real de archivos, formato, canales, semantica temporal,
disponibilidad de etiquetas y consecuencias para el futuro selector de datasets
de la aplicacion.

## Fuentes revisadas

Fuente local:

```text
codigo/data/raw/nasa_ims_bearing/4.+Bearings.zip
```

Fuentes de referencia:

- `codigo/data/raw/README.md`
- `Readme Document for IMS Bearing Data.pdf`, incluido dentro del paquete local.
- NASA Open Data Portal: `https://data.nasa.gov/dataset/ims-bearings`
- NASA PCoE Data Set Repository:
  `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/`

## Resultado de inspeccion del contenedor local

El fichero local principal es:

```text
codigo/data/raw/nasa_ims_bearing/4.+Bearings.zip
```

Propiedades observadas:

```text
tamano local: 1.1G
tipo: Zip archive data
contenido zip:
  4. Bearings/
  4. Bearings/IMS.7z
```

El `.zip` no contiene directamente las senales. Contiene un unico archivo
principal `IMS.7z`, de aproximadamente 1.075 GB.

Para inspeccion local se extrajo temporalmente `IMS.7z` a:

```text
/tmp/nasa_ims_inspect/IMS.7z
```

No se modifica el dataset crudo en `codigo/data/raw/`.

## Resultado de inspeccion de IMS.7z

El archivo `IMS.7z` contiene:

```text
1st_test.rar
2nd_test.rar
3rd_test.rar
Readme Document for IMS Bearing Data.pdf
```

Resumen:

```text
1st_test.rar: 366,567,310 bytes
2nd_test.rar:  85,581,092 bytes
3rd_test.rar: 609,047,134 bytes
Readme Document for IMS Bearing Data.pdf: 400,443 bytes
```

El README interno se pudo extraer y leer con `pdftotext`. Los `.rar` se
pudieron listar con `rarfile`, pero no se pudieron extraer muestras de senal
porque el entorno no dispone de una herramienta de extraccion RAR como
`unrar`, `bsdtar`, `7z` o `unar`.

## Estructura documentada por el README interno

El README incluido en el paquete describe tres experimentos test-to-failure.
Cada dataset contiene archivos individuales que son snapshots de vibracion de
1 segundo. Cada fichero contiene 20.480 puntos por canal, con frecuencia de
muestreo de 20 kHz. El nombre de cada fichero indica la fecha y hora de
adquisicion.

Condiciones del banco:

```text
rotacion: 2000 RPM
carga radial: 6000 lbs
rodamiento: Rexnord ZA-2115 double row
lubricacion: forzada
```

Resumen por set segun README:

| Set | Rango temporal | Ficheros | Canales | Fallo final |
| --- | --- | ---: | ---: | --- |
| 1 | 2003-10-22 12:06:24 a 2003-11-25 23:39:56 | 2156 | 8 | bearing 3 inner race; bearing 4 roller element |
| 2 | 2004-02-12 10:32:39 a 2004-02-19 06:22:39 | 984 | 4 | bearing 1 outer race |
| 3 | 2004-03-04 09:27:46 a 2004-04-04 19:01:57 | 4448 | 4 | bearing 3 outer race |

Arreglo de canales:

```text
Set 1:
  Bearing 1 -> Ch 1 y Ch 2
  Bearing 2 -> Ch 3 y Ch 4
  Bearing 3 -> Ch 5 y Ch 6
  Bearing 4 -> Ch 7 y Ch 8

Set 2:
  Bearing 1 -> Ch 1
  Bearing 2 -> Ch 2
  Bearing 3 -> Ch 3
  Bearing 4 -> Ch 4

Set 3:
  Bearing 1 -> Ch 1
  Bearing 2 -> Ch 2
  Bearing 3 -> Ch 3
  Bearing 4 -> Ch 4
```

## Estructura observada en los RAR

Listado local de `1st_test.rar`:

```text
directorio: 1st_test/
ficheros: 2156
primer fichero: 1st_test/2003.10.22.12.06.24
ultimo fichero:  1st_test/2003.11.25.23.39.56
tamano por fichero: ~1.12 MB a ~1.15 MB
```

Listado local de `2nd_test.rar`:

```text
directorio: 2nd_test/
ficheros: 984
primer fichero: 2nd_test/2004.02.12.10.32.39
ultimo fichero:  2nd_test/2004.02.19.06.22.39
tamano por fichero: ~512 KB a ~558 KB
```

Listado local de `3rd_test.rar`:

```text
directorio observado: 4th_test/txt/
ficheros observados: 6324
primer fichero: 4th_test/txt/2004.03.04.09.27.46
ultimo fichero:  4th_test/txt/2004.04.18.02.42.55
tamano por fichero: ~512 KB a ~561 KB
```

Hay una discrepancia relevante entre el README y el archivo local para el tercer
RAR: el README habla de `Set No. 3`, 4448 ficheros y rango hasta
2004-04-04 19:01:57, mientras que `3rd_test.rar` lista 6324 ficheros bajo
`4th_test/txt/` y alcanza 2004-04-18 02:42:55. Antes de generar un manifiesto
real, esta discrepancia debe resolverse o documentarse como variante local del
paquete.

## Formato de senal

Segun el README:

- formato ASCII;
- cada fila representa un punto temporal;
- cada fichero contiene 20.480 puntos;
- frecuencia de muestreo: 20 kHz;
- Set 1 contiene 8 canales;
- Set 2 y Set 3 contienen 4 canales.

No se pudo leer una muestra real de fila desde los `.rar` porque falta una
herramienta local de extraccion RAR. La implementacion del manifiesto puede
usar el listado de archivos para construir metadatos temporales, pero el
perfilado y la validacion de canales reales requeriran extraer o leer ficheros
individuales.

## Etiquetas y semantica

NASA IMS no ofrece etiquetas por ventana como CWRU. La semantica observada es
run-to-failure:

- los datos comienzan en una fase nominal o de degradacion temprana;
- el fallo se conoce al final del experimento;
- la etiqueta exacta por fichero debe definirse metodologicamente.

Propuesta inicial para manifiesto:

```text
label = "unknown" para registros sin criterio temporal definido
label_detail = fallo final conocido del set
task_type = "run_to_failure"
label_availability = "run_level" o "partial"
```

No se deben calcular metricas supervisadas equivalentes a CWRU hasta definir
una politica de etiquetado defendible. Para una primera fase, NASA IMS debe
validar capacidad de ingestion, perfilado, limpieza y estructuracion.

## Estrategia de particion

No debe usarse split aleatorio por ventana, porque las muestras forman una
secuencia temporal de degradacion.

Opciones futuras:

- particion cronologica dentro de cada set;
- entrenar con tramo inicial nominal y evaluar tramos posteriores;
- leave-one-bearing-out si se reformula por rodamiento;
- comparar estrategias solo despues de definir etiquetas temporales.

Regla inicial:

```text
No entrenar ni evaluar NASA IMS hasta definir particion temporal sin fuga.
```

## Implicaciones para la futura interfaz

La aplicacion deberia separar seleccion de dataset, formato de entrada y
adaptador. El usuario no deberia elegir un pipeline interno directamente, sino
subir o seleccionar archivos y ver una previsualizacion estructurada antes de
ejecutar.

Flujo recomendado:

1. El usuario selecciona o sube una ruta/archivo.
2. La aplicacion detecta formato: directorio, `.mat`, `.csv`, `.txt`, `.zip`,
   `.7z`, `.rar` o paquete anidado.
3. El sistema propone uno o mas adaptadores compatibles.
4. El usuario confirma el adaptador si hay ambiguedad.
5. La aplicacion muestra un `DatasetDescriptor` preliminar:
   - dataset candidato;
   - formato;
   - numero de ficheros detectados;
   - canales inferidos;
   - si hay etiquetas suficientes;
   - si se puede generar manifiesto;
   - limitaciones o bloqueos.
6. Solo si el adaptador declara `supports_manifest = true`, se habilita la
   accion de generar manifiesto.

Estados que la interfaz deberia mostrar:

```text
ready_for_manifest
needs_adapter_confirmation
needs_extraction_tool
needs_dataset_inspection
unsupported_format
unsupported_labels
```

Para la copia actual de NASA IMS, la interfaz deberia mostrar:

```text
dataset candidato: nasa_ims_bearing
formato detectado: zip -> 7z -> rar -> ASCII snapshots
estado: needs_extraction_tool / needs_dataset_inspection
accion permitida: inspeccion de contenedor y descriptor preliminar
accion bloqueada: generacion de manifiesto real
motivo: falta extraccion RAR y hay discrepancia README vs RAR 3
```

## Requisitos tecnicos antes de implementar build_manifest

Para implementar `build_manifest(...)` de `nasa_ims_bearing` hay dos caminos:

1. **Requerir dataset preextraido**:
   - entrada: directorios `1st_test/`, `2nd_test/`, `4th_test/txt/` o variante
     normalizada;
   - ventaja: evita dependencias de extraccion en el pipeline;
   - inconveniente: la interfaz debe guiar al usuario para preparar archivos.

2. **Soportar extraccion de archivos anidados**:
   - entrada: `4.+Bearings.zip`;
   - requiere soporte para `zip`, `7z` y `rar`;
   - posible dependencia: `py7zr` para `.7z` y herramienta externa para `.rar`;
   - inconveniente: aumenta superficie operativa y tiempo de ingestion.

Decision recomendada para primera implementacion:

```text
Exigir NASA IMS preextraido para generar manifiesto.
Mantener la inspeccion de paquetes comprimidos como previsualizacion.
```

Esta decision encaja mejor con el MVP local y con la futura interfaz: la app
puede detectar el paquete anidado, explicar el bloqueo y pedir extraccion
controlada antes de ejecutar.

## Propuesta de manifiesto NASA IMS

Columnas comunes:

```text
record_id
dataset
source_path
source_format
label
label_detail
condition_id
asset_id
run_id
timestamp_start
timestamp_end
sampling_rate_hz
target_sample_rate_hz
channel_names
primary_channel
n_channels
metadata_json
notes
```

Valores por set:

```text
dataset = nasa_ims_bearing
source_format = txt
sampling_rate_hz = 20000
target_sample_rate_hz = 12000 o 20000, pendiente de decision
run_id = set_1 | set_2 | set_3_local_variant
condition_id = test_to_failure
label = unknown inicialmente
label_detail = fallo final conocido del set
```

Canales:

```text
set_1: channel_1 ... channel_8
set_2: channel_1 ... channel_4
set_3/local_variant: channel_1 ... channel_4
```

## Criterios de aceptacion para el siguiente paso

Antes de implementar `build_manifest(...)`:

- decidir si se trabaja con dataset preextraido;
- fijar nombres canonicos de sets;
- resolver o documentar la discrepancia del tercer RAR;
- preparar una carpeta temporal sintetica que reproduzca la estructura real;
- escribir tests de manifiesto NASA IMS sobre esa carpeta sintetica;
- no tocar perfilado, limpieza ni estructuracion todavia.

## Implementacion realizada

Se ha creado un ejecutor/adaptador de manifiesto NASA IMS solo para carpetas
preextraidas y sinteticas:

```text
codigo/app/services/dataset_adapters.py
codigo/tests/test_dataset_adapters.py
codigo/tests/test_dataset_manifest_executor.py
```

El primer test debe construir una carpeta temporal con:

```text
nasa_ims_bearing/
  1st_test/
    2003.10.22.12.06.24
  2nd_test/
    2004.02.12.10.32.39
  4th_test/txt/
    2004.03.04.09.27.46
```

y validar que se puede generar un manifiesto sin extraer ni usar el paquete real
completo.

La implementacion:

- rechaza archivos comprimidos y exige una carpeta preextraida;
- genera `manifest.csv` con las columnas de `CommonManifestRecord`;
- usa `label = "unknown"` y `label_detail` con el fallo final conocido del set;
- conserva `sampling_rate_hz = 20000` y `target_sample_rate_hz = 20000`;
- serializa `channel_names` y `metadata_json` como JSON dentro del CSV;
- documenta `4th_test/txt/` como variante local de `set_3`.

## Siguiente paso recomendado

Se ha adaptado el perfilado para leer el manifiesto comun NASA IMS y producir
un resumen de senal con canales, frecuencia, valores no finitos y estadisticos
ligeros, manteniendo el mismo principio: no cargar senales completas dentro del
estado global.

Tambien se ha adaptado la limpieza para leer manifiestos comunes y seleccionar
un canal NASA IMS de forma controlada mediante `CleaningConfig.selected_channel`.
La prueba sintetica usa una carpeta preextraida, genera manifiesto y perfil,
limpia `channel_2` y rechaza un canal no declarado antes de escribir artefactos.

El siguiente paso recomendado es enriquecer el diagnostico agentico de calidad
de senal y mantener NASA IMS limitado a ingestion, perfilado y limpieza hasta
definir una particion temporal y una politica de etiquetas defendibles.

## Avance de diagnostico agentico

El perfilado genera ahora un `decision_summary` para que el agente limpiador
reciba evidencia y opciones soportadas, no solo estadisticos crudos. Para NASA
IMS esto permite distinguir perfiles con varios canales viables, remuestreo
necesario, valores no finitos o calidad insuficiente. La decision final sigue
en el agente, pero el LLM local decide sobre un expediente experto calculado de
forma determinista.

El enfoque general para hacer viables agentes expertos con LLM locales queda en:

```text
codigo/docs/29_agentes_expertos_llm_locales.md
```

## Relacion con estructuracion temporal

El expediente experto se ha extendido tambien al agente estructurador, pero NASA
IMS continua bloqueado para modelado supervisado. El resumen puede proponer
ventanas y advertir sobre fuga temporal, pero no debe usarse para entrenar o
evaluar modelos hasta definir una politica de particion cronologica y etiquetas
defendibles para datos run-to-failure.

## Prueba agentica controlada con Qwen

Para comprobar el comportamiento de los agentes locales ante NASA IMS, se ha
ejecutado una prueba smoke con una carpeta sintetica preextraida compatible con
el formato observado:

```text
python -m codigo.scripts.run_nasa_ims_qwen_smoke \
  --model qwen3.5:4b \
  --run-id nasa-ims-qwen-smoke-fase3-qwen
```

La ejecucion usa el grafo completo y agentes Qwen/Ollama, pero sustituye el
modelado real por un bloqueo metodologico temporal dentro de la prueba. El
objetivo es observar decisiones agenticas, no producir metricas NASA IMS
prematuras.

Snapshot persistido:

```text
codigo/reports/runs/nasa-ims-qwen-smoke-fase3-qwen/
```

Resultado:

- estado final: `failed`;
- motivo: NASA IMS carece de etiquetas por ventana y de una politica temporal
  validada;
- artefactos generados: manifiesto, perfil, senales limpias, log de limpieza,
  features, tensores y splits;
- decisiones registradas: 12, incluyendo 1 decision del limpiador, 1 del
  estructurador, 1 del modelador y 9 del supervisor.

Decisiones relevantes de Qwen:

- el limpiador selecciono `channel_1` porque era el canal preferente del
  manifiesto y no presentaba problemas de calidad;
- el estructurador eligio `window_size = 1024`, `overlap = 0.5` y features
  temporales soportadas, priorizando mas ventanas por fichero y bajo coste;
- el modelador propuso `isolation_forest`, coherente con el unico ejecutor
  disponible, pero aun sin resolver la incompatibilidad metodologica de NASA
  IMS.

La prueba es util precisamente porque no termina en metricas. Demuestra que los
agentes locales pueden usar el contexto experto para tomar decisiones validas,
pero tambien que la incertidumbre metodologica debe elevarse al plano agentico:
autocritica, solicitud de evidencia y propuestas comparables antes de ejecutar.
Por decision de diseno, no se anadira de momento una funcion determinista que
pare al modelador; se priorizara que los agentes aprendan a expresar dudas y
alternativas dentro de contratos estructurados.

## Diagnostico no supervisado de degradacion

Para empezar a trabajar con NASA IMS sin forzar etiquetas por ventana, se ha
anadido un diagnostico no supervisado sobre las features temporales:

```text
python -m codigo.scripts.run_nasa_ims_degradation_diagnostics
```

Este diagnostico no calcula recall, precision ni F1. En su lugar estima una
senal de degradacion relativa a partir de columnas como RMS, energia,
peak-to-peak y curtosis, agregada por fichero temporal.

Resultado de la prueba smoke sintetica:

```text
trend_status = increasing_degradation_signal
early_mean_score = 0.3080
late_mean_score = 0.6866
late_early_ratio = 2.2296
n_files = 3
n_windows = 21
```

Artefactos:

```text
codigo/reports/nasa_ims_bearing/nasa-ims-qwen-smoke-fase3-qwen/degradation/
```

Esta metrica no sustituye una evaluacion supervisada, pero permite comenzar a
comparar decisiones agenticas sobre NASA IMS sin presentar un recall artificial
o metodologicamente debil.

## Benchmark sintetico temporal etiquetado

Para poder ensayar metricas supervisadas sin atribuir etiquetas falsas al NASA
IMS real, se ha creado un benchmark sintetico compatible con la estructura de
NASA IMS Set 2:

```text
codigo/app/services/synthetic_nasa_ims.py
codigo/scripts/run_nasa_ims_synthetic_temporal_benchmark.py
codigo/tests/test_synthetic_nasa_ims.py
```

La carpeta generada mantiene:

- ficheros con nombre temporal tipo `2004.02.12.10.32.39`;
- cuatro canales tabulares;
- frecuencia de muestreo de 20 kHz;
- manifiesto comun `CommonManifestRecord`;
- etiquetas controladas `normal` / `fault` generadas por construccion.

Advertencia metodologica:

```text
Estas etiquetas no son anotaciones oficiales de NASA IMS.
El benchmark solo sirve para probar el flujo multi-dataset con metricas
supervisadas controladas.
```

Ejecucion agentica con Qwen:

```text
python -m codigo.scripts.run_nasa_ims_synthetic_temporal_benchmark \
  --model qwen3.5:4b \
  --run-id nasa-ims-synth-agentic-qwen-fase3
```

Snapshot persistido:

```text
codigo/reports/runs/nasa-ims-synth-agentic-qwen-fase3/
```

Resultados principales:

| Metrica | Valor |
| --- | ---: |
| Precision | 0.9130 |
| Recall | 0.6000 |
| F1-score | 0.7241 |
| ROC-AUC | 0.8041 |
| PR-AUC | 0.8842 |
| FPR | 0.1429 |

Decisiones relevantes de Qwen:

- el limpiador selecciono `channel_1` por ser canal preferente del manifiesto y
  no presentar problemas de calidad;
- el estructurador eligio `window_size = 2048` y `overlap = 0.5`, equilibrando
  resolucion temporal y numero de ventanas;
- el modelador selecciono `isolation_forest` para el conjunto de features de
  ventana;
- el evaluador rechazo la ejecucion porque el recall queda por debajo del
  umbral local y la FPR queda por encima del maximo permitido.

Esta run es util porque produce un caso no trivial: el sistema multiagente no
obtiene un recall perfecto, detecta la insuficiencia y deja la evidencia
persistida para una futura iteracion agentica de configuracion.

## Reintentos agenticos sobre el benchmark sintetico

La iteracion posterior usa la run anterior como origen y entrega al modelador un
analisis de fallo con falsos negativos, falsos positivos, matriz de confusion y
convencion del umbral:

```text
python -m codigo.scripts.run_nasa_ims_agentic_retry \
  --model qwen3.5:4b \
  --source-run-id nasa-ims-synth-agentic-qwen-fase3 \
  --run-id-prefix nasa-ims-synth-agentic-qwen-fase3-retry \
  --max-attempts 2
```

Qwen razono que el fallo principal eran anomalias escapadas y propuso bajar el
umbral de decision. El primer ajuste de `threshold_quantile = 0.95` mejoro
recall y F1, pero tambien aumento la FPR. En el segundo intento, el agente
priorizo demasiado la sensibilidad con `threshold_quantile = 0.50`: recupero
todas las anomalias, pero marco todos los normales de test como anomalos.

| Run | threshold_quantile | Precision | Recall | F1 | FPR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base | 0.99 | 0.9130 | 0.6000 | 0.7241 | 0.1429 |
| Retry 1 | 0.95 | 0.8846 | 0.6571 | 0.7541 | 0.2143 |
| Retry 2 | 0.50 | 0.7143 | 1.0000 | 0.8333 | 1.0000 |

La ejecucion final queda rechazada y se detiene con `next_action = stop` porque
se agotaron los dos reintentos permitidos. Esto deja una evidencia clara para
el TFM: el agente aprende de su error y actua sobre el umbral en la direccion
correcta, pero la aplicacion no confunde mejora de recall con aprobacion
industrial si las falsas alarmas se disparan.

Sobre estos reintentos se ha generado tambien un post-mortem de razonamiento.
El primer reintento queda clasificado automaticamente como `partially_supported`
y el segundo como `overcorrected`. Con el trigger de revision humana se han
creado solicitudes para que una persona decida si el razonamiento debe
reutilizarse como contexto positivo, negativo o caso frontera:

```text
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-01/iteration/reasoning_postmortem.md
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/iteration/reasoning_postmortem.md
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/iteration/human_reasoning_review_request.md
```

Finalmente, los snapshots NASA se han normalizado para usar nombres de
artefactos neutrales (`windows_features`, `model_predictions`,
`evaluation_metrics`, etc.) en lugar de nombres heredados `cwru_*`. Esto no
modifica rutas ni metricas, pero mejora la trazabilidad multi-dataset y evita
que una run NASA parezca acoplada al benchmark CWRU.
