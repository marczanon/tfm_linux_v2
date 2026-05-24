# Supervisor LLM con contratos estrictos

## Objetivo

Activar el primer agente LLM real del MVP: el supervisor. El LLM toma la
decision de alto nivel, pero no ejecuta transformaciones ni genera codigo. Su
salida debe validar contra `SupervisorDecision`.

La frontera queda asi:

```text
LLM supervisor
-> SupervisorDecision validada con Pydantic
-> LangGraph enruta
-> ejecutores Python deterministas
```

## Implementacion

Archivos principales:

```text
codigo/app/services/llm.py
codigo/app/agents/supervisor.py
codigo/app/graph/pipeline.py
codigo/tests/test_llm_service.py
codigo/tests/test_supervisor_agent.py
```

`codigo/app/services/llm.py` define:

- `JSONLLMClient`: protocolo para clientes que devuelven objetos JSON.
- `OllamaJSONClient`: cliente local para Ollama usando `/api/chat` y modo
  `format=json`. El parametro `think` queda configurable para equilibrar
  razonamiento y salida JSON estricta.
- `get_default_json_llm_client`: fabrica el cliente desde variables de entorno.
- `parse_json_object`: parser tolerante para respuestas JSON.

`codigo/app/agents/supervisor.py` define tres rutas:

- `decide_supervisor_action(...)`: punto de entrada principal.
- `decide_supervisor_action_with_llm(...)`: llamada LLM y validacion.
- `decide_supervisor_action_deterministic(...)`: fallback reproducible.

## Configuracion

Por defecto el pipeline conserva el fallback determinista. Para activar el
supervisor LLM:

```bash
export TFM_SUPERVISOR_MODE=llm
export TFM_LLM_PROVIDER=ollama
export TFM_LLM_MODEL=<modelo-local>
export OLLAMA_HOST=http://127.0.0.1:11434
```

Variables opcionales:

```bash
export TFM_LLM_TIMEOUT_SECONDS=60
export TFM_LLM_THINK=false
```

`TFM_LLM_THINK=false` es el valor por defecto porque algunos modelos Qwen en
Ollama devuelven el razonamiento en `thinking` y dejan `message.content` vacio
si se combina razonamiento visible con `format=json`. Si se quiere permitir el
modo de razonamiento del modelo, se puede usar `TFM_LLM_THINK=true`. Para omitir
el parametro en la peticion a Ollama, se acepta `TFM_LLM_THINK=auto`.

Tambien se puede inyectar un cliente desde tests o scripts:

```python
decision = decide_supervisor_action(
    state,
    llm_client=client,
    use_llm=True,
)
```

## Seguridad de decision

Aunque el LLM decide, su salida queda limitada por varias capas:

1. debe devolver JSON parseable;
2. debe validar contra `SupervisorDecision`;
3. `current_stage` debe coincidir con el estado real;
4. no puede activar `requires_human_review` en el MVP local;
5. no puede inventar transiciones fuera del plan permitido;
6. si falta una entrada obligatoria, debe detenerse en `failed`;
7. si falla cualquier validacion, se usa el fallback determinista.

Esto permite introducir IA en la toma de decisiones sin permitir que el modelo
ejecute codigo, manipule datos directamente o corrompa el estado.

## Estado local

La integracion con Ollama requiere que el servicio este levantado en
`127.0.0.1:11434` y que exista un modelo configurado en `TFM_LLM_MODEL`.
Durante las fases posteriores se ha validado el cliente con `qwen3.5:4b` para
supervisor, limpiador, estructurador, modelador y evaluador.

## Verificacion

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 59 tests
OK
```

Las pruebas cubren:

- parseo de respuestas JSON;
- uso de una decision LLM valida;
- rechazo de transiciones LLM invalidas;
- fallback determinista ante fallo de validacion;
- ejecucion completa del grafo supervisado con ejecutores simulados.

## Siguiente paso

Este paso ya ha evolucionado en `14_agente_limpiador_llm.md`, donde se
implementa el primer agente LLM especializado y se valida con `qwen3.5:4b`.
