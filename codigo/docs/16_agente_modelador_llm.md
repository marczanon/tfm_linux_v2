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
- ruta esperada del modelo entrenado;
- alternativas comparables en `comparison_candidates`, cuando existan varios
  modelos o configuraciones soportadas.

Para el MVP CWRU y la Fase 3, las validaciones restringen la decision a modelos
realmente ejecutables:

```text
model_name in {isolation_forest, pca_reconstruction_error}
random_state = 42
train_split = train
validation_split = validation | null
expected_model_path = codigo/models/cwru_bearing/<model_name>.joblib
```

En Fase 3 la validacion de `expected_model_path` ya no esta anclada a CWRU: la
ruta esperada se calcula con `state.project_context.dataset`, por ejemplo
`codigo/models/nasa_ims_bearing/isolation_forest.joblib` en ejecuciones NASA
IMS sinteticas.

El ejecutor de modelado contiene soporte determinista para Isolation Forest y
PCA con error de reconstruccion. Aunque el contrato `ModelingConfig` contempla
otros algoritmos futuros, el agente no puede seleccionar One-Class SVM, LOF ni
autoencoders hasta que existan ejecutores reproducibles para esas opciones.

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

- solo se permiten `isolation_forest` y `pca_reconstruction_error`;
- `random_state` debe ser 42;
- `n_jobs` debe ser 1 si aparece;
- `n_estimators` debe estar entre 10 y 500;
- `n_components`, si aparece en PCA, debe ser numerico y valido;
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

## Comparacion agentica de modelos

En Fase 3 se ha ampliado `ModelingDecision` con `comparison_candidates`. El
agente puede proponer alternativas de modelado y el protocolo experimental las
ejecuta solo si estan soportadas por el ejecutor determinista.

Validacion real:

```text
python -m codigo.scripts.run_cwru_agentic_model_comparison \
  --model qwen3.5:4b \
  --plan-id cwru-agentic-model-qwen-fase3
```

Qwen propuso Isolation Forest como seleccion principal, PCA reconstruction
error como modelo alternativo y una variante conservadora de Isolation Forest.
Sobre la estructuracion 1024/50%, PCA obtuvo precision 1.0000 y FPR 0.0000,
pero recall 0.9623. Esto introduce una comparacion mas realista que el caso
unico de recall perfecto.

La prueba agentica NASA sintetica `nasa-ims-synth-agentic-qwen-fase3` confirma
el mismo contrato multi-dataset: Qwen selecciono `isolation_forest` sobre
features NASA IMS-like y el evaluador rechazo la ejecucion por recall 0.6000 y
FPR 0.1429, dejando un caso no perfecto para iteracion posterior.

## Reintento agentico tras fallo

En Fase 3 se ha incorporado `ModelingRetryDecision` para que el modelador no
solo elija una configuracion inicial, sino que pueda aprender de una ejecucion
fallida. La entrada del agente no es el dataset completo, sino un expediente de
fallo generado de forma determinista:

```text
codigo/app/services/iteration_analysis.py
```

Ese expediente incluye matriz de confusion, resumen de falsos negativos,
resumen de falsos positivos, umbral efectivo, convencion de scoring y numero
maximo de reintentos. Con esa evidencia, Qwen decidio bajar
`threshold_quantile` al detectar muchas anomalias escapadas.

Validacion real sobre el benchmark NASA IMS sintetico:

| Run | threshold_quantile | Precision | Recall | F1 | FPR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base | 0.99 | 0.9130 | 0.6000 | 0.7241 | 0.1429 |
| Retry 1 | 0.95 | 0.8846 | 0.6571 | 0.7541 | 0.2143 |
| Retry 2 | 0.50 | 0.7143 | 1.0000 | 0.8333 | 1.0000 |

El resultado muestra dos comportamientos relevantes para el TFM. Primero, el
agente aprendio una direccion tecnica razonable: bajar el umbral aumenta la
sensibilidad y reduce falsos negativos. Segundo, el sistema no permite bucles
infinitos ni aprueba una mejora parcial si el coste industrial es excesivo: el
segundo reintento alcanza recall perfecto, pero dispara FPR a 1.0000, por lo
que la evaluacion queda rechazada y el bucle termina con `next_action = stop`.

## Post-mortem y revision humana del razonamiento

Para distinguir suerte de razonamiento tecnico, cada reintento puede generar un
post-mortem estructurado:

```text
codigo/app/services/reasoning_audit.py
codigo/app/schemas/reasoning.py
codigo/scripts/create_agentic_reasoning_audit.py
```

El post-mortem compara:

- hipotesis declarada por el agente;
- evidencia citada;
- accion ejecutada;
- efecto esperado;
- metricas antes y despues;
- critica automatica;
- lecciones reutilizables.

Sobre las dos runs NASA sinteticas se han creado artefactos de revision humana:

```text
reasoning_postmortem.json
reasoning_postmortem.md
human_reasoning_review_request.json
human_reasoning_review_request.md
human_reasoning_review_template.json
```

La revision humana no modifica las metricas ni aprueba una run rechazada. Su
objetivo es etiquetar si el razonamiento del agente fue `correct`,
`partially_correct`, `incorrect`, `unsafe` o `needs_more_evidence`. Esa etiqueta
puede reutilizarse despues como memoria supervisada: contexto para futuros
agentes, RAG local, ejemplos positivos/negativos o filtro para descartar
patrones de decision repetidamente erroneos.

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
Ran 157 tests
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
