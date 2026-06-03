# Fase 7 - Hito 8.1: comparativa run-to-failure como panel de investigacion

Fecha: 2026-06-03.

## Objetivo

Empezar a convertir el panel principal de investigacion en una vista industrial
centrada en degradacion run-to-failure. El primer paso no crea otro runner ni
lanza experimentos automaticamente: amplia la comparacion existente de runs
para que pueda juzgar modelos y protocolos por metricas temporales, no solo por
F1.

## Capacidad buscada

```text
Comparar runs run-to-failure con lead time, falsas alarmas nominales,
tendencia del score, deteccion antes de fallo y fallos perdidos, manteniendo
las metricas binarias como apoyo/proxy.
```

## Inventario previo anti-duplicacion

Busquedas realizadas:

```text
rg -n "RunComparison|compare_runs|/runs/compare|degradation|temporal_series|RunVisualizationData|metrics_by_split|metric_families" codigo/app codigo/frontend/src codigo/tests codigo/docs
```

Piezas encontradas:

- `codigo/app/services/run_registry.py`: propietario canonico de
  `compare_runs(...)` y contratos `RunComparison`.
- `codigo/app/api/routes.py`: endpoint existente `GET /runs/compare`.
- `codigo/app/executors/evaluation.py`: calcula `degradation_metrics`.
- `codigo/app/graph/pipeline.py`: propaga resumen plano de degradacion a
  `MetricsReport.extra`.
- `codigo/app/services/run_visualization.py`: ya expone series temporales por
  run individual.
- `codigo/frontend/src/App.tsx`: vista de registro y comparacion basica.
- `codigo/frontend/src/types.ts`: espejo TypeScript del contrato.

Decision:

```text
extend
```

Motivo: la comparacion de runs ya existe y es la frontera natural para decidir
que modelo/protocolo es mejor. Crear un endpoint paralelo para NASA o para
run-to-failure duplicaria responsabilidad y volveria a atar la app a datasets
concretos.

## Cambios implementados

Backend:

- `RunComparisonRow` incorpora contexto de investigacion:
  `supervision_profile`, `label_source`, `label_granularity`, `model_name` y
  `metric_families`.
- La comparacion lee `MetricsReport.extra` y, si existe, el `metrics.json`
  completo del evaluador para extraer metricas de degradacion.
- `RunComparison` mantiene `metrics` para precision/recall/F1/FPR y anade
  `degradation_metrics` como bloque opcional.
- Las metricas temporales comparadas son:
  - deteccion antes de fallo;
  - lead time medio;
  - falsa alarma nominal media;
  - tendencia Spearman media del score;
  - fallos perdidos;
  - separacion inicio-final media cuando esta disponible.

Frontend:

- La vista de comparacion detecta si hay `degradation_metrics`.
- Si existen, muestra un bloque principal `Degradacion run-to-failure` antes de
  las metricas binarias.
- La tabla de runs comparadas muestra modelo, perfil, fuente de etiquetas,
  lead time, falsa alarma nominal y tendencia.
- Las metricas binarias quedan visibles como apoyo para no perder
  compatibilidad con `binary_fault_classification`.

## Fronteras mantenidas

- No se crea otro endpoint.
- No se crea runner NASA ni runner run-to-failure.
- No se recalculan metricas en frontend.
- No se presentan etiquetas proxy como oficiales.
- No se ejecuta codigo generado por agentes.
- No se salta todavia a RUL profundo: primero se consolida comparacion,
  health indicator y alerta temprana.

## Verificacion

Pruebas ejecutadas:

```text
python -m unittest codigo.tests.test_run_registry codigo.tests.test_api_runs
npm run build
python -c "from codigo.app.services.run_registry import compare_runs; ..."
curl -sS http://127.0.0.1:5173/
curl -sS http://127.0.0.1:8010/health
```

Resultado:

- `31` tests backend OK;
- build frontend OK;
- la comparacion entre `fase7-paso7-nasa-common-long` y
  `fase7-paso7-nasa-common-long-v2` devuelve `degradation_metrics`;
- Vite sirve la aplicacion en `http://127.0.0.1:5173/`.
- FastAPI responde `status=ok` en `http://127.0.0.1:8010/health`.

Validacion Docker:

- diferida en este entorno porque `docker` no esta disponible en la distro WSL
  activa.

## Siguiente paso

El siguiente bloque natural es usar esta comparacion enriquecida para lanzar o
seleccionar runs de varias familias de modelo sobre el mismo protocolo
run-to-failure:

- `pca_reconstruction_error`;
- `isolation_forest`;
- `one_class_svm`.

Despues, la visualizacion deberia evolucionar a small multiples temporales por
modelo y a un health indicator suavizado/normalizado para analistas.
