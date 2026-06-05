# Fase 10 - Hito 2B: modularizacion runs, informes y visualizacion

Fecha: 2026-06-05.

Estado: implementado.

Hoja de ruta: `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`.

Subhito previo: `codigo/docs/98_fase10_hito2a_shell_common_frontend.md`.

## Objetivo

Continuar la reestructuracion del frontend reduciendo el peso de `App.tsx` y
dando propietario propio a tres dominios que ya existian:

- detalle de run;
- informes y render Markdown;
- visualizacion operacional 2D/run-to-failure.

El objetivo sigue siendo estructural. No se cambian estilos, APIs, contratos ni
comportamiento de ejecucion.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mover bloques existentes de App.tsx a modulos de dominio, manteniendo la misma
UI y preparando el futuro CockpitView de Fase 10.
```

Piezas reutilizadas:

- `RunDetailView`;
- `MetricCard`;
- `ArtifactList`;
- paneles de informe final, auditoria y debate;
- render Markdown filtrado de rutas locales;
- `VisualizationView`;
- panel temporal run-to-failure;
- panel de recomendacion agentica;
- grafica SVG temporal;
- scatter PCA/proyeccion 2D;
- helpers de metricas, segundos, confianza y etiquetas.

Decision:

```text
move + extract helpers
```

Motivo: los bloques ya funcionaban. La mejora era separar responsabilidades y
preparar los siguientes cambios visuales sin seguir creciendo dentro de
`App.tsx`.

## Cambios implementados

### Runs

Nuevo archivo:

```text
codigo/frontend/src/components/runs/RunDetailView.tsx
```

Contiene:

- `RunDetailView`;
- `MetricCard`;
- `ArtifactList`.

### Informes

Nuevos archivos:

```text
codigo/frontend/src/components/reports/ReportPanels.tsx
codigo/frontend/src/components/reports/ReportDocument.tsx
```

Contienen:

- `FinalReportPanel`;
- `ExecutionAuditPanel`;
- `ReportDebatePanel`;
- render Markdown compacto;
- parseo de secciones;
- filtrado de rutas locales y fuentes tecnicas.

### Visualizacion

Nuevo archivo:

```text
codigo/frontend/src/components/visualization/VisualizationView.tsx
```

Contiene:

- `VisualizationView`;
- `VisualizationMetricsPanel`;
- `MotorControlPanel`;
- `AgentRecommendationPanel`;
- `TemporalSeriesChart`;
- `ProjectionScatter`;
- helpers visuales de perfil, etiquetas, estados, escalado y metricas.

### Helpers comunes

Se amplia:

```text
codigo/frontend/src/lib/formatters.ts
```

Con:

- `formatMetric`;
- `formatSeconds`;
- `confidenceText`.

Se amplia:

```text
codigo/frontend/src/lib/labels.ts
```

Con:

- `runStatusLabel`.

## Resultado estructural

Antes del Hito 10.2:

```text
codigo/frontend/src/App.tsx  5126 lineas
```

Tras Hito 10.2A:

```text
codigo/frontend/src/App.tsx  4895 lineas
```

Tras este Hito 10.2B:

```text
codigo/frontend/src/App.tsx  3511 lineas
```

Lectura:

```text
App.tsx sigue siendo grande, pero ya empieza a ser un orquestador en vez de un
archivo que posee toda la UI.
```

## No cambios deliberados

- No se modifica `api.ts`.
- No se modifica `types.ts`.
- No se modifica `styles.css`.
- No se anaden dependencias.
- No se cambia la vista por defecto.
- No se introduce todavia `CockpitView`.
- No se cambian endpoints ni contratos backend.
- No se altera la logica de ejecucion, polling, memoria o seleccion de runs.
- No se cambian graficas ni calculos visuales.

## Verificacion

Comando ejecutado:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
build correcto
```

Pendiente recomendado:

- revision visual manual en navegador;
- comprobar una run con informe;
- comprobar una run con visualizacion temporal;
- comprobar una run sin visualizacion para estados vacios.

## Riesgo residual

El riesgo principal es visual, no de contrato:

```text
alguna seccion puede haber conservado JSX y clases, pero conviene validar en
navegador que la composicion se mantiene identica.
```

Mitigacion aplicada:

- no se han tocado clases CSS;
- no se ha modificado `styles.css`;
- build TypeScript/Vite correcto;
- los componentes se han movido por dominios completos.

## Siguiente paso

Antes de introducir `CockpitView`, conviene hacer un tercer subpaso estructural
moderado:

```text
extraer Agentes/Memoria o Pipeline/Runs segun prioridad.
```

Recomendacion:

1. Extraer `AgentObservabilityView` y memoria si se quiere proteger el nucleo
   investigador.
2. Extraer `PipelineDashboard` si se quiere preparar antes la vista principal.

Despues de uno de esos dos cortes, `App.tsx` quedara suficientemente pequeno
para introducir `CockpitView` con menos riesgo.
