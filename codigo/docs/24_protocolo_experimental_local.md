# Protocolo experimental local

## Objetivo

Implementar el Hito 4 de la Fase 2: pasar de ejecuciones aisladas a un conjunto
pequeno de experimentos comparables, sin introducir nuevos modelos ni contratos
que no tengan ejecutor determinista.

El protocolo se apoya en dos piezas ya existentes:

- `run_and_persist_cwru_pipeline(...)`, que ejecuta el grafo y guarda un
  snapshot local por `run_id`;
- `compare_runs(...)`, que compara metricas persistidas entre ejecuciones.

## Servicio implementado

El modulo principal es:

```text
codigo/app/services/experiment_protocol.py
```

Contratos principales:

- `ExperimentSpec`: una ejecucion concreta con `experiment_id`, `run_id`,
  descripcion y `ModelingConfig`;
- `ExperimentPlan`: manifiesto del conjunto experimental;
- `ExperimentRunSummary`: resumen de cada snapshot generado;
- `ExperimentPlanResult`: resultado agregado con rutas y comparacion.

Funciones principales:

- `default_cwru_experiment_plan(...)`;
- `run_cwru_experiment_plan(...)`.

## Plan inicial

El primer plan local es:

```text
cwru_iforest_threshold_v1
```

Incluye dos ejecuciones comparables de Isolation Forest:

| Experimento | Cambio controlado |
| --- | --- |
| `baseline_threshold_099` | `threshold_quantile=0.99`, `n_estimators=200` |
| `conservative_threshold_100` | `threshold_quantile=1.0`, `n_estimators=200` |

La unica variable que cambia es el cuantil usado para fijar el umbral de
anomalia. El resto del pipeline permanece estable: manifiesto, perfilado,
limpieza, estructuracion temporal, algoritmo, semilla y numero de arboles.

## Regla de alcance

No se ha anadido ningun modelo nuevo. Aunque el contrato `ModelingConfig`
contempla otros algoritmos futuros, el protocolo solo usa `isolation_forest`
porque es el ejecutor determinista ya implementado y validado.

## Artefactos generados

Cada ejecucion conserva su snapshot en:

```text
codigo/reports/runs/<run_id>/
```

El plan experimental conserva sus artefactos agregados en:

```text
codigo/experiments/cwru_local/cwru_iforest_threshold_v1/
```

Archivos principales:

```text
experiment_plan.json
comparison.json
results_table.md
baseline_threshold_099/models/
baseline_threshold_099/evaluation/
baseline_threshold_099/final_report.md
conservative_threshold_100/models/
conservative_threshold_100/evaluation/
conservative_threshold_100/final_report.md
```

Los modelos, predicciones, metricas e informes se escriben dentro de la carpeta
del experimento para evitar sobrescrituras entre ejecuciones comparables.

## Resultados reales

La ejecucion local sobre CWRU ha generado dos runs completados y aprobados:

| Experimento | Run ID | Precision | Recall | F1 | FPR |
| --- | --- | ---: | ---: | ---: | ---: |
| `baseline_threshold_099` | `cwru_iforest_threshold_v1_baseline_threshold_099` | 0.9991 | 1.0000 | 0.9996 | 0.0513 |
| `conservative_threshold_100` | `cwru_iforest_threshold_v1_conservative_threshold_100` | 0.9996 | 1.0000 | 0.9998 | 0.0256 |

La comparacion identifica como mejor ejecucion global al experimento
`conservative_threshold_100` para precision, F1 y tasa de falsos positivos. El
recall queda empatado en 1.0000, por lo que el registro conserva el primer run
con ese valor como mejor fila para esa metrica.

## Validacion

Validacion focalizada del hito:

```text
conda run -n tfm_v2 python -m unittest codigo.tests.test_experiment_protocol
```

Resultado:

```text
Ran 3 tests in 0.037s
OK
```

Validacion real del protocolo:

```text
from codigo.app.services.experiment_protocol import (
    default_cwru_experiment_plan,
    run_cwru_experiment_plan,
)

result = run_cwru_experiment_plan(default_cwru_experiment_plan())
```

Salida principal:

```text
codigo/experiments/cwru_local/cwru_iforest_threshold_v1/results_table.md
```

## Encaje con la Fase 2

Este hito deja preparada la base para:

- repetir planes experimentales locales con `run_id` trazable;
- comparar runs desde el registro sin recalcular metricas;
- llevar una tabla reproducible a la memoria;
- exponer resultados mediante una API minima en el siguiente hito activo.

Human Review queda pospuesto hasta que exista una aplicacion o interfaz donde
la logica de aprobacion humana pueda disenarse con el contexto real de uso.
