# Fase 10 - Hito 10.8B - Oficina 3D runtime y senales

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Reforzar la oficina 3D de agentes para que represente mejor senales reales de
runtime cuando existan eventos en memoria, y para que sea honesta cuando se
esta inspeccionando una run persistida sin job vivo.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mapear actividad, memoria, herramientas, errores y debate en la oficina 3D de
agentes usando eventos runtime existentes y snapshot seleccionado.
```

Piezas reutilizadas:

- `AgentObservabilityView`;
- `AgentOffice3D`;
- `agentOffice3d.ts`;
- `AgentRuntimeEvent`;
- `selectedSnapshot` ya cargado por `loadRunDetail(...)`;
- `AGENT_PROFILES`, `eventsForAgent(...)` y `eventOwnerId(...)`.

Decision:

```text
extend
```

Motivo: `10.8A` ya tenia escena, toggle y modelo base. El hito necesitaba
enriquecer las senales derivadas, no crear otra vista ni abrir endpoints.

## Cambios implementados

En `agentOffice3d.ts`:

- se anaden conteos por agente de:
  - decisiones;
  - memoria;
  - herramientas;
  - debate/verificacion;
  - errores.
- se anaden badges reales por agente;
- se anaden `latestKind`, `latestStage` y `latestSummary`;
- se calculan transiciones recientes entre agentes a partir de la secuencia de
  `AgentRuntimeEvent`;
- si no hay transiciones, se mantienen conexiones desde `supervisor` a agentes
  con eventos o seleccionados.

En `AgentOffice3D.tsx`:

- se visualizan conexiones recientes entre agentes cuando existen eventos;
- cada mesa puede mostrar indicadores pequenos para memoria, herramientas,
  debate y error;
- el overlay distingue `Runtime vivo` frente a oficina sin eventos;
- la ficha del agente muestra badges derivados y conteo de debate;
- si no hay eventos runtime vivos, se muestra una nota basada en el snapshot
  seleccionado.

En `AgentObservabilityView.tsx` y `App.tsx`:

- se pasa `selectedSnapshot` a la vista de agentes;
- `AgentOffice3D` recibe `runId`, `n_decisions` y `n_errors` para explicar el
  estado historico sin convertirlo en eventos simulados.

En `styles.css`:

- se anaden badges de senales;
- se anade aviso `agent-office-3d-runtime-note`;
- se aumenta la altura minima desktop de la oficina 3D para evitar recortes.

## Criterios metodologicos

- No se inventan eventos para snapshots historicos.
- Los eventos vivos siguen saliendo de `job.events`.
- Las decisiones persistidas solo se muestran como conteo de snapshot cuando no
  hay runtime en memoria.
- No se crea endpoint nuevo para `decisions.json`.
- La oficina 3D sigue siendo opcional mediante `2D`/`3D`.

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

Validacion local:

- Vite activo en `http://127.0.0.1:5173/`;
- backend activo en `http://127.0.0.1:8010`;
- `GET /api/health` responde `ok`;
- se abre `Agentes`;
- se activa `3D`;
- se comprueba canvas WebGL;
- se comprueba nota de snapshot:

```text
Snapshot persistido: 20 decisiones y 0 errores
```

- se valida que no aparece `HTTP 500 Internal Server Error`;
- se valida que el aviso de snapshot queda dentro del canvas.

Screenshots:

```text
/tmp/tfm-frontend-agent-office3d-b/desktop-page.png
/tmp/tfm-frontend-agent-office3d-b/desktop-scene.png
/tmp/tfm-frontend-agent-office3d-b/desktop-scene-fixed.png
```

Pixel check:

```text
desktop scene: 1194x391, 47 buckets de color, OK
```

## Limitacion

El backend actual solo expone eventos runtime vivos mediante jobs en memoria.
Las runs persistidas conservan `decisions.json`, pero no existe un endpoint
frontend ya disponible para convertirlo en eventos historicos. Por eso este
hito no simula eventos desde `decisions.json`; muestra el snapshot como resumen
persistido y reserva la actividad por agente para jobs con `events`.

## Siguiente paso

Actualizacion 2026-06-06: Hito 10.8C queda implementado en
`codigo/docs/119_fase10_hito8c_oficina_3d_interaccion_foco.md`.

Hito 10.8D:

- validar con una ejecucion que produzca eventos runtime vivos si se decide
  lanzar una run de prueba;
- comprobar transiciones reales y senales durante `job.events`;
- cerrar el Hito 10.8.
