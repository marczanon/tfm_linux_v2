# Fase 10 - Hito 10.9E-A - Metricas como subpantalla de Visualizacion

Fecha: 2026-06-06.

Estado: implementado y validado con run real.

## Objetivo

Reducir la carga visual de `Visualizacion` moviendo el apartado de metricas a
una seccion interna propia, igual que se hizo con `Memoria` dentro de
`Agentes`.

La vista deja de mezclar siempre selector, graficas y metricas. Ahora las
metricas quedan disponibles bajo demanda:

```text
Visualizacion -> Metricas
```

## Alcance

Incluido:

- nueva seccion interna `Metricas`;
- `Metricas` dentro del rail de secciones de `Visualizacion`;
- eliminacion del panel fijo de metricas en la cabecera;
- panel superior de seleccion de run a ancho completo;
- `VisualizationMetricsPanel` reutilizado sin cambiar contratos;
- responsive desktop/movil sin scroll horizontal.

No incluido:

- cambios backend;
- nuevos endpoints;
- nuevas metricas;
- rediseño completo de graficas;
- cambios en comparacion, serie, mapa o 3D salvo el encaje de navegacion.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Separar metricas de la primera lectura de Visualizacion y mostrarlas solo como
subpantalla interna.
```

Piezas revisadas:

- `VisualizationView`;
- `VisualizationMetricsPanel`;
- `VisualizationMetricCards`;
- `MetricBars`;
- `RunVisualizationData`;
- estilos `visualization-workspace`, `visualization-panel` y
  `visual-section-tabs`.

Decision:

```text
adapt
```

Motivo: las metricas, contratos y renderizadores ya existian. Solo hacia falta
reubicarlas dentro de la navegacion interna.

## Implementacion

Archivos modificados:

- `codigo/frontend/src/components/visualization/VisualizationView.tsx`;
- `codigo/frontend/src/styles.css`;
- `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`;
- `codigo/docs/120_fase10_hito9_identidad_visual_industrial_plan.md`;
- `codigo/docs/README.md`.

Cambios:

- `VisualSectionId` incorpora `metrics`;
- las opciones run-to-failure pasan a:

```text
Estado | Metricas | Agente | Comparar | Serie | Mapa
```

- las opciones no run-to-failure mantienen el foco visual primero:

```text
Comparar | Serie | Mapa | Metricas
```

- el panel de metricas se renderiza solo cuando `visibleVisualSection ===
  "metrics"`;
- el panel de seleccion de run y modo 2D/3D pasa a ocupar la fila superior;
- el rail de secciones usa columnas adaptativas para admitir 4-6 secciones.

## Verificacion

Build:

```text
cd codigo/frontend
npm run build
```

Resultado: correcto.

Playwright:

- desktop `1440x1100`: `Metricas` existe como pestaña, no aparece como panel
  fijo inicial, aparece al activarla, sin scroll horizontal;
- movil `390x920`: mismo comportamiento, sin scroll horizontal.

Capturas:

```text
/tmp/tfm-frontend-109e-metrics-desktop.png
/tmp/tfm-frontend-109e-metrics-mobile.png
```

Validacion posterior:

- durante la primera captura el backend/API respondia con `HTTP 500 Internal
  Server Error` y el sistema aparecia `offline`;
- posteriormente se levanta backend en `127.0.0.1:8010` y `/runs` vuelve a
  listar las ejecuciones persistidas;
- el usuario revisa `Visualizacion` con una run real y confirma que el apartado
  queda correcto;
- `10.9E` no mantiene pendientes funcionales.

## Siguiente paso

Nota posterior: `10.9F` queda implementado y cerrado en
`codigo/docs/126_fase10_hito9f_qa_visual_global.md`.

Nota posterior: `10.10` queda implementado en
`codigo/docs/127_fase10_hito10_informe_evidencia_artefactos.md`.

Continuar con `10.11`:

- pulido final;
- QA visual;
- smoke local y posible rebuild Docker.
