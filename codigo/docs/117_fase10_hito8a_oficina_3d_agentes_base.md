# Fase 10 - Hito 10.8A - Oficina 3D de agentes base

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Abrir Hito 10.8 con una oficina 3D opcional dentro de `Agentes`, manteniendo
la oficina 2D actual como modo por defecto y permitiendo mostrar u ocultar el
3D con un boton `2D`/`3D`.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Crear una oficina 3D opcional de agentes, reutilizando el runtime de Agentes y
el patron Three.js ya validado en la sala 3D industrial.
```

Piezas revisadas y reutilizadas:

- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`;
- `codigo/frontend/src/lib/agentRuntime.ts`;
- `AGENT_PROFILES`;
- `AgentRuntimeEvent`;
- `eventsForAgent(...)`;
- `eventOwnerId(...)`;
- `agentLabel(...)`;
- `codigo/frontend/src/components/visualization/WebGLFallback.tsx`;
- `supportsWebGL(...)` desde `visualization3d.ts`;
- patron de `React.lazy`, `Suspense`, `OrbitControls` y validacion Playwright
  del Hito 10.7.

Decision:

```text
extend + new isolated component
```

Motivo: `Agentes` ya contenia la oficina 2D, timeline, detalle, memoria y
conversacion. La escena 3D necesitaba un componente aislado para no mezclarla
con la sala industrial ni duplicar estado.

## Cambios implementados

Nuevo `codigo/frontend/src/lib/agentOffice3d.ts`:

- construye un `AgentOfficeModel` desde `AgentRuntimeEvent[]`;
- mapea `AGENT_PROFILES` a posiciones 3D estables;
- calcula estado visual por agente:
  - reposo;
  - activo;
  - decision;
  - memoria;
  - error.
- calcula conteos por agente de eventos, decisiones, memoria, herramientas y
  errores;
- crea conexiones desde `supervisor` a agentes con eventos o seleccionados.

Nuevo `codigo/frontend/src/components/agents/AgentOffice3D.tsx`:

- crea una escena Three.js con oficina, mesas/nodos, suelo, paredes, luces y
  conexiones;
- usa `OrbitControls` con camara limitada;
- usa `Raycaster` para hover/click sobre nodos;
- al hacer click en un agente llama a `onSelectAgent(agentId)`;
- muestra overlay compacto con job, eventos, estado, memoria, leyenda y ficha
  del agente inspeccionado;
- reutiliza `WebGLFallback` si WebGL no esta disponible.

En `AgentObservabilityView.tsx`:

- se anade `AgentOfficeModeToggle`;
- el modo `2D` mantiene la oficina agentica existente;
- el modo `3D` carga `AgentOffice3D` con `React.lazy`;
- el panel de oficina ocupa todo el ancho solo cuando `3D` esta activo.

En `styles.css`:

- se anaden estilos acotados con prefijo `agent-office-3d`;
- se anade `agent-map-panel.wide-3d`;
- se ajusta responsive para desktop y movil.

## Criterios metodologicos

- La oficina 3D no inventa pensamiento ni actividad.
- Si no hay eventos runtime, los agentes aparecen en reposo.
- Los colores y conteos salen de `AgentRuntimeEvent`.
- El modo 2D sigue siendo el modo por defecto.
- La escena 3D se carga bajo demanda.
- La oficina 3D queda separada de la sala industrial de `Visualizacion`.

## Verificacion

Comandos ejecutados:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Validacion Playwright:

- se arranca Vite en `http://127.0.0.1:5173/`;
- se arranca backend local en `http://127.0.0.1:8010`;
- `GET /api/health` responde `ok`;
- se abre `Agentes`;
- se confirma que el modo inicial muestra la oficina 2D;
- se pulsa `Mostrar oficina 3D`;
- se confirma que existe canvas WebGL;
- se confirma que el panel pasa a modo ancho;
- se pulsa `Mostrar oficina 2D`;
- se confirma que el canvas se desmonta y vuelve la oficina 2D.

Screenshots generados:

```text
/tmp/tfm-frontend-agent-office3d/desktop-page.png
/tmp/tfm-frontend-agent-office3d/desktop-scene.png
/tmp/tfm-frontend-agent-office3d/mobile-page.png
/tmp/tfm-frontend-agent-office3d/mobile-scene.png
```

Analisis de pixeles sobre screenshots:

```text
desktop scene: 1194x391, 47 buckets de color, OK
mobile scene: 640x1002, 41 buckets de color, OK
```

Observacion:

- durante una primera validacion el backend no estaba levantado y el frontend
  mostro `HTTP 500 Internal Server Error`;
- se levanto backend local y se repitio la comprobacion con `/api/health` OK;
- la escena 3D no dependia de ese error, pero se dejo la app navegable para
  inspeccion manual.

## Limitaciones

- La validacion final se hizo con el contexto de `Agentes` sin eventos runtime
  cargados, por lo que la oficina aparece en reposo.
- El componente ya calcula estados desde eventos reales cuando existan, pero el
  siguiente subhito debe reforzar la lectura visual de actividad, memoria,
  herramientas, errores y debate sobre una run con eventos cargados.

## Siguiente paso

Hito 10.8B:

- cargar una run con eventos runtime reales;
- reforzar el mapeo visual de actividad por agente;
- hacer mas visibles memoria, herramientas, errores y debate;
- validar que los conteos de la oficina 3D coinciden con la banda de
  investigacion agentica;
- mantener el boton `2D`/`3D` como puerta de entrada opcional.
