# Registro consultable de ejecuciones

## Objetivo

Implementar el Hito 3 de la Fase 2: consultar ejecuciones ya persistidas,
filtrarlas y comparar metricas principales sin requerir API, frontend ni base
de datos externa.

La nueva capa se construye encima de:

```text
codigo/app/services/run_persistence.py
```

## Implementacion

Archivo principal:

```text
codigo/app/services/run_registry.py
```

Tests:

```text
codigo/tests/test_run_registry.py
```

El servicio expone:

```text
list_runs(runs_dir, dataset=None, current_stage=None, approved=None)
get_run(run_id, runs_dir)
get_run_artifacts(run_id, runs_dir)
compare_runs(run_ids, runs_dir)
```

## Contratos

El registro define tres contratos Pydantic:

```text
RunComparisonRow
MetricComparison
RunComparison
```

`RunComparisonRow` resume una ejecucion con:

- `run_id`;
- dataset;
- estado final;
- aprobacion;
- precision;
- recall;
- F1-score;
- tasa de falsos positivos;
- ruta del informe;
- ruta del snapshot.

`MetricComparison` indica, para cada metrica:

- si valores altos son mejores;
- mejor run;
- peor run;
- diferencia absoluta entre ambos.

`RunComparison` agrupa las filas y comparaciones para dos o mas ejecuciones.

## Capacidades

El registro permite:

- listar ejecuciones persistidas desde `index.json`;
- filtrar por dataset;
- filtrar por estado final;
- filtrar por aprobacion;
- cargar metadata completa de un snapshot;
- recuperar artefactos persistidos;
- comparar precision, recall, F1-score y FPR entre dos o mas runs.

## Comparacion de metricas

Para precision, recall y F1-score:

```text
higher_is_better = true
```

Para tasa de falsos positivos:

```text
higher_is_better = false
```

Esto permite que el registro identifique como mejor ejecucion la de menor FPR.

## Decisiones de diseno

- El registro lee `index.json` y los snapshots locales; no recalcula metricas.
- No modifica ejecuciones persistidas.
- No depende de LangGraph.
- No requiere que el pipeline se ejecute de nuevo.
- Devuelve objetos Pydantic reutilizables por la futura API minima.

## Tests

Comando focalizado:

```bash
conda run -n tfm_v2 python -m unittest codigo.tests.test_run_registry
```

Las pruebas cubren:

- listado con filtros por aprobacion, estado y dataset;
- carga de snapshot por `run_id`;
- lectura de artefactos;
- comparacion de dos runs;
- rechazo de comparaciones con menos de dos runs;
- error claro si falta un `run_id`.

## Ejemplo de uso

```python
from codigo.app.services.run_registry import compare_runs, list_runs

runs = list_runs("codigo/reports/runs", approved=True)
comparison = compare_runs(
    ["run-baseline", "run-candidate"],
    "codigo/reports/runs",
)
```

## Siguiente paso

Con persistencia, wrapper persistido y registro consultable, el siguiente hito
es definir un protocolo experimental local: generar varias ejecuciones
comparables y guardar una tabla de resultados para la memoria.
