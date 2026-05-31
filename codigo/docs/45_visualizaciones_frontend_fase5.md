# Visualizaciones y traduccion de eventos agenticos

Fecha: 2026-05-29.

## Objetivo

Ampliar el frontend de Fase 5 con dos capacidades visuales:

- traducir el JSON observable de cada evento agentico a una frase legible;
- anadir una pestaña `Visualizacion` con graficas de metricas y una proyeccion
  2D de ventanas/features con anomalias detectadas.

## Inventario previo

Busquedas realizadas:

```text
rg -n "metrics|artifact|artifacts|projection|embedding|pca|scatter|anomal|prediction|score|features" codigo/app codigo/tests codigo/docs codigo/frontend/src
rg -n "AgentRuntimeDetail|payload|runtime-json|RunDetailView|metric" codigo/frontend/src/App.tsx
```

Piezas encontradas:

- `RunSnapshot` ya guarda `metrics_path` y `artifacts_path`.
- `get_run_artifacts(...)` ya expone referencias a `features`,
  `predictions`, `metrics` y `report`.
- Las runs CWRU persistidas ya contienen `windows_features.csv` y
  `predictions.csv`.
- La pestaña `Agentes` ya muestra `AgentRuntimeEvent.payload` como JSON.
- No existia endpoint de contenido derivado para visualizacion 2D; el frontend
  no debe leer ficheros internos directamente.

Decision: `extend`.

Motivo: se reutiliza la persistencia existente y se anade una capa read-only de
datos derivados para visualizacion. No se crea otro runner ni se recalculan
modelos; solo se proyectan artefactos ya generados.

Impacto en compatibilidad: se anade `GET /runs/{run_id}/visualization` sin
modificar endpoints existentes.

## Implementacion

Backend:

- nuevo contrato `RunVisualizationData`;
- servicio `build_run_visualization(...)`;
- endpoint `GET /runs/{run_id}/visualization?max_points=...`;
- lectura de metricas desde el snapshot persistido;
- union por `window_id` entre `windows_features.csv` y `predictions.csv`;
- escalado y PCA 2D sobre features numericas;
- muestreo estable con prioridad parcial a anomalias;
- frontera visual aproximada como elipse sobre puntos predichos como normales.

La frontera se etiqueta explicitamente como aproximacion visual: el umbral real
del detector se aplica en el espacio original del modelo, no en la proyeccion
PCA 2D.

Frontend:

- nueva pestaña `Visualizacion`;
- selector de run persistida;
- grafica de barras para precision, recall, F1, FPR, ROC-AUC y PR-AUC;
- scatter SVG con puntos normales, anomalias detectadas y frontera aproximada;
- leyenda visual y tooltip por ventana;
- traduccion determinista del `payload` de cada `AgentRuntimeEvent` a una linea
  de texto humano junto al JSON tecnico.

## Criterios de aceptacion

- Al seleccionar una run con features y predicciones, la UI muestra metricas y
  proyeccion 2D.
- Las anomalias detectadas se distinguen visualmente de las ventanas normales.
- La frontera aproximada se muestra sin presentarla como frontera exacta del
  modelo.
- Al seleccionar un agente, se ve una lectura humana del evento antes del JSON.
- Si faltan artefactos, el endpoint degrada con `projection_available=false` y
  una advertencia.

## Verificacion

Comandos ejecutados:

```text
python -m unittest codigo.tests.test_run_visualization codigo.tests.test_api_runs
npm run build
curl -sS http://127.0.0.1:8010/runs/hito3-cwru-bg-20260529-01/visualization?max_points=80
curl -sS http://127.0.0.1:5174/api/runs/hito3-cwru-bg-20260529-01/visualization?max_points=80
```

Resultado:

- 22 tests relevantes pasan correctamente;
- el frontend compila correctamente;
- el endpoint directo devuelve metricas, puntos 2D, fuentes y frontera;
- el proxy Vite devuelve el mismo contrato desde el frontend local.

## Limitaciones

- La proyeccion usa PCA 2D para visualizacion; no sustituye al modelo original.
- La frontera es una elipse aproximada sobre puntos normales proyectados, no una
  frontera exacta de Isolation Forest o PCA reconstruction error.
- De momento se visualiza una muestra compacta para mantener la UI fluida.
