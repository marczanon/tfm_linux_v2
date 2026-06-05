# Fase 10 - Hito 1: inventario frontend y mapa de componentes

Fecha: 2026-06-05.

Estado: implementado como hito documental previo a tocar codigo frontend.

Hoja de ruta: `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`.

## Objetivo

Preparar la reestructuracion del frontend como cockpit visual industrial sin
romper la aplicacion existente.

Este hito no cambia comportamiento. Su resultado es un mapa de responsabilidades
para saber que extraer, que conservar, que no duplicar y en que orden conviene
trabajar.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Inventariar el frontend actual y definir una modularizacion incremental para
convertirlo en cockpit visual sin crear otro frontend ni romper contratos.
```

Busquedas realizadas:

```text
rg -n "^export default function|^function [A-Z][A-Za-z0-9_]*|^function [a-z][A-Za-z0-9_]*|^const [A-Z][A-Za-z0-9_]*|^type [A-Z][A-Za-z0-9_]*|^interface [A-Z][A-Za-z0-9_]*" codigo/frontend/src/App.tsx
rg -n "^export async function|^async function|^function |^const API|fetchApi|/api/|/runs|/memory|/llm|/datasets" codigo/frontend/src/api.ts
rg -n "^export interface|^export type" codigo/frontend/src/types.ts
rg -n "^\\.[A-Za-z0-9_-]+|^@media|^:root|^body|^button|^input|^select|^textarea" codigo/frontend/src/styles.css
find codigo/frontend/src -maxdepth 3 -type f -printf '%p\n' | sort
wc -l codigo/frontend/src/App.tsx codigo/frontend/src/styles.css codigo/frontend/src/api.ts codigo/frontend/src/types.ts
```

Piezas canonicas:

- `codigo/frontend/src/App.tsx`: propietario actual de vistas, estado,
  componentes y helpers.
- `codigo/frontend/src/api.ts`: cliente API unico del frontend.
- `codigo/frontend/src/types.ts`: contratos TypeScript del backend.
- `codigo/frontend/src/styles.css`: estilos globales actuales.
- `codigo/frontend/src/main.tsx`: punto de montaje React.
- `codigo/frontend/package.json`: scripts y dependencias React/Vite.

Decision:

```text
extend + modularize
```

Motivo: no falta una app nueva. Falta separar responsabilidades de una app que
ya funciona y que concentra demasiado codigo en `App.tsx` y `styles.css`.

## Inventario cuantitativo

Tamanos observados:

```text
codigo/frontend/src/App.tsx     5126 lineas
codigo/frontend/src/styles.css  3469 lineas
codigo/frontend/src/api.ts       294 lineas
codigo/frontend/src/types.ts     548 lineas
```

Lectura:

- `App.tsx` ya contiene practicamente todo el producto.
- `styles.css` combina estilos historicos y una capa de dashboard mas reciente.
- `api.ts` y `types.ts` estan razonablemente acotados y deben conservarse como
  frontera estable.

## Mapa de App.tsx

### Constantes y tipos locales

Rango aproximado: lineas 79-200.

Responsabilidades:

- adaptador fallback;
- defaults por dataset;
- fases del pipeline;
- puntos de revision humana;
- etiquetas de fases;
- filtros de runs;
- tipo de vista activa;
- perfiles visuales de agentes.

Destino recomendado:

```text
src/constants/pipeline.ts
src/constants/agents.ts
src/constants/datasets.ts
```

### Orquestador principal

Rango aproximado: lineas 202-844.

Responsabilidades:

- estado global de la pantalla;
- carga de health, LLM, adaptadores y runs;
- polling de jobs;
- dry-run;
- ejecucion background;
- carga de detalle de run;
- carga y curacion de memoria;
- comparacion de runs;
- seleccion de dataset/agente/vista;
- render condicional de vistas principales.

Riesgo:

```text
Es la zona con mas acoplamiento. No debe extraerse de golpe.
```

Destino recomendado:

```text
src/App.tsx como orquestador fino al principio
src/hooks/useDashboardData.ts
src/hooks/useRunExecution.ts
src/hooks/useRunDetail.ts
src/hooks/useAgentMemory.ts
src/hooks/useRunComparison.ts
```

La extraccion de hooks debe hacerse despues de mover componentes puros o
subvistas, no como primer cambio.

### Shell y estado global

Rango aproximado: lineas 845-969.

Componentes:

- `AppShell`;
- `StatusHeader`;
- `HealthSummary`;
- `ErrorState`.

Destino recomendado:

```text
src/components/shell/AppShell.tsx
src/components/shell/StatusHeader.tsx
src/components/shell/HealthSummary.tsx
src/components/common/ErrorState.tsx
```

Estos componentes son buenos candidatos para una primera extraccion porque
dependen de props claras y no transforman datos complejos.

### Pipeline

Rango aproximado: lineas 970-1709.

Componentes:

- `PipelineDashboard`;
- `PipelineConfig`;
- `PreflightPanel`;
- `ExecutionStatus`;
- `RunHistoryPanel`;
- `PanelTitle`;
- `RunContextBand`;
- `ContextItem`;
- `ViewTabs`;
- `HumanReviewControls`.

Responsabilidades:

- configuracion de run;
- selector de dataset;
- controles LLM;
- revision humana;
- preflight;
- ejecucion;
- historial;
- filtros;
- comparacion;
- detalle de run.

Destino recomendado:

```text
src/views/PipelineView.tsx
src/components/pipeline/PipelineConfig.tsx
src/components/pipeline/PreflightPanel.tsx
src/components/pipeline/ExecutionStatus.tsx
src/components/runs/RunHistoryPanel.tsx
src/components/runs/RunContextBand.tsx
src/components/common/PanelTitle.tsx
src/components/common/ViewTabs.tsx
```

Observacion:

La futura Fase 10 debe separar `Panel principal` de `Pipeline`. El pipeline
actual no desaparece; pasa a ser una vista operativa o una seccion invocable
desde el cockpit.

### Agentes y memoria

Rango aproximado: lineas 1711-2584.

Componentes:

- `AgentObservabilityView`;
- `AgentNodeCard`;
- `AgentRuntimeDetail`;
- `AgentEventTranslation`;
- `AgentConversation`;
- `AgentMemoryPanel`;
- `MemoryStat`;
- `MemoryLifecycleStrip`;
- `MemoryDistribution`;
- `MemoryRuntimeFlow`;
- `MemoryRecordList`;
- `MemoryRecordDetail`.

Helpers cercanos:

- `retrievalEventLabel`;
- `memoryFlowMeta`;
- `memoryFlowItems`;
- `formatSimilarity`;
- `shortText`.

Destino recomendado:

```text
src/views/AgentsView.tsx
src/components/agents/AgentMap.tsx
src/components/agents/AgentRuntimeDetail.tsx
src/components/agents/AgentConversation.tsx
src/components/memory/AgentMemoryPanel.tsx
src/components/memory/MemoryRecordList.tsx
src/components/memory/MemoryRecordDetail.tsx
src/lib/agentRuntime.ts
src/lib/memoryRuntime.ts
```

Observacion:

Esta zona es donde se puede permitir mas texto. Debe conservar rationale,
debate, trazas, memoria y guardarrailes. La Fase 10 no debe simplificarla hasta
perder valor investigador.

### Planes, jobs, runs y comparacion

Rango aproximado: lineas 2585-3059.

Componentes:

- `RuntimeTimeline`;
- `PlanView`;
- `JobView`;
- `CapabilityList`;
- `RunFiltersView`;
- `RunsTable`;
- `ComparisonView`;
- `ComparisonMetricCard`;
- `ComparisonRowsTable`.

Destino recomendado:

```text
src/components/jobs/JobView.tsx
src/components/jobs/RuntimeTimeline.tsx
src/components/plans/PlanView.tsx
src/components/datasets/CapabilityList.tsx
src/components/runs/RunFiltersView.tsx
src/components/runs/RunsTable.tsx
src/components/runs/ComparisonView.tsx
```

Observacion:

`RuntimeTimeline` se usa conceptualmente tanto en ejecucion como en agentes. En
una extraccion real puede vivir en `components/jobs` o `components/agents`
segun el primer uso que se migre.

### Visualizacion

Rango aproximado: lineas 3060-3926.

Componentes:

- `VisualizationView`;
- `VisualizationMetricsPanel`;
- `VisualizationMetricCards`;
- `MotorControlPanel`;
- `AgentRecommendationPanel`;
- `RecommendationList`;
- `StateMeter`;
- `OperationalFlow`;
- `WindowStateStrip`;
- `MetricBars`;
- `TemporalSeriesChart`;
- `TemporalHealthBadge`;
- `ProjectionScatter`;

Helpers cercanos:

- `scoreAtX`;
- `temporalAxisLabel`;
- `healthStateLabel`;
- `recommendationStatusLabel`;
- `formatSeconds`.

Destino recomendado:

```text
src/views/VisualizationView.tsx
src/components/visualization/VisualizationMetricsPanel.tsx
src/components/visualization/MotorControlPanel.tsx
src/components/visualization/AgentRecommendationPanel.tsx
src/components/visualization/TemporalSeriesChart.tsx
src/components/visualization/ProjectionScatter.tsx
src/lib/visualization.ts
```

Observacion:

Esta sera una de las zonas principales de Fase 10, pero no debe recibir 3D
hasta que la visualizacion 2D y la separacion de componentes esten limpias.

### LLM, detalle de run, informes y render Markdown

Rango aproximado: lineas 3927-4396.

Componentes:

- `LLMStatusPanel`;
- `RunDetailView`;
- `MetricCard`;
- `ArtifactList`;
- `FinalReportPanel`;
- `ExecutionAuditPanel`;
- `ReportDebatePanel`;
- `ReportPreview`;
- `MarkdownDocumentPreview`;
- `ReportDocument`;
- `ReportBlocks`.

Helpers cercanos:

- `parseReportDocument`;
- `sanitizedReportLines`;
- `reportMeta`;
- `reportBlocks`;
- `inlineReportText`;
- `stripMarkdown`;
- `containsLocalPath`.

Destino recomendado:

```text
src/components/llm/LLMStatusPanel.tsx
src/components/runs/RunDetailView.tsx
src/components/reports/FinalReportPanel.tsx
src/components/reports/ExecutionAuditPanel.tsx
src/components/reports/ReportDebatePanel.tsx
src/components/reports/ReportDocument.tsx
src/lib/reportParsing.ts
```

Observacion:

El render de informes es relativamente independiente. Es buen candidato para
extraccion temprana despues de shell/common.

### Helpers compartidos

Rango aproximado: lineas 4397-5120.

Responsabilidades:

- estado de runs;
- defaults y normalizacion de request;
- revision humana;
- generacion de `run_id`;
- etiquetas de LLM, metricas, perfiles, estados, fuentes, memoria y eventos;
- construccion de conversacion agentica;
- extraccion segura desde payloads runtime;
- formateo de fechas, eventos, metricas y confianza;
- escalado para graficas SVG.

Destino recomendado:

```text
src/lib/runRequest.ts
src/lib/labels.ts
src/lib/formatters.ts
src/lib/agentRuntime.ts
src/lib/memoryRecords.ts
src/lib/reportParsing.ts
src/lib/visualization.ts
```

Regla:

```text
Antes de mover helpers, comprobar que no cierran sobre estado React.
```

## Mapa de api.ts

`api.ts` ya funciona como frontera unica con FastAPI.

Grupos:

- salud y LLM:
  - `getHealth`;
  - `getLLMStatus`;
- runs:
  - `listRuns`;
  - `getRun`;
  - `getRunArtifacts`;
  - `getRunReport`;
  - `getRunAuditReport`;
  - `getRunReportDebate`;
  - `getRunVisualization`;
  - `compareRuns`;
- datasets:
  - `listDatasetAdapters`;
  - `describeDataset`;
- ejecucion:
  - `createDryRun`;
  - `createBackgroundRun`;
  - `getRunJob`;
  - `getRunJobEvents`;
- memoria:
  - `listMemoryCollections`;
  - `listMemoryRecords`;
  - `getMemoryRecord`;
  - `curateMemoryRecord`;
  - `deleteMemoryRecord`;
- infraestructura:
  - `apiRequest`;
  - `apiTextRequest`;
  - `parseErrorDetail`;
  - `errorMessage`;
  - `normalizeBaseUrl`.

Decision:

```text
Mantener api.ts como frontera canonica durante Fase 10.
```

No conviene dividirlo aun. Si mas adelante crece mucho, podria separarse en
modulos por dominio, pero solo despues de estabilizar vistas.

## Mapa de types.ts

Grupos principales:

- ejecucion pipeline:
  - `PipelineRunExecutionMode`;
  - `PipelineRunStage`;
  - `PipelineRunRequest`;
  - `ApiRunRequest`;
  - `ApiRunResponse`;
- runs:
  - `RunIndexEntry`;
  - `RunSnapshot`;
  - `RunFilters`;
  - `ArtifactRef`;
- comparacion:
  - `RunComparisonRow`;
  - `MetricComparison`;
  - `RunComparison`;
- visualizacion:
  - `VisualizationMetric`;
  - `ProjectionPoint`;
  - `ProjectionBoundary`;
  - `TemporalSeriesPoint`;
  - `TemporalRunSeries`;
  - `TemporalSeriesData`;
  - `AgentOperationalRecommendation`;
  - `RunVisualizationData`;
- agentes runtime:
  - `AgentRuntimeEventKind`;
  - `AgentRuntimeEventSource`;
  - `AgentRuntimeEvent`;
- memoria:
  - `AgentMemoryTarget`;
  - `AgentMemoryCollection`;
  - `MemoryRole`;
  - `MemoryCollectionSummary`;
  - `MemoryRecordSummary`;
  - `ReasoningMemoryRecord`;
  - `MemoryCurationRequest`;
  - `MemoryCurationResponse`;
- datasets:
  - `DatasetAdapterInfo`;
  - `DatasetDescriptor`;
  - `DatasetDescribeRequest`;
  - `DatasetDescribeResponse`;
  - `DatasetCapabilityRule`;
  - `DatasetRunPolicy`;
  - `DatasetPipelinePaths`;
  - `DatasetPipelinePlan`;
- jobs y entorno:
  - `ApiRunJobStatus`;
  - `HealthResponse`;
  - `LLMStatusResponse`.

Decision:

```text
Mantener types.ts como espejo unico de contratos backend por ahora.
```

No dividir tipos antes de dividir vistas, para evitar imports cruzados y churn
innecesario.

## Mapa de styles.css

Observacion principal:

```text
styles.css contiene una primera capa historica y una capa de dashboard de
producto a partir de la seccion "Product dashboard layout".
```

Bloques detectados:

- tokens globales `:root`;
- base `body`, `button`, `input`, `select`, `textarea`;
- botones e iconos;
- bandas de estado;
- tabs;
- workspace y paneles;
- formularios;
- preflight;
- jobs;
- tablas de runs;
- comparacion;
- artefactos;
- informes;
- visualizacion temporal;
- panel de motor;
- recomendacion agentica;
- PCA/scatter;
- agentes;
- memoria;
- timeline;
- conversacion;
- responsive;
- segunda capa de dashboard de producto.

Riesgo:

```text
Hay clases repetidas y overrides por cascada. No conviene borrar estilos hasta
haber movido componentes y verificado pantallas.
```

Destino recomendado:

```text
src/styles/tokens.css
src/styles/base.css
src/styles/shell.css
src/styles/pipeline.css
src/styles/runs.css
src/styles/agents.css
src/styles/memory.css
src/styles/visualization.css
src/styles/reports.css
src/styles/responsive.css
```

Orden recomendado:

1. Mantener `styles.css` mientras se extraen componentes.
2. Extraer CSS por bloques solo cuando los componentes ya esten fuera de
   `App.tsx`.
3. Revisar duplicados y overrides al final de cada bloque, no antes.

## Dependencias actuales

`package.json` declara:

- `react`;
- `react-dom`;
- `lucide-react`;
- `typescript`;
- `vite`;
- `@vitejs/plugin-react`.

Decision:

```text
No anadir dependencias en Hito 10.1.
```

Para Hito 10.2 tampoco deberia hacer falta. `three` queda reservado para hitos
3D reales y una libreria de graficas solo debe entrar si evita fragilidad
medible frente al SVG/canvas actual.

## Estructura objetivo

Propuesta inicial:

```text
codigo/frontend/src/
  App.tsx
  main.tsx
  api.ts
  types.ts
  constants/
    agents.ts
    datasets.ts
    pipeline.ts
  hooks/
    useAgentMemory.ts
    useDashboardData.ts
    useRunComparison.ts
    useRunDetail.ts
    useRunExecution.ts
  views/
    CockpitView.tsx
    PipelineView.tsx
    AgentsView.tsx
    VisualizationView.tsx
  components/
    agents/
    common/
    datasets/
    jobs/
    llm/
    memory/
    pipeline/
    reports/
    runs/
    shell/
    visualization/
  lib/
    agentRuntime.ts
    formatters.ts
    labels.ts
    memoryRecords.ts
    reportParsing.ts
    runRequest.ts
    visualization.ts
  styles/
```

`CockpitView.tsx` no debe implementarse hasta Hito 10.2 o 10.3. El primer
movimiento debe ser dejar sitio para ella sin romper `Pipeline`.

## Orden de extraccion recomendado

### Paso A: componentes comunes y shell

Extraer:

- `PanelTitle`;
- `StatusPill`;
- `StatusItem`;
- `ErrorState`;
- `ViewTabs`;
- `AppShell`;
- `StatusHeader`;
- `HealthSummary`;

Motivo: props claras, bajo acoplamiento, verificacion visual sencilla.

### Paso B: parsing y render de informes

Extraer:

- `ReportDocument`;
- `ReportBlocks`;
- `FinalReportPanel`;
- `ExecutionAuditPanel`;
- `ReportDebatePanel`;
- helpers de `reportParsing`.

Motivo: zona relativamente aislada y util para reducir `App.tsx` sin tocar
ejecucion.

### Paso C: visualizacion

Extraer:

- `VisualizationView`;
- `MotorControlPanel`;
- `TemporalSeriesChart`;
- `ProjectionScatter`;
- helpers de visualizacion.

Motivo: sera foco de Fase 10 y conviene aislarla antes de embellecerla.

### Paso D: agentes y memoria

Extraer:

- `AgentObservabilityView`;
- `AgentConversation`;
- `AgentMemoryPanel`;
- `MemoryRecordDetail`;
- helpers de eventos y memoria.

Motivo: alto valor investigador, pero mas acoplamiento con runtime y memoria.

### Paso E: pipeline y runs

Extraer:

- `PipelineDashboard`;
- `PipelineConfig`;
- `RunHistoryPanel`;
- `PlanView`;
- `JobView`;
- `RunsTable`;
- `ComparisonView`.

Motivo: es la zona mas operativa y con mas callbacks. Conviene moverla cuando
common, reports y visualizacion ya hayan demostrado la pauta.

### Paso F: hooks de orquestacion

Extraer:

- `useDashboardData`;
- `useRunExecution`;
- `useRunDetail`;
- `useAgentMemory`;
- `useRunComparison`.

Motivo: debe hacerse al final, cuando las vistas ya tengan fronteras claras.
Separar estado demasiado pronto puede crear duplicacion o renders dificiles de
razonar.

## Frontera con el futuro cockpit

El panel principal de Fase 10 no debe ser una version mas bonita de `Pipeline`.
Debe ser una vista nueva que consume datos ya cargados:

- health;
- LLM status;
- adapters;
- visible runs;
- selected run;
- selected visualization;
- selected recommendation;
- job activo;
- errores.

Por tanto, `CockpitView` deberia aparecer despues de tener un shell claro y
antes de redisenar profundamente `Pipeline`.

## Riesgos detectados

### App.tsx demasiado grande

Mitigacion: extraccion por componentes puros antes de hooks.

### styles.css con overrides historicos

Mitigacion: no borrar estilos al principio; separar CSS cuando cada bloque ya
tenga componente propietario.

### props muy largas

Mitigacion: no introducir stores globales todavia. Usar props explicitas hasta
que el acoplamiento real justifique hooks o context.

### perdida de flujos existentes

Mitigacion: mantener `Pipeline`, `Agentes` y `Visualizacion` accesibles durante
toda la migracion.

### caidas a fallback mal comunicadas

Mitigacion: las vistas nuevas deben mostrar estado LLM, eventos de correccion de
contrato y fallback real como hechos visibles.

## Criterios de cierre del hito

El Hito 10.1 queda cerrado con:

- inventario de componentes de `App.tsx`;
- mapa de `api.ts`;
- mapa de `types.ts`;
- mapa de `styles.css`;
- estructura objetivo propuesta;
- orden de extraccion recomendado;
- decision explicita de no crear frontend paralelo;
- decision explicita de no tocar backend en este hito.

No se ejecuta `npm run build` porque no se han modificado archivos del
frontend; la verificacion aplicable a este hito es documental.

## Siguiente paso

Avanzar al Hito 10.2 con un cambio pequeno:

```text
Crear estructura de carpetas frontend y extraer componentes comunes/shell,
manteniendo el comportamiento actual y ejecutando npm run build.
```

El primer cambio de codigo recomendado es extraer `PanelTitle`, `StatusPill`,
`StatusItem`, `ErrorState`, `ViewTabs`, `AppShell`, `StatusHeader` y
`HealthSummary`. Si esa extraccion compila y la app mantiene la misma lectura,
se podra introducir el `CockpitView` como vista principal en el siguiente
subpaso.
