# Diseno de soporte multi-dataset

## Objetivo

Definir la frontera tecnica para que el pipeline deje de estar acoplado a CWRU
sin perder reproducibilidad, trazabilidad ni seguridad. Este documento es el
primer paso operativo historico de la Fase 3 y sigue siendo referencia en Fase
4 antes de modificar `dataset_manifest.py`, `data_profiler.py`, `cleaning.py`,
`structuring.py`, el runner comun o la API de ejecucion.

Estado inicial: implementados los contratos comunes `DatasetDescriptor`,
`DatasetAdapterInfo` y `CommonManifestRecord`, junto con el registro local
`dataset_adapters.py` y pruebas sinteticas para CWRU, NASA IMS y senales
tabulares genericas.

Estado de integracion CWRU: implementado `generate_dataset_manifest(...)` como
wrapper comun en `dataset_manifest.py`; el adaptador `cwru_bearing` delega en
`generate_cwru_manifest(...)` y los tests comprueban que el CSV resultante es
equivalente al generado por el ejecutor historico.

Estado NASA IMS sintetico: el adaptador puede reconocer rutas con indicadores
`nasa`/`ims` o ficheros con formato temporal tipo IMS, inferir canales desde
ficheros pequenos, registrar numero de ficheros candidatos, extensiones logicas
y recuentos de canales, y detectar inconsistencias basicas entre ficheros.
Ademas, genera un manifiesto comun para carpetas preextraidas con estructuras
`1st_test/`, `2nd_test/` y `4th_test/txt/`, manteniendo bloqueada la ingestion
directa del paquete anidado `zip -> 7z -> rar`.

El objetivo no es ejecutar todavia un nuevo dataset, sino fijar:

- contrato comun de descriptor de dataset;
- formato esperado de manifiesto comun;
- registro de adaptadores;
- estrategia inicial para NASA IMS;
- compatibilidad con CWRU;
- pruebas minimas antes de ejecutar datos reales.

## Principio arquitectonico

El pipeline debe distinguir tres niveles:

1. **Dataset crudo**: estructura original de ficheros, nombres, canales,
   metadatos y etiquetas disponibles.
2. **Adaptador de dataset**: codigo determinista que inspecciona el dataset y
   lo traduce a contratos comunes.
3. **Pipeline comun**: perfilado, limpieza, estructuracion, modelado,
   evaluacion, persistencia y reporting usando rutas y contratos estables.

Los agentes no deben interpretar directamente carpetas crudas ni nombres de
fichero. Deben recibir resumenes estructurados generados por adaptadores y
perfiladores deterministas.

## Contrato comun de descriptor de dataset

Se propone introducir un descriptor ligero, validado con Pydantic, que describa
el dataset antes de generar el manifiesto.

Ubicacion candidata:

```text
codigo/app/schemas/dataset.py
```

Modelo candidato:

```text
DatasetDescriptor
```

Campos propuestos:

```text
dataset_id: str
dataset_name: str
domain: str
asset_type: str
raw_path: str
source_format: str
adapter_id: str
label_availability: str
task_type: str
sampling_rate_hz: float | null
channel_names: list[str]
has_multiple_conditions: bool
has_run_to_failure: bool
metadata: dict[str, str | int | float | bool | null]
notes: list[str]
```

Valores candidatos para campos controlados:

```text
domain = "rotating_machinery" | "industrial_time_series" | "unknown"
asset_type = "bearing" | "motor" | "turbine" | "pump" | "unknown"
source_format = "mat" | "csv" | "txt" | "tsv" | "npz" | "directory"
label_availability = "file_level" | "window_level" | "run_level" | "none" | "partial"
task_type = "binary_anomaly" | "multiclass_fault" | "run_to_failure" | "unknown"
```

Reglas:

- `dataset_id` debe ser estable y usable en rutas.
- `raw_path` debe apuntar a una ruta local permitida.
- `adapter_id` debe existir en el registro de adaptadores.
- `sampling_rate_hz` puede ser `null` si debe inferirse por fichero o si el
  dataset no declara frecuencia unica.
- `metadata` no debe contener arrays ni senales completas.

## Formato comun de manifiesto

El manifiesto comun debe seguir siendo un CSV ligero, con una fila por unidad
cruda procesable. En CWRU la unidad es un fichero `.mat`; en NASA IMS puede ser
un fichero temporal, un segmento o una lectura concreta segun el adaptador.

Ruta esperada:

```text
codigo/data/interim/<dataset_id>/manifest.csv
```

Columnas comunes obligatorias:

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

Semantica:

- `record_id`: identificador unico y estable dentro del dataset.
- `dataset`: coincide con `dataset_id`.
- `source_path`: ruta local al fichero crudo o unidad procesable.
- `label`: valor normalizado para evaluacion inicial, por ejemplo `normal`,
  `fault`, `unknown` o `degradation`.
- `label_detail`: tipo de fallo, condicion o descripcion si existe.
- `condition_id`: condicion experimental, carga, velocidad, severidad o banco.
- `asset_id`: maquina, rodamiento, canal de banco o unidad fisica si aplica.
- `run_id`: ejecucion temporal o secuencia de degradacion si aplica.
- `timestamp_start` y `timestamp_end`: ISO 8601 si existe tiempo real; vacio si
  no aplica.
- `sampling_rate_hz`: frecuencia original de esa unidad si se conoce.
- `target_sample_rate_hz`: frecuencia objetivo propuesta para el pipeline.
- `channel_names`: lista serializada JSON de canales disponibles.
- `primary_channel`: canal recomendado por adaptador o agente.
- `n_channels`: numero de canales numericos disponibles.
- `metadata_json`: JSON compacto con metadatos especificos del dataset.
- `notes`: observaciones humanas o advertencias de adaptador.

Columnas especificas permitidas:

Los adaptadores pueden anadir columnas especificas siempre que no sustituyan a
las comunes. Ejemplos:

```text
fault_diameter_inch
fault_location
load_hp
rpm
bearing_id
test_id
measurement_index
```

Reglas:

- El pipeline comun debe depender solo de las columnas obligatorias.
- Los agentes pueden usar columnas especificas como contexto, pero no deben
  asumir que existen en todos los datasets.
- `metadata_json` debe ser JSON valido.
- No se guardan senales ni arrays dentro del manifiesto.

## Registro de adaptadores

Se propone formalizar un registro local de adaptadores. El codigo ya dispone de
`signal_adapters.py` para lectura de formatos; Fase 3 debe introducir una capa
superior para datasets.

Ubicacion candidata:

```text
codigo/app/services/dataset_adapters.py
```

Interfaz candidata:

```text
DatasetAdapter
```

Operaciones:

```text
adapter_id() -> str
supports(raw_path: Path) -> bool
describe(raw_path: Path) -> DatasetDescriptor
build_manifest(raw_path: Path, output_dir: Path) -> ManifestResult
```

Adaptadores iniciales:

```text
cwru_bearing
nasa_ims_bearing
generic_tabular_signal
```

Funcion de registro candidata:

```text
get_dataset_adapter(adapter_id: str) -> DatasetAdapter
infer_dataset_adapter(raw_path: Path) -> DatasetAdapter
list_dataset_adapters() -> list[DatasetAdapterInfo]
```

Reglas:

- La inferencia automatica puede sugerir un adaptador, pero la ejecucion real
  debe registrar que adaptador se uso.
- Si hay ambiguedad, el sistema debe pedir decision estructurada o Human Review,
  no adivinar silenciosamente.
- Los adaptadores no deben modificar datos crudos.
- Los adaptadores no deben llamar a LLMs.

## Estrategia para CWRU

CWRU debe convertirse en el primer adaptador registrado sin romper el flujo
actual.

Decision:

- mantener `generate_cwru_manifest(...)` como implementacion ya verificada;
- envolverla en un adaptador `cwru_bearing` cuando se implemente la capa
  multi-dataset;
- preservar las columnas historicas de CWRU;
- anadir o derivar columnas comunes donde sea necesario;
- conservar CWRU como benchmark de regresion.

Criterio de compatibilidad:

- los tests actuales de CWRU deben seguir pasando;
- las rutas existentes no deben cambiar;
- los runs persistidos existentes deben seguir siendo consultables;
- el grafo actual debe poder ejecutarse con el adaptador CWRU sin cambios de
  comportamiento observable.

## Estrategia para NASA IMS

NASA IMS se usara como primer candidato para validar datasets mas complejos,
pero no se deben codificar supuestos rigidos hasta inspeccionar la copia local y
su documentacion asociada.

Objetivo inicial:

- trabajar primero con un subconjunto pequeno;
- generar descriptor y manifiesto;
- perfilar canales sin modelado costoso;
- comprobar si el pipeline puede manejar series largas y condiciones de
  degradacion;
- documentar limitaciones de etiquetas y particionado.

Supuestos que deben validarse antes de implementar:

- estructura exacta de carpetas;
- formato de cada fichero;
- numero de canales;
- frecuencia de muestreo declarada;
- granularidad de etiquetas;
- existencia de secuencias run-to-failure;
- criterio para definir `normal`, `degradation` o `fault`;
- estrategia de particion sin fuga temporal.

Decision provisional:

- `dataset_id = "nasa_ims_bearing"`;
- `asset_type = "bearing"`;
- `task_type = "run_to_failure"` o `binary_anomaly` segun el subconjunto y las
  etiquetas disponibles;
- `label_availability = "run_level"` o `partial` si no hay etiqueta por
  fichero;
- `adapter_id = "nasa_ims_bearing"`.

Salida minima esperada:

```text
codigo/data/interim/nasa_ims_bearing/descriptor.json
codigo/data/interim/nasa_ims_bearing/manifest.csv
codigo/data/interim/nasa_ims_bearing/profile.json
```

Regla metodologica:

No se deben comparar metricas de NASA IMS contra CWRU como si fueran el mismo
problema. Primero se validara que el pipeline y los agentes pueden describir,
limpiar y estructurar el dataset. La evaluacion cuantitativa vendra despues de
definir etiquetas y particiones defendibles.

## Compatibilidad con agentes

El soporte multi-dataset debe aumentar el poder de los agentes solo despues de
darles contexto estructurado.

Entradas nuevas candidatas para agentes:

```text
dataset_descriptor
manifest_summary
quality_diagnostics
adapter_capabilities
supported_model_registry
```

Decisiones candidatas:

```text
DatasetSelectionDecision
ChannelSelectionDecision
StructuringStrategyDecision
ExperimentPlanDecision
UnsupportedCapabilityDecision
```

Guardarrailes:

- el agente puede recomendar adaptador, canal, ventana, features o modelo;
- el agente no puede leer carpetas crudas por su cuenta;
- el agente no puede crear columnas de manifiesto no soportadas;
- el agente no puede decidir que un dataset tiene etiquetas suficientes sin que
  el adaptador o el perfil lo confirmen;
- si faltan etiquetas o metadatos, debe devolver una limitacion explicita.

## Cambios esperados por modulo

No se implementan en este paso, pero el diseno anticipa estos cambios:

```text
codigo/app/schemas/dataset.py
  - DatasetDescriptor
  - DatasetAdapterInfo
  - ManifestRecord comun

codigo/app/services/dataset_adapters.py
  - registro de adaptadores
  - adaptador CWRU
  - adaptador NASA IMS inicial

codigo/app/executors/dataset_manifest.py
  - mantener CWRU
  - anadir capa comun sin romper generate_cwru_manifest

codigo/app/executors/data_profiler.py
  - aceptar manifiestos comunes
  - resumir calidad de senal por dataset heterogeneo

codigo/app/agents/cleaner.py
codigo/app/agents/structurer.py
codigo/app/agents/modeler.py
  - consumir descriptor y resumen de manifiesto cuando existan
```

## Pruebas minimas antes de datos reales

Tests unitarios:

- `DatasetDescriptor` acepta un caso CWRU y un caso NASA IMS sintetico;
- el registro lista adaptadores conocidos;
- pedir un adaptador inexistente devuelve error claro;
- un manifiesto comun sintetico valida columnas obligatorias;
- `metadata_json` invalido se rechaza;
- `channel_names` debe ser JSON de lista de strings.

Tests de compatibilidad CWRU:

- `generate_cwru_manifest(...)` sigue generando el manifiesto actual;
- el adaptador CWRU produce descriptor compatible;
- el pipeline CWRU actual sigue pasando la suite existente;
- los tests de persistencia y API no cambian.

Tests con NASA IMS sintetico:

- crear una carpeta temporal con dos o tres ficheros pequenos;
- construir descriptor y manifiesto sin descargar dataset real;
- perfilar canales numericos;
- comprobar que no se cargan arrays en el estado global.

Validacion con datos reales:

- usar primero un subconjunto pequeno;
- ejecutar solo manifiesto y perfilado;
- revisar artefactos manualmente;
- no lanzar modelado hasta definir particiones y etiquetas.

## Artefactos esperados

Para cada dataset soportado:

```text
codigo/data/interim/<dataset_id>/descriptor.json
codigo/data/interim/<dataset_id>/manifest.csv
codigo/data/interim/<dataset_id>/profile.json
codigo/reports/runs/<run_id>/state_final.json
codigo/reports/runs/<run_id>/artifacts.json
codigo/reports/runs/<run_id>/summary.md
```

Para experimentos posteriores:

```text
codigo/experiments/<dataset_id>/<plan_id>/experiment_plan.json
codigo/experiments/<dataset_id>/<plan_id>/comparison.json
codigo/experiments/<dataset_id>/<plan_id>/results_table.md
```

## Orden de implementacion recomendado

1. Anadir contratos Pydantic de descriptor y registro de adaptadores.
2. Crear tests sinteticos de descriptor y manifiesto comun.
3. Implementar adaptador CWRU como envoltorio del manifiesto actual.
4. Verificar que CWRU no cambia.
5. Crear adaptador NASA IMS minimo sobre datos sinteticos.
6. Validar descriptor y manifiesto NASA IMS con una carpeta temporal.
7. Ejecutar perfilado sobre un subconjunto real cuando este disponible.
8. Documentar limitaciones observadas antes de limpiar, estructurar o modelar.

## Siguiente paso tecnico

Tras preparar el adaptador NASA IMS minimo sobre datos sinteticos, se inspecciono
la copia local/documental de NASA IMS:

```text
codigo/docs/28_inspeccion_nasa_ims.md
```

Ya se ha implementado `build_manifest(...)` para `nasa_ims_bearing` trabajando
solo con carpetas preextraidas y sinteticas. La ingestion directa del paquete
anidado `zip -> 7z -> rar` queda pospuesta hasta decidir dependencias y
experiencia de interfaz.

Tambien se ha adaptado el perfilado para consumir el manifiesto comun NASA IMS
y validar, sobre una carpeta sintetica preextraida, que los resumenes de
canales, frecuencia, etiquetas y estadisticos ligeros quedan persistidos sin
cargar senales completas en el estado global. Los snapshots IMS sin extension se
leen como tablas numericas mediante la capa de adaptadores de senal, incluyendo
una funcion publica `read_signal_frame(...)` para inspeccionarlos como
`DataFrame`.

Tambien se ha adaptado la limpieza para consumir tanto el manifiesto historico
CWRU como el manifiesto comun. El contrato `CleaningConfig` incorpora
`selected_channel`, de modo que NASA IMS puede limpiarse sobre un canal
declarado (`channel_1`, `channel_2`, etc.) sin inferencias libres ni cambios ad
hoc en el ejecutor. Si el canal pedido no aparece en `channel_names`, la
ejecucion se rechaza antes de escribir artefactos.

Tambien se ha enriquecido el perfilado con un `decision_summary` orientado al
agente limpiador. Este resumen traduce los estadisticos en un expediente de
decision con estado de calidad, acciones requeridas, canales candidatos,
opciones de limpieza soportadas y advertencias bloqueantes o no bloqueantes. El
objetivo es que un LLM local no tenga que conocer NASA IMS de memoria: decide
sobre evidencia calculada y opciones validas. El criterio general queda
documentado en `codigo/docs/29_agentes_expertos_llm_locales.md`.

Tambien se ha extendido el patron al agente estructurador sobre senales limpias.
El resumen de decision propone configuraciones de ventana y solape dentro de
rangos soportados, estima numero de ventanas y coste, enumera conjuntos de
features temporales ejecutables y advierte sobre fuga de informacion por
fichero, run o secuencia temporal. NASA IMS sigue sin pasar a modelado hasta
definir particion temporal y politica de etiquetas defendibles.

El siguiente paso tecnico sera ejecutar y persistir, sobre CWRU, al menos dos
configuraciones de ventana propuestas por este expediente para comprobar que son
comparables antes de generalizar el flujo.

## Decision de Fase 4: runner comun para API e interfaz

Tras extender la memoria agentica a varios agentes, se ha fijado la forma de
ejecucion que debera usar una futura API o interfaz grafica. La decision es no
crear una aplicacion separada por dataset. Se mantiene un runner comun que
recibe una peticion explicita, resuelve el adaptador y aplica una politica de
capacidades antes de ejecutar.

Implementacion inicial:

```text
codigo/app/schemas/pipeline_run.py
codigo/app/services/pipeline_runner.py
codigo/scripts/run_dataset_pipeline_with_memory.py
codigo/tests/test_pipeline_runner.py
```

Contratos principales:

```text
PipelineRunRequest
DatasetRunPolicy
DatasetCapabilityRule
DatasetPipelinePaths
DatasetPipelinePlan
```

La futura interfaz podra usar este flujo:

```text
seleccion de dataset/adaptador/ruta
-> PipelineRunRequest
-> plan_dataset_pipeline_run(...)
-> mostrar descriptor, capacidades y bloqueos
-> ejecutar solo si can_execute_requested_stages=true
```

Reglas adoptadas:

- el usuario o la UI seleccionan `dataset_id` y opcionalmente `adapter_id`;
- la inferencia de adaptador solo se usa cuando no hay ambiguedad;
- si `adapter_id` y `dataset_id` no coinciden, la planificacion falla antes de
  ejecutar;
- las rutas se derivan de forma canonica por `dataset_id/run_id`;
- CWRU permite el pipeline supervisado completo;
- NASA IMS real permite manifiesto, perfilado, limpieza y estructuracion, pero
  bloquea modelado y evaluacion supervisados hasta tener politica temporal y
  etiquetas defendibles;
- NASA IMS puede habilitar una ejecucion completa si la peticion declara una
  politica temporal versionada, empezando por `nasa_ims_temporal_v1`;
- NASA IMS sintetico o controlado puede habilitar modelado supervisado solo si
  la peticion declara `allow_synthetic_labels=true`;
- los scripts especificos por dataset quedan como atajos reproducibles de
  experimentos concretos, no como arquitectura principal.

Ejemplos de planificacion:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id cwru_bearing \
  --adapter-id cwru_bearing \
  --raw-path codigo/data/raw/cwru_bearing/mat \
  --run-id plan-cwru-smoke \
  --plan-only
```

Resultado esperado: `can_execute_requested_stages=true`.

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id plan-nasa-full-smoke \
  --plan-only
```

Resultado esperado: `can_execute_requested_stages=false`, con bloqueos en
`modeling` y `evaluation`.

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id plan-nasa-diagnostic-smoke \
  --execution-mode diagnostic \
  --plan-only
```

Resultado esperado: `can_execute_requested_stages=true`, limitado a manifiesto,
perfilado, limpieza y estructuracion.

Con esto, la seleccion futura desde interfaz no llamara directamente a scripts
`cwru_*` o `nasa_*`, sino a la misma logica de planificacion. Los scripts por
dataset permanecen para reproducir runs canonicas ya documentadas.

## Validacion del runner comun

Se ha ejecutado una validacion importante para comprobar que la nueva capa
multi-dataset no rompe el benchmark CWRU ni salta los guardarrailes NASA IMS.

### CWRU completo con runner comun

Comando:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id cwru_bearing \
  --adapter-id cwru_bearing \
  --raw-path codigo/data/raw/cwru_bearing/mat \
  --run-id cwru-runner-common-validation-fase4-001
```

Resultado:

- `final_stage`: `completed`;
- `approved`: `true`;
- errores: `0`;
- snapshot:
  `codigo/reports/runs/cwru-runner-common-validation-fase4-001`;
- informe:
  `codigo/reports/cwru_bearing/cwru-runner-common-validation-fase4-001/final_report.md`.

Metricas:

```text
precision = 0.9991497803599263
recall = 1.0
f1_score = 0.9995747093847462
false_positive_rate = 0.05128205128205128
```

Estas metricas coinciden exactamente con:

```text
cwru-memory-transversal-fase4-001
cwru_iforest_threshold_v1_baseline_threshold_099
```

Interpretacion: el runner comun reproduce el comportamiento CWRU conocido y no
altera el benchmark de regresion.

### NASA IMS diagnostic con runner comun

Comando:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id nasa-runner-common-diagnostic-fase4-001 \
  --execution-mode diagnostic
```

Resultado:

- `final_stage`: `completed`;
- metricas: `null`;
- evaluacion: `null`;
- errores: `0`;
- artefactos generados: `manifest`, `profile`, `clean_signals`, `log`,
  `features`, `tensors`, `splits`;
- mensajes de herramienta ejecutados: `dataset_manifest`, `data_profiler`,
  `cleaning`, `structuring`.

Interpretacion: el modo `diagnostic` ejecuta solo las fases permitidas para
NASA IMS real/preextraido y se detiene antes de modelado supervisado.

### NASA IMS full sin politica sigue bloqueado

Comando:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id nasa-runner-common-full-block-check-fase4-001 \
  --plan-only
```

Resultado:

- `can_execute_requested_stages=false`;
- bloqueo en `modeling`;
- bloqueo en `evaluation`;
- motivo: NASA IMS real requiere declarar una politica temporal versionada o
  etiquetas sinteticas/controladas antes de evaluacion supervisada.

### NASA IMS full con politica temporal v1

Se ha incorporado la primera politica temporal versionada:

```text
codigo/docs/33_politica_temporal_nasa_ims.md
codigo/app/services/nasa_ims_temporal_policy.py
```

La peticion declara:

```text
dataset_policy_id = "nasa_ims_temporal_v1"
```

Con esta politica, el runner genera primero el manifiesto NASA IMS comun y
despues escribe un manifiesto derivado:

```text
manifest_temporal_policy_v1.csv
```

La politica ordena cada `run_id` cronologicamente, etiqueta el tramo inicial
como `normal`, el tramo posterior como `degradation` y anade en
`metadata_json`:

```text
dataset_policy_id
label_source = "temporal_proxy"
label_granularity = "proxy_temporal"
label_policy_id = "nasa_ims_temporal_v1"
official_nasa_labels = false
official_window_labels = false
split_hint
split_source
temporal_order_index
temporal_phase
```

El ejecutor de estructuracion lee `split_hint` desde los `.npz` limpios y usa
la estrategia `metadata_json_split_hint` cuando todos los registros la declaran.
Si no hay hints, CWRU y los flujos existentes conservan la estrategia anterior.

Comando validado:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id nasa-runner-temporal-policy-v1-completed-low-metrics-002 \
  --dataset-policy-id nasa_ims_temporal_v1
```

Resultado:

- `can_execute_requested_stages=true`;
- el pipeline alcanza modelado y evaluacion;
- `final_stage=completed`;
- `approved=false`;
- informe final generado en
  `codigo/reports/nasa_ims_bearing/nasa-runner-temporal-policy-v1-completed-low-metrics-002/final_report.md`;
- manifiesto temporal: 2 registros `normal` y 1 `degradation`;
- splits: 1 registro normal a `train`, 1 normal a `test`, 1 degradacion a
  `test`;
- ventanas: 3 `train` normales y 6 `test`;
- metricas de test: precision 0.5000, recall 1.0000, F1 0.6667, FPR 1.0000.

Interpretacion: la politica v1 desbloquea ejecucion completa auditable sobre
NASA IMS, pero no aprueba automaticamente el resultado. Una run con metricas
bajas queda completada y trazada con `approved=false`, no marcada como fallo de
infraestructura. Las metricas son proxy metodologicas y deben citar la politica
temporal usada.

Conclusion: la logica comun queda lista como base para preflight de API/UI. El
paso siguiente sera decidir si se ajusta el protocolo/modelo NASA para reducir
FPR o si se expone primero esta planificacion desde un endpoint de aplicacion,
sin introducir todavia interfaz grafica.

## API controlada inicial

El preflight multi-dataset ya se ha expuesto en la API mediante:

```text
POST /runs
```

La solicitud usa `ApiRunRequest`, que extiende `PipelineRunRequest` con
`dry_run`. El valor por defecto es `dry_run=true`, por lo que una futura UI
puede pedir el plan, mostrar descriptor, rutas, capacidades y bloqueos, y solo
despues lanzar la ejecucion enviando `dry_run=false`.

Guardarrailes de esta version:

- `raw_path` debe estar dentro de raices permitidas por `create_app`;
- por defecto solo se permite `codigo/data/raw`;
- si la politica multi-dataset bloquea fases, la ejecucion responde `409`;
- `use_llm=true` y memoria RAG quedan fuera de la ejecucion API inicial;
- Human Review usa los contratos existentes `HumanReviewSettings` y
  `HumanApproval`;
- en modo `passive` se devuelven razones sin bloquear; en modo `required`, la
  ejecucion necesita `human_approval.approved=true`;
- `background=true` acepta la ejecucion como job local en memoria, observable
  mediante `GET /run-jobs/{job_id}`;
- `run_id` no se sobrescribe desde API;
- los snapshots se guardan en el mismo `codigo/reports/runs/` que los scripts.

Documento especifico:

```text
codigo/docs/34_api_ejecucion_controlada_fase4.md
```

## Regla transversal de reutilizacion

El soporte multi-dataset y la futura interfaz deben seguir el protocolo de
reutilizacion definido en:

```text
codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md
```

Implicaciones directas para este diseno:

- no crear un runner nuevo por dataset si `pipeline_runner.py` puede planificar o
  ejecutar la misma capacidad;
- no duplicar contratos de solicitud si `PipelineRunRequest` o `ApiRunRequest`
  ya expresan el concepto;
- no meter logica de politica temporal en la API si pertenece a
  `nasa_ims_temporal_policy.py`;
- no crear otra puerta de revision humana si `human_review.py`,
  `HumanReviewSettings` y `HumanApproval` ya cubren el caso;
- antes de anadir endpoints nuevos, revisar si deben delegar en
  `run_registry.py`, `run_persistence.py` o `pipeline_runner.py`.

La decision por defecto sera adaptar o extender la pieza canonica existente. Una
pieza nueva solo se justificara si evita mezclar responsabilidades o si no hay
frontera clara donde colocar la capacidad.
