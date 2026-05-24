# Supervisor determinista

## Objetivo

Introducir el primer nodo supervisor del MVP sin usar todavia LLMs. La fase
sigue el enfoque `contract-first`: el supervisor emite una `SupervisorDecision`
validada por Pydantic, pero la politica interna es determinista.

Esto permite preparar la arquitectura multiagente sin mezclar aun razonamiento
generativo con transformaciones de datos.

## Implementacion

Archivos principales:

```text
codigo/app/agents/supervisor.py
codigo/app/graph/pipeline.py
codigo/tests/test_supervisor_agent.py
codigo/tests/test_graph_pipeline.py
```

El modulo `supervisor.py` expone:

```text
decide_supervisor_action(state: TFMStateModel) -> SupervisorDecision
```

La decision contiene:

- fase actual;
- fase objetivo;
- siguiente nodo;
- motivo de la decision;
- confianza;
- indicador de revision humana;
- motivo de parada si la decision es terminal.

## Flujo supervisado

El grafo ya no avanza directamente de un ejecutor al siguiente. Todas las
transiciones pasan por `supervisor`:

```text
START
-> supervisor
-> manifest_executor
-> supervisor
-> profiler_executor
-> supervisor
-> cleaning_executor
-> supervisor
-> structuring_executor
-> supervisor
-> modeling_executor
-> supervisor
-> evaluator
-> supervisor
-> END
```

Cada ejecutor actualiza rutas, artefactos, metricas ligeras o errores. Despues
devuelve el control al supervisor, que decide si continuar, detenerse por error
o finalizar.

## Politica inicial

La politica determinista valida entradas minimas por fase:

```text
dataset_manifest -> raw_path
profiling        -> manifest_path
cleaning         -> manifest_path + profile_path
structuring      -> clean_path
modeling         -> features artifact o tensor_path
evaluation       -> predictions artifact
```

Si falta una entrada obligatoria, el supervisor emite una decision terminal con
`next_stage = failed`. Si la fase es `completed`, emite una decision terminal
con `stop_reason = completed`.

## Trazabilidad

Cada decision del supervisor se guarda en `messages` con rol `supervisor` y
contenido JSON serializado. No se incorporan datasets, senales ni tensores al
estado.

Ejemplo de decision no terminal:

```json
{
  "agent_name": "supervisor",
  "current_stage": "profiling",
  "next_stage": "profiling",
  "next_node": "profiler_executor",
  "requires_human_review": false,
  "stop_reason": null
}
```

## Verificacion

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 54 tests
OK
```

Las pruebas cubren:

- decisiones aisladas del supervisor;
- validacion de entradas obligatorias;
- ejecucion completa del grafo supervisado con ejecutores simulados;
- parada controlada ante fallo de un ejecutor;
- registro alternado de decisiones del supervisor y mensajes de ejecutores.

Prueba integrada con CWRU real:

```text
current_stage = completed
next_node = None
artifacts = 12
messages = 13
supervisor_decisions = 7
metrics_path = codigo/reports/cwru_bearing/evaluation/metrics.json
f1_score = 0.9995747093847462
```

## Siguiente paso

Este paso ya ha evolucionado en `13_supervisor_llm.md`, donde el supervisor
puede usar un LLM para emitir `SupervisorDecision` y conserva esta politica
determinista como fallback reproducible.
