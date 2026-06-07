# Fase 10 - Hito 10.6B - Comparacion visual de runs y modelos

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Extender `Visualizacion` con una comparacion visual de runs/modelos, usando la
comparacion existente de la aplicacion y sin crear un backend paralelo de
analitica visual.

El alcance queda limitado a frontend. No se cambian backend, contratos API,
esquemas Pydantic, grafo, agentes ni ejecutores.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mostrar una comparacion visual de modelos/runs dentro de Visualizacion
reutilizando compareRuns(...) y RunComparison.
```

Piezas canonicas reutilizadas:

- `compareRuns(...)` en `codigo/frontend/src/api.ts`;
- estado `runComparison`, `selectedCompareRunIds` y `comparingRuns` en
  `App.tsx`;
- `RunComparison` y `RunComparisonRow`;
- helpers `metricLabel(...)` y `formatComparisonMetric(...)`;
- estilos existentes de comparacion como referencia visual.

Decision:

```text
adapt
```

Motivo: la comparacion ya existia en el historico de runs. La mejora correcta
era exponerla tambien en `Visualizacion` como lectura visual de modelos, no
crear otra consulta ni otro contrato.

## Cambios implementados

En `App.tsx`:

- se pasan a `VisualizationView` los estados y handlers existentes de
  comparacion;
- no se crea estado nuevo;
- no se cambia `submitRunComparison(...)`.

En `VisualizationView`:

- se añade el panel `Comparacion visual`;
- se permite seleccionar runs desde la propia vista de visualizacion;
- se reutiliza el boton de comparacion sobre los IDs seleccionados;
- se muestran tarjetas de mejores metricas;
- se muestra una matriz visual por run con barras normalizadas;
- cuando hay metricas de degradacion, se prioriza `degradation_metrics`;
- cuando no hay degradacion, se usan metricas binarias.

En `styles.css`:

- se añaden chips compactos de seleccion de runs;
- se añaden tarjetas de mejores metricas;
- se añade matriz responsive de barras por run/modelo.

## Criterios metodologicos

La UI no recalcula resultados experimentales:

- las metricas salen de `RunComparison`;
- los valores por run salen de `RunComparisonRow`;
- la normalizacion de barras es solo representacion visual frontend;
- no se inventan metricas ni rankings nuevos;
- no se modifica ningun endpoint.

## Verificacion

Comando ejecutado:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

## Siguiente paso

El cierre del Hito 10.6 queda documentado en
`codigo/docs/111_fase10_cierre_hito6_visualizacion_2d_avanzada.md`. Despues,
la fase puede pasar al Hito 10.7 si se decide abordar la sala 3D industrial.
