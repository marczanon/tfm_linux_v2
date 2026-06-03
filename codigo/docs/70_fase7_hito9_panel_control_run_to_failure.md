# Fase 7 - Hito 9.1: panel de control run-to-failure en Visualizacion

Fecha: 2026-06-03.

## Objetivo

Convertir la pestana `Visualizacion` en una lectura mas humana para el perfil
principal:

```text
run_to_failure_degradation
```

La curva temporal por ventanas se mantiene porque es util tecnicamente, pero se
anade una capa operacional encima para que un analista entienda rapidamente el
estado del motor, el riesgo, el flujo de ventanas y las metricas temporales
principales.

## Capacidad buscada

```text
Mostrar una run run-to-failure como panel de control de activo, manteniendo la
curva tecnica existente y relegando la PCA/frontera a diagnostico secundario.
```

## Reutilizacion aplicada

Busquedas realizadas:

```text
rg -n "TemporalSeriesPoint|TemporalRunSeries|VisualizationMetric|ProjectionBoundary|TemporalSeriesChart|ProjectionScatter|MetricBars" codigo/app codigo/frontend/src codigo/tests codigo/docs
```

Piezas encontradas:

- `codigo/app/schemas/api_visualization.py`: contrato canonico del endpoint.
- `codigo/app/services/run_visualization.py`: construccion read-only desde
  artefactos persistidos.
- `codigo/frontend/src/App.tsx`: pestana `Visualizacion`, grafica temporal y
  PCA 2D.
- `codigo/frontend/src/types.ts`: espejo TypeScript.
- `codigo/frontend/src/styles.css`: estilos de la pestana.
- `codigo/tests/test_run_visualization.py`: tests enfocados.

Decision:

```text
extend
```

Motivo: no se crea endpoint nuevo ni grafica paralela. El endpoint existente
de visualizacion recibe mas contexto del perfil y el frontend decide que bloque
es principal segun `supervision_profile`.

## Decision sobre la PCA y la frontera

La PCA actual si usa informacion de una run NASA/run-to-failure cuando existen
`features.csv` y `predictions.csv`: proyecta las ventanas/features a 2D y une
predicciones por `window_id`.

Sin embargo, la frontera que se dibuja no es la frontera real del detector:

- es una elipse visual aproximada calculada sobre puntos predichos como
  normales en la proyeccion PCA;
- el umbral real se aplica en el espacio original del modelo o sobre el score;
- en `run_to_failure_degradation` no debe usarse como criterio principal.

Decision:

- mantener la PCA como `Diagnostico 2D`;
- explicar en la UI que es secundaria;
- no eliminarla porque ayuda a ver separacion de ventanas y distribucion de
  anomalias;
- no presentarla como validacion temporal ni como frontera industrial real.

## Decision sobre metricas

Antes, la pestana mostraba Precision, Recall, F1 y FPR como bloque principal.
En una run NASA temporal esas metricas pueden existir porque hay
`label_source=temporal_proxy`, pero no son el criterio principal del perfil.

Decision:

- para `run_to_failure_degradation`, las metricas primarias son:
  - deteccion antes de fallo;
  - lead time medio;
  - falsas alarmas nominales;
  - tendencia del score;
  - fallos perdidos;
  - separacion inicio-final;
- Precision, Recall, F1, FPR, ROC-AUC y PR-AUC quedan como metricas binarias
  auxiliares/proxy;
- para `binary_fault_classification`, las metricas binarias siguen siendo
  principales.

## Cambios implementados

Backend:

- `VisualizationMetric` incluye ahora:
  - `metric_family`;
  - `value_kind`;
  - `note`.
- `RunVisualizationData` incluye:
  - `supervision_profile`;
  - `label_source`;
  - `label_granularity`;
  - `model_name`;
  - `metric_families`;
  - `primary_metrics`;
  - `auxiliary_metrics`;
  - `binary_metric_context`;
  - `projection_role`;
  - `projection_explanation`.
- `run_visualization.py` lee el estado final y el `metrics.json` completo del
  evaluador cuando esta disponible.
- Si detecta `run_to_failure_degradation`, rellena `primary_metrics` con la
  familia temporal y deja las binarias en `auxiliary_metrics`.

Frontend:

- `Visualizacion` detecta el perfil de la run.
- Para run-to-failure muestra:
  - cabecera con perfil, fuente de etiquetas y modelo;
  - tarjetas de metricas temporales;
  - metricas binarias auxiliares con contexto de etiquetas;
  - nuevo bloque `Panel de control / Estado del motor`;
  - estado actual, salud, riesgo, lead time, alertas y puntos criticos;
  - flujo visual `ventanas -> detector -> estado -> agente`;
  - tira de ventanas coloreada por `nominal`, `watch`, `warning`, `critical`;
  - curva temporal existente, ahora con bandas de estado de fondo;
  - PCA renombrada como diagnostico 2D cuando el perfil es temporal.
- Para perfil binario se mantiene la lectura anterior.

## Aclaracion: picos, alertas sostenidas y fallo

Cada barra o punto representa una ventana temporal. El detector asigna un
`anomaly_score` a cada ventana de forma local. Por eso puede ocurrir que una
ventana aparezca como critica y la siguiente vuelva a nominal: no significa que
el motor haya fallado y se haya recuperado, sino que esa ventana concreta tuvo
un score anomalo.

Para que el panel sea mas legible se separan dos conceptos:

- `primer pico`: primera ventana que dispara una anomalia puntual;
- `aviso sostenido`: primera zona con al menos tres ventanas consecutivas en
  `warning` o `critical`.

Tambien se exponen:

- `picos aislados`;
- `episodios` de alerta;
- `racha maxima` de ventanas consecutivas en alerta.

El fallo mostrado en una run de replay se obtiene de los metadatos temporales
del dataset o politica (`time_to_failure_seconds`, `relative_life`), no de una
prediccion RUL del modelo. Por eso la UI lo declara como fallo historico del
replay cuando esta disponible.

## Verificacion

Pruebas ejecutadas:

```text
python -m unittest codigo.tests.test_run_visualization
python -m unittest codigo.tests.test_run_visualization codigo.tests.test_api_runs
npm run build
python - <<'PY'
from codigo.app.services.run_visualization import build_run_visualization
v = build_run_visualization("fase7-paso7-nasa-common-long-v2", max_points=80)
print(v.supervision_profile)
print(v.primary_metrics)
print(v.auxiliary_metrics)
PY
```

Resultado:

- tests de visualizacion OK;
- tests de visualizacion + API runs OK;
- build frontend OK;
- la run real `fase7-paso7-nasa-common-long-v2` devuelve:
  - `supervision_profile=run_to_failure_degradation`;
  - `label_source=temporal_proxy`;
  - `model_name=pca_reconstruction_error`;
  - `primary_metrics` temporales;
  - `auxiliary_metrics` binarias;
  - `projection_role=diagnostic`;
  - estado temporal actual `critical`.

Verificacion adicional tras separar picos y avisos sostenidos:

- en `fase7-paso7-nasa-common-long-v2`, el primer pico aparece en vida relativa
  `0.043`, pero el primer aviso sostenido aparece en `0.652`;
- la run tiene picos aislados y varios episodios, por lo que no debe
  interpretarse cada barra critica temprana como fallo real del motor.

## Limitaciones

- La recomendacion agentica operacional aun no se muestra como tarjeta propia;
  queda para el siguiente paso de cierre.
- La cola global de activos/runs en `warning` o `critical` aun no esta
  implementada.
- La PCA sigue siendo diagnostica; no se usa como frontera real.
- RUL sigue sin estimarse como prediccion real. Solo se muestra tiempo restante
  cuando procede de replay historico.

## Siguiente paso

El siguiente bloque natural dentro del cierre de base es:

- anadir cola/listado de runs o activos priorizados por estado de salud;
- exponer interpretacion agentica operacional con evidencia citada;
- preparar small multiples para comparar modelos run-to-failure visualmente.
