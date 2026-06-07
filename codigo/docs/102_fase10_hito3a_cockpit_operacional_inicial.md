# Fase 10 - Hito 10.3A - Cockpit operacional inicial

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Introducir una primera vista `Cockpit` como panel principal de la aplicacion,
clara y poco textual, sin eliminar la vista `Pipeline` existente ni cambiar
contratos backend.

Este subhito inicia Hito 10.3 despues de la modularizacion de Hito 10.2. No
pretende cerrar el rediseño visual final, sino crear el punto de entrada desde
el que se podra evolucionar el panel principal.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Crear una vista principal operacional que reutilice estado, runs, job activo,
LLM, health, run seleccionada y visualizacion persistida ya disponibles en App.
```

Piezas reutilizadas:

- `AppShell`, `ViewTabs`, `HealthSummary` y `StatusHeader`;
- estado existente de `App.tsx`;
- contratos `RunIndexEntry`, `RunSnapshot`, `RunVisualizationData`,
  `ApiRunJobStatus`, `LLMStatusResponse` y `HealthResponse`;
- helpers `formatMetric`, `formatSeconds`, `formatDate`, `confidenceText`,
  `llmStatusLabel` y `runStatusLabel`;
- acciones existentes de navegacion, ejecucion, refresh LLM y carga de run.

Decision:

```text
extend
```

Motivo: el frontend ya tenia todos los datos necesarios para una primera
consola. No hacia falta crear endpoints ni duplicar logica de runs.

## Cambios implementados

Se ha creado:

- `codigo/frontend/src/components/cockpit/CockpitView.tsx`

Se ha ampliado:

- `codigo/frontend/src/types/ui.ts`: `AppView` incorpora `cockpit`;
- `codigo/frontend/src/components/shell/ViewTabs.tsx`: nueva pestaña
  `Cockpit`;
- `codigo/frontend/src/components/shell/AppShell.tsx`: permite ocultar el
  resumen global cuando la vista principal ya lo resume;
- `codigo/frontend/src/App.tsx`: `cockpit` pasa a ser la vista inicial y se
  conecta con la navegacion a `Pipeline`, `Agentes` y `Visualizacion`;
- `codigo/frontend/src/styles.css`: estilos compactos y responsive para la
  nueva consola.

## Contenido del cockpit

La vista muestra:

- estado API;
- estado LLM/Ollama;
- dataset activo;
- contador de runs;
- runs aprobadas;
- estado del job;
- run foco con metricas principales;
- salud temporal si la visualizacion de la run esta cargada;
- recomendacion agentica persistida si existe;
- historial corto de runs;
- acciones directas hacia nueva run, ejecucion de plan, agentes y
  visualizacion.

## Criterios metodologicos

El cockpit no inventa resultados:

- las metricas vienen de runs persistidas;
- la recomendacion viene de `RunVisualizationData.agent_recommendation`;
- la salud temporal viene de `RunVisualizationData.temporal_series`;
- si la run no esta cargada, la UI lo muestra como ausencia de datos;
- el panel resume decisiones agenticas, no las sustituye.

La vista `Pipeline` sigue siendo el flujo completo de configuracion,
preflight, human review, ejecucion y detalle.

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

Pulir Hito 10.3B:

- mejorar jerarquia visual del cockpit tras verlo en navegador;
- decidir si el resumen superior global debe desaparecer tambien en otras
  vistas;
- cargar automaticamente una ultima run en el cockpit solo si no introduce
  latencia ni llamadas ocultas excesivas;
- añadir accesos a informe/evidencia desde la run foco;
- revisar solapes en desktop y movil.
