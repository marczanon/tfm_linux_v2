# Fase 10 - Hito 10.2D - Modularizacion Pipeline/Runs/Jobs

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Cerrar el ultimo corte estructural de `App.tsx` antes de empezar el cockpit
operacional, separando la UI de pipeline, preflight, jobs, historico de runs y
comparacion en modulos de dominio.

La intencion no era redisenar la experiencia todavia, sino dejar una base
manejable para hacerlo sin romper la aplicacion.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Extraer de App.tsx los bloques restantes de Pipeline/Runs/Jobs y sus helpers
sin modificar contratos backend ni comportamiento visible.
```

Busqueda realizada:

```text
rg -n "^function (PipelineDashboard|PipelineConfig|PreflightPanel|ExecutionStatus|RunHistoryPanel|RunContextBand|RuntimeTimeline|PlanView|JobView|CapabilityList|RunFiltersView|RunsTable|ComparisonView|LLMStatusPanel|isActiveJob|defaultRequest|normalizedRequest|mergeHumanApproval|emptyToNull|approvalValue|metricLabel|formatComparisonMetric)" codigo/frontend/src/App.tsx
rg -n "RuntimeTimeline|PlanView|JobView|CapabilityList|LLMStatusPanel|RunContextBand|PipelineDashboard|RunHistoryPanel" codigo/frontend/src/App.tsx codigo/frontend/src/components
```

Decision:

```text
adapt + extend
```

Motivo: todas las capacidades ya existian. El cambio correcto era moverlas a
propietarios claros, no duplicar flujos ni crear una vista paralela.

## Cambios implementados

Se han creado modulos de dominio:

- `codigo/frontend/src/components/pipeline/PipelineDashboard.tsx`
- `codigo/frontend/src/components/pipeline/PipelineConfig.tsx`
- `codigo/frontend/src/components/runs/RunHistoryPanel.tsx`
- `codigo/frontend/src/components/runs/RunContextBand.tsx`
- `codigo/frontend/src/components/plans/PlanView.tsx`
- `codigo/frontend/src/components/jobs/JobView.tsx`
- `codigo/frontend/src/components/datasets/CapabilityList.tsx`
- `codigo/frontend/src/components/llm/LLMStatusPanel.tsx`

Se han extraido helpers puros:

- `codigo/frontend/src/lib/forms.ts`
- `codigo/frontend/src/lib/jobs.ts`
- `codigo/frontend/src/lib/runComparison.ts`
- `codigo/frontend/src/lib/runRequest.ts`

`App.tsx` queda como orquestador de:

- estado React compartido;
- llamadas API;
- polling de jobs;
- seleccion de vista;
- carga de runs, visualizacion y memoria;
- handlers que conectan la UI con los contratos existentes.

## Resultado estructural

Antes de este corte:

```text
codigo/frontend/src/App.tsx: 2051 lineas
```

Despues de este corte:

```text
codigo/frontend/src/App.tsx: 715 lineas
```

Esto deja el frontend en una posicion mucho mas sana para introducir
`CockpitView` sin seguir aumentando el archivo central.

## Compatibilidad metodologica

El cambio mantiene la metodologia del proyecto:

- no cambia endpoints;
- no cambia contratos TypeScript/backend;
- no oculta los modos LLM;
- no introduce diagnosticos inventados por frontend;
- no sustituye decisiones agenticas por visualizaciones deterministas;
- mantiene preflight, human review, jobs, runs persistidas, informes, memoria y
  comparacion.

Los agentes siguen teniendo protagonismo: la interfaz solo ordena herramientas
de control y auditoria para que el usuario pueda elegir, ejecutar, observar y
revisar con claridad.

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

## Criterio de cierre

Hito 10.2 queda preparado para cerrarse como modularizacion base. El siguiente
paso logico es Hito 10.3: crear el panel principal operacional `CockpitView`,
usando los modulos extraidos en vez de tocar de nuevo un `App.tsx` monolitico.
