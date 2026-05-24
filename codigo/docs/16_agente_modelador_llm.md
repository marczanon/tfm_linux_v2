# Agente modelador LLM

## Objetivo

Introducir el agente LLM que decide el modelo base y sus hiperparametros. El
agente devuelve una `ModelingDecision`; no entrena modelos ni genera
predicciones directamente. La ejecucion real sigue delegada en:

```text
codigo/app/executors/modeling.py
```

## Que decide

El agente modelador propone:

- algoritmo de deteccion de anomalias;
- semilla de reproducibilidad;
- hiperparametros;
- split de entrenamiento;
- split de validacion para umbral;
- ruta esperada del modelo entrenado.

Para el MVP CWRU, las validaciones restringen la decision a:

```text
model_name = isolation_forest
random_state = 42
train_split = train
validation_split = validation | null
expected_model_path = codigo/models/cwru_bearing/isolation_forest.joblib
```

El ejecutor de modelado ya contiene el soporte determinista para Isolation
Forest. Por tanto, aunque el contrato `ModelingConfig` contemple modelos
futuros, el agente no puede seleccionar One-Class SVM, LOF, PCA ni autoencoders
hasta que existan ejecutores reproducibles para esas opciones.

## Implementacion

Archivos principales:

```text
codigo/app/agents/modeler.py
codigo/app/graph/pipeline.py
codigo/tests/test_modeler_agent.py
```

El agente expone:

```text
decide_modeling_action(state, llm_client=None, use_llm=None) -> ModelingDecision
```

Rutas disponibles:

- `decide_modeling_action_with_llm(...)`: usa un cliente LLM JSON.
- `decide_modeling_action_deterministic(...)`: fallback reproducible.

## Encaje en el grafo

La fase `modeling` queda dividida en decision y ejecucion:

```text
supervisor
-> modeling_agent
-> supervisor
-> modeling_executor
```

El supervisor enruta a `modeling_agent` si `modeling_config` todavia es
`null`. El agente escribe la configuracion en el estado y despues el supervisor
autoriza el ejecutor determinista.

## Validaciones de seguridad

La respuesta del LLM se valida contra `ModelingDecision` y despues se acota con
reglas del MVP:

- solo se permite `isolation_forest`;
- `random_state` debe ser 42;
- `n_jobs` debe ser 1 si aparece;
- `n_estimators` debe estar entre 10 y 500;
- `threshold_quantile` debe estar en `(0, 1]`;
- no se aceptan hiperparametros fuera de los soportados por el ejecutor.

Si el LLM falla, devuelve JSON invalido o propone una configuracion fuera de
estos limites, se activa el fallback determinista.

## Verificacion LLM local

Modelo usado:

```text
qwen3.5:4b
```

Resultado validado:

```text
model_name = isolation_forest
random_state = 42
train_split = train
validation_split = validation
expected_model_path = codigo/models/cwru_bearing/isolation_forest.joblib
confidence = 0.9
threshold_quantile = 0.99
```

Durante la prueba se ha detectado que Qwen puede devolver razonamiento en el
campo `thinking` de Ollama y dejar `message.content` vacio. El cliente
`OllamaJSONClient` usa `think=false` por defecto en llamadas JSON estrictas
para forzar que el JSON validable llegue por `message.content`, pero el valor
queda configurable con `TFM_LLM_THINK=true` o `TFM_LLM_THINK=auto` para pruebas
con mayor razonamiento.

## Tests

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 74 tests
OK
```

Prueba integrada del pipeline:

```text
current_stage = completed
messages = 19
supervisor_decisions = 10
cleaner_decisions = 1
structurer_decisions = 1
modeler_decisions = 1
f1_score = 0.9995747093847462
```

## Siguiente paso

El agente evaluador queda documentado en `17_agente_evaluador_llm.md`. El
siguiente avance tecnico sera introducir el agente redactor para generar el
informe tecnico final a partir de artefactos, decisiones y metricas validadas.
