# Agente evaluador LLM

## Objetivo

Introducir el agente LLM que interpreta las metricas ya calculadas por el
ejecutor determinista. El agente devuelve una `EvaluationDecision`; no recalcula
metricas, no modifica predicciones y no transforma datos. La evaluacion
numerica sigue delegada en:

```text
codigo/app/executors/evaluation.py
```

## Que decide

El agente evaluador propone:

- si el resultado queda aprobado para el MVP local;
- un resumen tecnico de las metricas;
- la siguiente accion recomendada;
- limitaciones del experimento;
- umbrales usados para recall y tasa de falsos positivos.

Para el MVP CWRU, las validaciones restringen la decision a:

```text
min_recall_required = 0.90
max_false_positive_rate = 0.10
approved = recall >= 0.90 and false_positive_rate <= 0.10
```

El agente puede redactar el juicio tecnico y sus limitaciones, pero no puede
aprobar una ejecucion que no cumpla esos umbrales.

## Implementacion

Archivos principales:

```text
codigo/app/agents/evaluator.py
codigo/app/graph/pipeline.py
codigo/tests/test_evaluator_agent.py
```

El agente expone:

```text
decide_evaluation_action(state, llm_client=None, use_llm=None) -> EvaluationDecision
```

Rutas disponibles:

- `decide_evaluation_action_with_llm(...)`: usa un cliente LLM JSON.
- `decide_evaluation_action_deterministic(...)`: fallback reproducible.

## Encaje en el grafo

La fase `evaluation` queda dividida en evaluacion numerica y juicio agentico:

```text
supervisor
-> evaluator
-> supervisor
-> evaluation_agent
-> supervisor
```

El nodo `evaluator` mantiene el comportamiento existente: calcula metricas y
genera los artefactos `metrics` y `report`. Despues, el supervisor enruta a
`evaluation_agent` si `metrics` existe pero `evaluation` todavia es `null`.

## Configuracion de razonamiento en Ollama

El cliente JSON usa `TFM_LLM_THINK=false` por defecto para que modelos como
Qwen devuelvan el JSON final en `message.content`. Esto no se considera una
decision fija de arquitectura: se puede activar razonamiento visible con:

```bash
export TFM_LLM_THINK=true
```

Tambien se puede omitir el parametro `think` en la peticion con:

```bash
export TFM_LLM_THINK=auto
```

La recomendacion para el MVP local es mantener `false` en agentes que deben
devolver JSON estricto, y comparar `true` o `auto` cuando se pruebe Qwen 9B o
se evaluen tareas de interpretacion mas exigentes.

## Tests

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado esperado tras esta fase:

```text
Ran 84 tests
OK
```

## Siguiente paso

El agente redactor queda documentado en `18_agente_redactor_llm.md`. El flujo
local ya puede cerrar la ejecucion con un informe tecnico final generado a
partir de artefactos, decisiones y metricas validadas.
