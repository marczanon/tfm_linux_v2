# Estado actual del MVP multiagente

Fecha de recopilacion: 2026-05-24.

## Resumen

El proyecto ya dispone de un MVP local funcional para deteccion de anomalias en
rodamientos de motor electrico usando CWRU Bearing Dataset. La aplicacion
ejecuta un flujo completo desde datos crudos hasta informe tecnico final,
manteniendo separadas dos responsabilidades:

- los agentes LLM toman decisiones estructuradas y validables;
- los ejecutores Python deterministas realizan las transformaciones, entrenan
  modelos, calculan metricas y escriben artefactos.

La orquestacion se realiza con LangGraph y patron de supervisor jerarquico. El
estado global nunca transporta senales completas: conserva rutas, resumentes,
configuraciones, metricas, errores, mensajes y referencias a artefactos.

## Que puede hacer ahora la aplicacion

La aplicacion puede ejecutar localmente el siguiente flujo completo:

```text
datos .mat CWRU
-> manifiesto del dataset
-> perfilado estadistico
-> limpieza de senales
-> estructuracion temporal
-> ventanas, features y tensores
-> entrenamiento Isolation Forest
-> predicciones de anomalia
-> evaluacion de metricas
-> juicio del evaluador
-> informe tecnico final
```

En una ejecucion real, el pipeline:

- inspecciona los ficheros `.mat` de CWRU y genera un manifiesto trazable;
- perfila canales, frecuencias, etiquetas y estadisticas basicas;
- extrae el canal principal `DE_time`;
- elimina valores no finitos y remuestrea a 12 kHz cuando procede;
- genera ventanas de 2048 muestras con 50% de solapamiento;
- calcula features temporales y conserva tensores crudos;
- crea particiones reproducibles train/validation/test a nivel de fichero;
- entrena un baseline `IsolationForest` con ventanas normales de train;
- genera predicciones por ventana;
- calcula precision, recall, F1, ROC-AUC, PR-AUC, FPR y matriz de confusion;
- interpreta metricas con un agente evaluador;
- genera un informe Markdown final con artefactos, metricas y limitaciones.

## Componentes implementados

### Contratos y estado

Archivos principales:

```text
codigo/app/schemas/state.py
codigo/app/schemas/agent_decisions.py
codigo/app/schemas/executor_results.py
codigo/app/graph/state.py
```

Incluyen:

- `TFMStateModel`, estado global validado;
- `ProjectContext`, contexto industrial de ejecucion;
- `CleaningConfig`, `StructuringConfig`, `ModelingConfig`;
- `MetricsReport` y `EvaluationResult`;
- `ArtifactRef` y `PipelineError`;
- decisiones de agentes: `SupervisorDecision`, `CleaningDecision`,
  `StructuringDecision`, `ModelingDecision`, `EvaluationDecision`,
  `ReportDecision`;
- resultados de ejecutores: manifiesto, perfilado, limpieza, estructuracion,
  modelado, evaluacion y reporting.

### Ejecutores deterministas

Archivos principales:

```text
codigo/app/executors/dataset_manifest.py
codigo/app/executors/data_profiler.py
codigo/app/executors/cleaning.py
codigo/app/executors/structuring.py
codigo/app/executors/modeling.py
codigo/app/executors/evaluation.py
codigo/app/executors/reporting.py
```

Responsabilidad:

- leer entradas desde disco;
- aplicar transformaciones reproducibles;
- guardar artefactos;
- devolver resultados estructurados;
- no depender de razonamiento generativo.

### Agentes LLM

Archivos principales:

```text
codigo/app/agents/supervisor.py
codigo/app/agents/cleaner.py
codigo/app/agents/structurer.py
codigo/app/agents/modeler.py
codigo/app/agents/evaluator.py
codigo/app/agents/report_writer.py
```

Cada agente tiene dos rutas:

- ruta LLM con cliente JSON y validacion Pydantic;
- fallback determinista para pruebas y ejecuciones sin modelo.

Los agentes implementados son:

- Supervisor: decide el siguiente nodo del grafo.
- Limpiador: propone configuracion de limpieza.
- Estructurador: propone ventana, solapamiento, canal, frecuencia y features.
- Modelador: selecciona modelo e hiperparametros dentro del MVP.
- Evaluador: interpreta metricas y decide si continuar.
- Redactor: decide la estructura del informe tecnico final.

### Servicio LLM

Archivo principal:

```text
codigo/app/services/llm.py
```

Incluye:

- `JSONLLMClient`, protocolo comun para clientes JSON;
- `OllamaJSONClient`, cliente local contra `/api/chat`;
- `parse_json_object`, parser de objetos JSON;
- configuracion por variables de entorno.

Variables relevantes:

```bash
export TFM_LLM_PROVIDER=ollama
export TFM_LLM_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
export TFM_LLM_THINK=false
```

`TFM_LLM_THINK=false` es el valor recomendado para llamadas JSON estrictas con
Qwen en el MVP local. Tambien se puede usar `TFM_LLM_THINK=true` para probar
razonamiento visible o `TFM_LLM_THINK=auto` para omitir el parametro `think`.

### Grafo LangGraph

Archivo principal:

```text
codigo/app/graph/pipeline.py
```

Flujo actual:

```text
START
-> supervisor
-> manifest_executor
-> supervisor
-> profiler_executor
-> supervisor
-> cleaner_agent
-> supervisor
-> cleaning_executor
-> supervisor
-> structuring_agent
-> supervisor
-> structuring_executor
-> supervisor
-> modeling_agent
-> supervisor
-> modeling_executor
-> supervisor
-> evaluator
-> supervisor
-> evaluation_agent
-> supervisor
-> report_writer
-> supervisor
-> END
```

Todas las transiciones vuelven al supervisor. Si falta una entrada obligatoria
o un ejecutor falla, el grafo termina de forma controlada en `failed`.

## Artefactos generados

La ejecucion real produce, entre otros:

```text
codigo/data/interim/cwru_bearing/manifest.csv
codigo/data/interim/cwru_bearing/profile.json
codigo/data/processed/cwru_bearing/clean_signals/
codigo/data/processed/cwru_bearing/cleaning_summary.json
codigo/data/tensors/cwru_bearing/windows_features.csv
codigo/data/tensors/cwru_bearing/windows_raw.npz
codigo/data/tensors/cwru_bearing/splits.json
codigo/models/cwru_bearing/isolation_forest.joblib
codigo/models/cwru_bearing/predictions.csv
codigo/models/cwru_bearing/modeling_summary.json
codigo/reports/cwru_bearing/evaluation/metrics.json
codigo/reports/cwru_bearing/evaluation/evaluation_summary.md
codigo/reports/cwru_bearing/final_report.md
```

## Resultado de una ejecucion real

Comprobacion ejecutada:

```bash
conda run -n tfm_v2 python -c "<ejecucion completa del pipeline CWRU>"
```

Resumen obtenido:

```text
current_stage = completed
next_node = null
report_path = codigo/reports/cwru_bearing/final_report.md
artifact_count = 13
message_count = 24
supervisor_decisions = 12
cleaner_decisions = 1
structurer_decisions = 1
modeler_decisions = 1
evaluator_decisions = 1
report_writer_decisions = 1
errors = []
```

Metricas principales sobre `test`:

```text
precision = 0.9991497803599263
recall = 1.0
f1_score = 0.9995747093847462
roc_auc = 0.9999963634909033
pr_auc = 0.9999999396693899
false_positive_rate = 0.05128205128205128
n_predictions = 7460
```

Juicio del evaluador:

```text
approved = true
next_action = continue
summary = Ejecucion aprobada: recall=1.0000, F1=0.9996, FPR=0.0513.
```

Limitaciones registradas:

- la validacion se realiza sobre CWRU, un benchmark controlado;
- la generalizacion industrial requiere validar otros datasets y condiciones de
  carga.

## Validacion con Ollama local

Servidor comprobado:

```text
OLLAMA_HOST = http://127.0.0.1:11434
modelo = qwen3.5:4b
```

El servidor respondio a `/api/tags` y tiene disponible `qwen3.5:4b`.

Validacion directa del agente redactor con `qwen3.5:4b`:

```text
agent_name = report_writer
confidence = 0.9
output_path = codigo/reports/cwru_bearing/final_report.md
output_format = markdown
n_sections = 6
```

Secciones devueltas por el LLM:

```text
Resumen ejecutivo
Contexto y datos
Configuraciones del pipeline
Metricas y evaluacion
Artefactos generados
Limitaciones y siguientes pasos
```

La decision valido contra `ReportDecision` y contra las restricciones del MVP.

## Verificacion automatizada

Comando ejecutado:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 91 tests
OK
```

Las pruebas cubren:

- esquemas Pydantic;
- estado inicial y validacion del estado global;
- adaptadores de entrada `.mat` y `.csv`;
- ejecutores de manifiesto, perfilado, limpieza, estructuracion, modelado,
  evaluacion y reporting;
- agentes supervisor, limpiador, estructurador, modelador, evaluador y
  redactor con cliente fake;
- cliente LLM JSON y parser;
- grafo LangGraph supervisado;
- fallbacks deterministas ante salidas invalidas.

## Limitaciones actuales

El MVP todavia no incluye:

- persistencia historica de ejecuciones;
- checkpoints persistentes de LangGraph;
- API FastAPI;
- frontend;
- Docker Compose completo;
- integracion SLURM;
- varios modelos comparables en produccion;
- validacion con datasets adicionales como NASA IMS;
- Human Review real antes de fases costosas.

Ademas, las metricas actuales son muy altas porque CWRU es un benchmark
controlado. Deben interpretarse como validacion del flujo y del baseline, no
como garantia de generalizacion industrial.

## Siguiente paso recomendado

La hoja de ruta activa pasa a ser:

```text
codigo/docs/20_hoja_ruta_fase_2.md
```

El siguiente paso metodologico es anadir persistencia ligera local antes de API
o frontend. La persistencia deberia guardar por ejecucion:

- estado final validado;
- decisiones de agentes;
- rutas de artefactos;
- metricas;
- evaluacion;
- errores;
- fecha de inicio y cierre;
- resumen del informe generado.

Una primera version puede ser un repositorio local de ejecuciones en:

```text
codigo/reports/runs/
```

con un fichero JSON por `run_id`. Mas adelante se podra migrar a PostgreSQL y
checkpoints persistentes de LangGraph.
