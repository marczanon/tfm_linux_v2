# Ejecutor de evaluacion CWRU

## Objetivo

Calcular metricas tecnicas a partir de las predicciones del modelo:

```text
codigo/models/cwru_bearing/predictions.csv
```

El ejecutor produce dos artefactos:

```text
codigo/reports/cwru_bearing/evaluation/metrics.json
codigo/reports/cwru_bearing/evaluation/evaluation_summary.md
```

## Implementacion

Archivo principal:

```text
codigo/app/executors/evaluation.py
```

Funciones:

- `evaluate_predictions(...)`: calcula metricas por split y guarda artefactos.
- `generate_evaluation_report(...)`: devuelve un `EvaluationExecutorResult`.

## Metricas

El split principal por defecto es `test`. Para cada split se calculan:

```text
precision
recall
f1_score
roc_auc
pr_auc
false_positive_rate
confusion_matrix
```

Si un split no contiene las dos clases, `roc_auc` y `pr_auc` se registran como
`null`.

## Verificacion

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 48 tests
OK
```

Ejecucion real:

```text
status = success
metrics_path = codigo/reports/cwru_bearing/evaluation/metrics.json
report_fragment_path = codigo/reports/cwru_bearing/evaluation/evaluation_summary.md
```

Metricas en `test`:

```text
precision = 0.9997164327236637
recall = 1.0
f1_score = 0.9998581962563812
roc_auc = 0.9999963634909033
pr_auc = 0.9999999396693899
false_positive_rate = 0.017094017094017096
confusion_matrix = {'tn': 115, 'fp': 2, 'fn': 0, 'tp': 7051}
```

Estas metricas son coherentes con un benchmark controlado como CWRU. Deben
interpretarse como validacion del pipeline y baseline inicial, no como garantia
de generalizacion industrial.

## Siguiente paso

Montar un grafo LangGraph minimo:

```text
codigo/app/graph/pipeline.py
codigo/tests/test_graph_pipeline.py
```

El primer grafo puede encadenar ejecutores deterministas y dejar preparados los
puntos donde despues entraran los agentes.
