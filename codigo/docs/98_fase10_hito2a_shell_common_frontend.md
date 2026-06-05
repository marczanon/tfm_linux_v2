# Fase 10 - Hito 2A: extraccion shell/common frontend

Fecha: 2026-06-05.

Estado: implementado.

Hoja de ruta: `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`.

Inventario previo:
`codigo/docs/97_fase10_hito1_inventario_frontend_mapa_componentes.md`.

## Objetivo

Iniciar el Hito 10.2 separando componentes de shell y componentes comunes del
frontend, sin cambiar comportamiento, estilos ni contratos API.

Este paso prepara el cockpit visual de Fase 10 reduciendo el tamano efectivo de
`App.tsx`, pero mantiene intactos los flujos actuales de `Pipeline`, `Agentes`
y `Visualizacion`.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Extraer componentes frontend de shell/common que ya existen dentro de App.tsx,
sin crear una nueva app ni cambiar experiencia de usuario.
```

Piezas reutilizadas:

- `AppShell`;
- `StatusHeader`;
- `HealthSummary`;
- `ViewTabs`;
- `PanelTitle`;
- `StatusItem`;
- `StatusPill`;
- `ErrorState`;
- `llmStatusLabel`;
- tipo local de vista `AppView`.

Decision:

```text
adapt + move
```

Motivo: los componentes ya existian y funcionaban. La mejora consiste en darles
propietario de archivo para que el siguiente hito pueda introducir `CockpitView`
sin seguir aumentando `App.tsx`.

## Cambios implementados

### Nuevas carpetas

```text
codigo/frontend/src/components/common/
codigo/frontend/src/components/shell/
codigo/frontend/src/lib/
codigo/frontend/src/types/
```

### Componentes comunes

Se extraen a `components/common`:

- `ErrorState.tsx`;
- `PanelTitle.tsx`;
- `StatusItem.tsx`;
- `StatusPill.tsx`.

Estos componentes mantienen las mismas clases CSS y el mismo JSX que tenian
dentro de `App.tsx`.

### Shell

Se extraen a `components/shell`:

- `AppShell.tsx`;
- `StatusHeader.tsx`;
- `HealthSummary.tsx`;
- `ViewTabs.tsx`.

`AppShell` sigue mostrando:

- marca actual;
- navegacion `Pipeline` / `Agentes` / `Visualizacion`;
- estado API;
- estado LLM;
- cabecera con boton `Actualizar`;
- resumen de health;
- errores globales;
- contenido de la vista activa.

### Helpers y tipos UI

Se crea:

- `codigo/frontend/src/lib/labels.ts` con `llmStatusLabel`;
- `codigo/frontend/src/types/ui.ts` con `AppView`.

No se modifica `codigo/frontend/src/types.ts` para no mezclar contratos backend
con tipos puramente visuales.

### App.tsx

`App.tsx` deja de definir esos componentes y pasa a importarlos.

No se extrae todavia:

- estado global;
- hooks;
- `PipelineDashboard`;
- `AgentObservabilityView`;
- `VisualizationView`;
- render de informes;
- helpers de runtime;
- CSS.

## No cambios deliberados

- No cambia la vista activa por defecto.
- No se introduce todavia `CockpitView`.
- No se toca `api.ts`.
- No se toca `types.ts`.
- No se toca `styles.css`.
- No se anaden dependencias.
- No se cambian clases CSS.
- No se cambian endpoints.
- No se cambia la logica de ejecucion, polling, memoria, informes ni
  visualizacion.

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

Tambien se ejecuto:

```text
git diff --check
```

Resultado:

```text
sin errores de whitespace
```

Smoke local:

```text
cd codigo/frontend
npm run dev
curl -sS http://127.0.0.1:5173/
```

Resultado:

```text
Vite sirve la app en http://127.0.0.1:5173/ y devuelve el HTML de entrada.
```

## Riesgo residual

El cambio es una extraccion estructural. Aunque la compilacion pasa, todavia
conviene hacer una revision visual manual al levantar Vite en el siguiente hito
o subhito.

Riesgo principal:

```text
Que algun detalle visual dependa de cascada CSS no evidente.
```

Mitigacion:

- no se han cambiado clases;
- no se ha tocado `styles.css`;
- build de produccion correcto;
- el siguiente paso debe validar la UI en navegador antes de introducir
  `CockpitView`.

## Siguiente paso

Continuar Hito 10.2 con un subpaso B:

```text
Introducir una vista Cockpit inicial como panel principal, manteniendo Pipeline
como vista operativa accesible y sin eliminar ningun flujo existente.
```

Ese `CockpitView` debe consumir datos ya presentes en `App.tsx`:

- `health`;
- `llmStatus`;
- `runs`;
- `selectedRunId`;
- `selectedVisualization`;
- `job`;
- `adapters`;
- `error`.

La vista debe ser ligera, clara y poco textual. La profundidad agentica seguira
en `Agentes`.
