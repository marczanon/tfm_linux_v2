# Pipeline persistido

## Objetivo

Implementar el Hito 2 de la Fase 2: ejecutar el pipeline CWRU y guardar
automaticamente un snapshot local de la ejecucion sin modificar el
comportamiento base de `run_cwru_pipeline`.

La nueva entrada es:

```text
run_and_persist_cwru_pipeline(...)
```

## Implementacion

Archivo principal:

```text
codigo/app/graph/pipeline.py
```

La funcion expone:

```text
run_and_persist_cwru_pipeline(
    initial_state,
    executors=None,
    agents=None,
    runs_dir="codigo/reports/runs",
) -> PersistedPipelineRun
```

El retorno es un objeto ligero:

```text
PersistedPipelineRun
```

con dos campos:

- `state`: estado final del pipeline en formato `TFMState`;
- `snapshot`: metadata `RunSnapshot` generada por la persistencia local.

## Flujo

La funcion ejecuta dos pasos:

```text
run_cwru_pipeline(...)
-> validate_state(...)
-> save_run_snapshot(...)
```

Esto mantiene separadas dos capacidades:

- ejecucion pura del grafo;
- ejecucion con persistencia de evidencia.

## Razon de diseno

No se ha convertido la persistencia en un nodo del grafo en esta fase. La razon
es mantener estable el MVP ya validado y poder comparar facilmente:

- pipeline sin efectos adicionales;
- pipeline persistido.

El wrapper tambien permite inyectar ejecutores o agentes de prueba igual que
`run_cwru_pipeline`, por lo que conserva la testabilidad del grafo.

## Artefactos persistidos

El snapshot generado conserva la misma estructura definida en:

```text
codigo/docs/21_persistencia_local_runs.md
```

Por cada `run_id`:

```text
codigo/reports/runs/<run_id>/state_final.json
codigo/reports/runs/<run_id>/decisions.json
codigo/reports/runs/<run_id>/artifacts.json
codigo/reports/runs/<run_id>/metrics.json
codigo/reports/runs/<run_id>/evaluation.json
codigo/reports/runs/<run_id>/summary.md
codigo/reports/runs/<run_id>/snapshot.json
```

Y el indice:

```text
codigo/reports/runs/index.json
```

## Tests

La prueba integrada se encuentra en:

```text
codigo/tests/test_graph_pipeline.py
```

Verifica que:

- el wrapper ejecuta los mismos ejecutores simulados que el pipeline base;
- el estado final queda en `completed`;
- se genera un snapshot con decisiones, artefactos y errores;
- existen los ficheros persistidos;
- `index.json` permite recuperar la ejecucion por `run_id`;
- las metricas principales quedan visibles en el indice.

## Validacion real

La validacion con CWRU real debe comprobar que:

```text
current_stage = completed
snapshot_dir = codigo/reports/runs/<run_id>
n_artifacts = 13
n_decisions = 17
n_errors = 0
```

## Siguiente paso

El siguiente hito es construir el registro consultable y la comparacion basica:

```text
codigo/app/services/run_registry.py
codigo/tests/test_run_registry.py
```

Ese registro debe leer los snapshots ya persistidos para listar runs, filtrar
por estado o aprobacion y comparar metricas principales.
