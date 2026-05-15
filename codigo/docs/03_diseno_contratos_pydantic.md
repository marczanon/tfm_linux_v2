# Diseno de contratos Pydantic

## Objetivo

El paso 5 fija los esquemas que usaran agentes, ejecutores y grafo para
intercambiar informacion sin ambiguedades. El objetivo es evitar texto libre
como salida principal, campos omitidos cuando deben ser `null` y objetos pesados
como senales, ventanas o arrays dentro del estado.

## Archivos implementados

```text
codigo/app/schemas/common.py
codigo/app/schemas/dataset.py
codigo/app/schemas/agent_decisions.py
codigo/app/schemas/executor_results.py
codigo/tests/test_dataset_schema.py
codigo/tests/test_agent_decisions_schema.py
codigo/tests/test_executor_results_schema.py
```

## Contratos de dataset

`dataset.py` define:

- `SignalChannel`: canal detectado en un fichero de senal.
- `FaultMetadata`: tipo de fallo, diametro, carga y RPM.
- `DatasetManifestRow`: fila del manifiesto de datos crudos.
- `DatasetManifest`: manifiesto completo.

Reglas principales:

- las filas `normal` deben llevar `fault_type = null` y
  `fault_diameter_inch = null`;
- las filas `fault` requieren `fault_type` y `fault_diameter_inch`;
- las filas de un manifiesto deben pertenecer al mismo dataset;
- `file_id` no puede repetirse dentro de un manifiesto;
- campos nulos relevantes se declaran de forma explicita.

## Contratos de agentes

`agent_decisions.py` define salidas estructuradas para:

- `SupervisorDecision`;
- `CleaningDecision`;
- `StructuringDecision`;
- `ModelingDecision`;
- `EvaluationDecision`;
- `ReportDecision`.

Reglas principales:

- toda decision incluye `decision_id`, `rationale`, `confidence` y marca
  temporal;
- el supervisor debe indicar `next_node` salvo en estados terminales;
- las decisiones terminales requieren `stop_reason`;
- los agentes especializados devuelven configuraciones Pydantic ya validadas;
- el redactor debe declarar secciones estructuradas del informe.

## Contratos de ejecutores

`executor_results.py` define:

- `ExecutorResult`;
- `ManifestResult`;
- `ProfileResult`;
- `CleaningResult`;
- `StructuringResult`;
- `ModelingResult`;
- `EvaluationExecutorResult`;
- `ReportExecutorResult`.

Reglas principales:

- un resultado `failed` requiere al menos un `PipelineError`;
- un resultado `success` no puede incluir errores;
- los resultados devuelven rutas, metricas y referencias a artefactos, no
  datos pesados;
- el resultado del manifiesto requiere filas generadas para considerarse
  correcto.

## Verificacion

Comando usado en el entorno objetivo:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 23 tests
OK
```

## Siguiente entrega implementable

El primer ejecutor determinista ya esta implementado para el manifiesto CWRU.
El siguiente paso es el perfilador:

```text
codigo/app/executors/data_profiler.py
codigo/tests/test_data_profiler.py
```

Ese ejecutor debe generar:

```text
codigo/data/interim/cwru_bearing/profile.json
```

y devolver un `ProfileResult` que pueda actualizar el `TFMState` con
`profile_path` y un `ArtifactRef`.
