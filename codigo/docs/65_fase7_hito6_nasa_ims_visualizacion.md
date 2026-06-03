# Fase 7 - Hito 6: estabilizacion NASA IMS y visualizacion diagnostica

Fecha: 2026-06-01.

## Objetivo

Corregir el comportamiento observado en la aplicacion web cuando NASA IMS se
ejecutaba como diagnostico: la run podia aparecer como `completed`, pero sin
metricas, sin predicciones y sin visualizacion 2D. El objetivo es hacer visible
la diferencia entre diagnostico y full run, y permitir una proyeccion util
aunque todavia no existan predicciones.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Hacer que NASA IMS sea ejecutable y observable desde la UI sin crear otro
runner ni otro endpoint de visualizacion.
```

Busquedas realizadas:

```text
rg -n -i "nasa|ims|visual|plot|artifact|status|completed" codigo/app codigo/frontend/src codigo/tests codigo/docs
rg -n "build_run_visualization|RunVisualizationData|visualization" codigo/app codigo/frontend/src codigo/tests
rg -n "nasa_ims|dataset_policy_id|execution_mode|status_for" codigo/app codigo/frontend/src codigo/tests
```

Piezas encontradas:

- `pipeline_runner.py` ya define la politica NASA IMS y aplica
  `nasa_ims_temporal_v1`.
- `run_visualization.py` ya construye el contrato read-only de visualizacion.
- `App.tsx` ya contiene defaults por dataset y la pestana `Visualizacion`.
- `RunVisualizationData` ya admite `projection_boundary=null`, metricas nulas
  y advertencias.

Decision: `extend`.

Motivo: el problema no requeria un runner nuevo. Bastaba con ampliar la
visualizacion existente para soportar modo diagnostico y ajustar los defaults
de la UI para que NASA IMS use la politica temporal en modo `full` cuando esa
politica esta declarada.

Impacto en compatibilidad: no se cambian contratos publicos. El endpoint
`GET /runs/{run_id}/visualization` sigue devolviendo `RunVisualizationData`,
pero ahora puede devolver `projection_available=true` con features solamente y
sin frontera de prediccion.

## Cambios implementados

Backend:

- `build_run_visualization(...)` ya no exige siempre `predictions`.
- Si existen `features` pero faltan `predictions`, calcula PCA 2D sobre las
  features numericas y devuelve puntos sin `anomaly_score`, `threshold` ni
  `predicted_anomaly`.
- La respuesta incluye una advertencia explicita: es una proyeccion
  diagnostica, no una visualizacion de anomalias predichas.
- Si faltan tambien las features, el comportamiento sigue degradando con
  `projection_available=false`.

Frontend:

- El default de `nasa_ims_bearing` pasa a:
  - `raw_path=codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen`;
  - `execution_mode=full`;
  - `dataset_policy_id=nasa_ims_temporal_v1`.
- Las runs `completed` sin evaluacion se etiquetan como `diagnostico` en la
  tabla y el detalle, para no confundirlas con una full run evaluada.
- La pestana `Visualizacion` muestra avisos cuando la proyeccion es solo
  diagnostica.
- La leyenda del scatter cambia a `ventanas proyectadas` cuando no hay
  predicciones.

## Validacion

Pruebas ejecutadas:

```text
python -m py_compile codigo/app/services/run_visualization.py
python -m unittest codigo.tests.test_run_visualization
npm run build
python -m codigo.scripts.run_dataset_pipeline_with_memory --dataset-id nasa_ims_bearing --adapter-id nasa_ims_bearing --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen --run-id nasa-fase7-full-visual-check --dataset-policy-id nasa_ims_temporal_v1 --execution-mode full
```

Resultado:

- `test_run_visualization` pasa con 3 tests.
- El frontend compila correctamente.
- La run `nasa-fase7-full-visual-check` termina en `completed`.
- La evaluacion no aprueba por metricas insuficientes, como era esperable:
  `precision=0.5`, `recall=1.0`, `f1=0.6667`, `FPR=1.0`.
- Aun sin aprobar, la run genera informe final, metricas, predicciones y
  visualizacion.
- Una run NASA diagnostica previa, `ui-nasa-ims-bearing-20260531170051`, ahora
  devuelve `projection_available=true` usando solo features.

## Limitaciones

- La politica temporal `nasa_ims_temporal_v1` sigue usando etiquetas proxy, no
  etiquetas oficiales NASA.
- La proyeccion diagnostica sin predicciones no debe interpretarse como
  deteccion de anomalias.
- La muestra preextraida es pequena y sirve para validar flujo, no para
  defender resultados industriales concluyentes.
