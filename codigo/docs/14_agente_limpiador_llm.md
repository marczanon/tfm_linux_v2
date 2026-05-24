# Agente limpiador LLM

## Objetivo

Introducir el primer agente LLM especializado del MVP: el limpiador. Su papel
es proponer una `CleaningDecision` a partir del perfil ligero del dataset. El
agente no transforma senales ni ejecuta codigo; el modulo autorizado para
aplicar cambios sigue siendo:

```text
codigo/app/executors/cleaning.py
```

## Implementacion

Archivos principales:

```text
codigo/app/agents/cleaner.py
codigo/app/graph/pipeline.py
codigo/tests/test_cleaner_agent.py
```

El agente expone:

```text
decide_cleaning_action(state, llm_client=None, use_llm=None) -> CleaningDecision
```

Rutas disponibles:

- `decide_cleaning_action_with_llm(...)`: usa un cliente LLM JSON.
- `decide_cleaning_action_deterministic(...)`: fallback reproducible.

## Encaje en el grafo

La fase `cleaning` se divide ahora en dos pasos:

```text
supervisor
-> cleaner_agent
-> supervisor
-> cleaning_executor
```

El supervisor enruta primero a `cleaner_agent` si `cleaning_config` todavia es
`null`. El limpiador genera la configuracion y la guarda en el estado. Despues,
el supervisor enruta a `cleaning_executor`.

## Validaciones

La salida LLM debe cumplir:

- JSON parseable;
- contrato `CleaningDecision`;
- `CleaningConfig` valida;
- `remove_non_finite = true`;
- `resample_to_hz = 12000` para el MVP CWRU;
- `normalization` en `none`, `zscore` o `robust`;
- `expected_artifact_path` no vacio.

Si la respuesta falla, se usa el fallback:

```text
strategy_id = cwru_clean_v1
remove_non_finite = true
resample_to_hz = 12000
normalization = none
```

## Verificacion LLM local

Modelo usado:

```text
qwen3.5:4b
```

Resultado del supervisor LLM:

```text
next_stage = dataset_manifest
next_node = manifest_executor
confidence = 0.9
```

Resultado del limpiador LLM:

```text
strategy_id = cwru_clean_llm_v1
remove_non_finite = true
resample_to_hz = 12000
normalization = none
confidence = 0.9
```

Ambas respuestas validaron correctamente contra sus contratos Pydantic.

## Tests

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 64 tests
OK
```

## Siguiente paso

Este paso ya ha evolucionado en `15_agente_estructurador_llm.md`, donde se
implementa y valida el agente estructurador LLM.
