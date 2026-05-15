# Diseno del estado global de LangGraph

## Objetivo

El estado global representa una ejecucion del pipeline. No contiene datasets,
senales completas, ventanas ni arrays. Solo guarda rutas, configuraciones
validadas, resumenes, metricas, errores y referencias a artefactos.

Esta decision mantiene el grafo ligero, serializable y compatible con
checkpoints futuros.

## Archivos implementados

```text
codigo/app/schemas/state.py
codigo/app/graph/state.py
codigo/tests/test_state_schema.py
```

## Capas del contrato

### Modelo canonico Pydantic

`TFMStateModel` valida el estado completo:

```text
thread_id
run_id
current_stage
next_node
project_context
raw_path
manifest_path
profile_path
extracted_signals_path
clean_path
tensor_path
splits_path
report_path
messages
dataset_profile
cleaning_config
structuring_config
modeling_config
metrics
evaluation
errors
human_approval
artifacts
```

Los modelos heredan de una base estricta que:

- rechaza campos no declarados;
- valida asignaciones;
- elimina espacios sobrantes en cadenas.

### Vista TypedDict para LangGraph

`TFMState` es la representacion ligera que circulara por LangGraph. Se obtiene
desde el modelo Pydantic mediante `model_dump(mode="json")`, por lo que es
serializable y adecuada para checkpoints.

### Inicializador CWRU

`create_initial_cwru_state` crea el estado inicial del MVP:

```text
current_stage = dataset_manifest
next_node = manifest_executor
raw_path = codigo/data/raw/cwru_bearing/mat
dataset = cwru_bearing
objective = binary_anomaly_detection
target_sample_rate_hz = 12000
main_channel = DE_time
```

## ProjectContext

El contexto fija el dominio del experimento:

```text
domain = industrial_anomaly_detection
machine_type = electric_motor_bearing
signal_type = vibration
dataset = cwru_bearing
objective = binary_anomaly_detection
target_sample_rate_hz = 12000
main_channel = DE_time
label_mode = binary_anomaly
```

## Artefactos

Los artefactos se guardan como referencias:

```text
name
artifact_type
path
producer
description
metadata
```

Ejemplo:

```text
name = cwru_manifest
artifact_type = manifest
path = codigo/data/interim/cwru_bearing/manifest.csv
producer = manifest_executor
```

## Configuraciones

El estado ya reserva contratos para:

- `CleaningConfig`;
- `StructuringConfig`;
- `ModelingConfig`.

Estos esquemas creceran cuando se implementen los ejecutores, pero ya fijan la
regla principal: el agente decide una configuracion validable y el ejecutor la
aplica de forma determinista.

## Errores y revision humana

Los errores se registran como `PipelineError`, con fase, nodo, mensaje,
detalles y marca temporal. La revision humana se representa con
`HumanApproval`, pensada para fases costosas o sensibles.

## Verificacion

La verificacion actual cubre:

- creacion del estado inicial CWRU;
- validacion con Pydantic;
- serializacion JSON;
- rechazo de campos desconocidos;
- validacion de rangos en configuraciones y metricas;
- referencias de artefactos sin payload pesado.

Comando usado:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 36 tests
OK
```

## Siguiente entrega implementable

Los ejecutores de manifiesto, perfilado, limpieza y estructuracion temporal ya
estan implementados. El siguiente paso deberia ser el ejecutor de modelado base:

```text
codigo/app/executors/modeling.py
codigo/tests/test_modeling_executor.py
```

El ejecutor debera leer `windows_features.csv`, entrenar modelos iniciales,
guardar modelos y predicciones, y actualizar el estado con referencias a
artefactos de modelado.
