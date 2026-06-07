# Fase 10 - Cierre Hito 10.6 - Visualizacion 2D avanzada

Fecha: 2026-06-06.

Estado: cerrado y verificado.

## Objetivo

Cerrar el Hito 10.6 como bloque frontend de sala 2D avanzada para inspeccion
temporal, Health Index, episodios de alerta y comparacion visual de
runs/modelos.

El cierre mantiene el alcance limitado a frontend y documentacion. No se
cambian backend, contratos API, esquemas Pydantic, grafo, agentes, ejecutores,
datasets ni memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Consolidar Visualizacion como sala 2D avanzada reutilizando RunVisualizationData,
TemporalRunSeries, RunComparison y compareRuns(...).
```

Busquedas y piezas revisadas:

- `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`;
- `codigo/docs/109_fase10_hito6a_visualizacion_2d_temporal_hi.md`;
- `codigo/docs/110_fase10_hito6b_comparacion_visual_runs_modelos.md`;
- `codigo/frontend/src/components/visualization/VisualizationView.tsx`;
- `codigo/frontend/src/App.tsx`;
- endpoints existentes `GET /runs/{run_id}/visualization` y
  `GET /runs/compare`.

Decision:

```text
reuse
```

Motivo: los propietarios canonicos ya existen y los subhitos 10.6A/10.6B
extienden la vista correcta sin crear contratos ni flujos paralelos. El cierre
no necesita una tercera implementacion; necesita verificacion y trazabilidad.

## Resultado cerrado

El Hito 10.6 queda compuesto por:

- `10.6A`: grafica temporal reforzada con Health Index y rail de episodios de
  alerta/critico.
- `10.6B`: comparacion visual de runs/modelos dentro de `Visualizacion`,
  reutilizando `RunComparison` y el estado existente de comparacion.

La vista `Visualizacion` queda preparada para:

- leer score temporal, riesgo, Health Index y estados desde
  `RunVisualizationData`;
- mostrar umbral, primer aviso, aviso persistente, onset confirmado y fallo de
  referencia cuando el contrato los trae;
- agrupar episodios visuales desde `TemporalSeriesPoint.health_state`;
- comparar modelos con metricas de degradacion cuando existen y caer a metricas
  binarias cuando no existen;
- conservar PCA 2D como diagnostico secundario.

## Verificacion realizada

Build frontend:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Servicios y proxy:

```text
GET http://127.0.0.1:8010/health
GET http://127.0.0.1:5173/api/health
GET http://127.0.0.1:5173/api/runs
```

Resultado: backend y proxy responden, y `/api/runs` devuelve runs historicos
persistidos.

Contratos de visualizacion validados con runs reales:

```text
GET /api/runs/fase9-hito4b-ae-readiness-lite-001_autoencoder_dense/visualization
```

Resultado: responde con `TemporalRunSeries`, `health_index`,
`health_state`, episodios, marcadores temporales, metricas primarias y
recomendacion agentica.

Contrato de comparacion validado con tres modelos reales:

```text
GET /api/runs/compare?run_ids=fase9-hito4b-ae-readiness-lite-001_autoencoder_dense&run_ids=fase9-hito4b-ae-readiness-lite-001_one_class_svm&run_ids=fase9-hito4b-ae-readiness-lite-001_pca_reconstruction_error
```

Resultado: responde con filas por run/modelo, metricas binarias y
`degradation_metrics` de run-to-failure.

## Criterios de cierre

- La sala 2D usa datos persistidos y contratos existentes.
- La UI no inventa metricas ni diagnosticos.
- No hay backend paralelo de analitica visual.
- No se han tocado servicios, scripts, tests, memoria ni recursos academicos.
- La siguiente evolucion puede pasar a Hito 10.7 si se decide explorar la sala
  3D industrial.

## Siguiente paso

El siguiente paso natural de la Fase 10 es el Hito 10.7: sala 3D de
visualizacion industrial, aislada y opcional, manteniendo la sala 2D como base
estable de lectura.
