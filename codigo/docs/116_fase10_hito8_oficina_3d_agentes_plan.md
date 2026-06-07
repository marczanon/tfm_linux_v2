# Fase 10 - Hito 10.8 - Plan oficina 3D de agentes

Fecha: 2026-06-06.

Estado: plan operativo. Los subhitos `10.8A`, `10.8B` y `10.8C` ya estan
implementados en `codigo/docs/117_fase10_hito8a_oficina_3d_agentes_base.md`,
`codigo/docs/118_fase10_hito8b_oficina_3d_runtime_senales.md` y
`codigo/docs/119_fase10_hito8c_oficina_3d_interaccion_foco.md`; queda
pendiente `10.8D`.

## Punto de partida

La Fase 10 queda en este punto:

- Hito 10.5 dejo `Agentes` como runtime investigativo con eventos reales,
  detalle de decision, memoria y conversacion derivada.
- Hito 10.6 cerro la visualizacion 2D avanzada.
- Hito 10.7 cerro la sala 3D industrial en `Visualizacion`, con Three.js,
  fallback WebGL, lazy loading, interaccion, Playwright y screenshots.

El siguiente paso natural es Hito 10.8: una oficina 3D de agentes dentro de
`Agentes`. No debe tocar backend ni contratos en el primer bloque.

## Objetivo

Crear una vista opcional 3D para explicar el runtime agentico como una oficina
de trabajo:

- cada agente aparece como mesa/nodo;
- la actividad se deriva de eventos persistidos;
- memoria, herramientas, errores y debate se muestran como senales visuales;
- click en un agente sincroniza con el detalle textual ya existente;
- la vista aporta comunicacion y trazabilidad visual, no diagnostico nuevo.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Representar la pestana Agentes como oficina 3D opcional usando eventos runtime
ya persistidos, sin crear contratos ni simular razonamiento.
```

Piezas canonicas a reutilizar:

- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`;
- `codigo/frontend/src/lib/agentRuntime.ts`;
- `AGENT_PROFILES`;
- `AgentRuntimeEvent`;
- `AgentMemoryPanel`;
- `IndustrialScene3D.tsx` solo como referencia de patron Three.js, no como
  componente a mezclar;
- `WebGLFallback.tsx` o un fallback comun equivalente si conviene extraerlo;
- estilos de Hito 10.7 como referencia de canvas, overlay y responsive;
- Playwright instalado en `codigo/frontend` para validacion visual.

Decision prevista:

```text
extend + new isolated component
```

Motivo: `Agentes` ya tiene propietario modular y estado suficiente. La escena
3D debe ser un componente nuevo y aislado porque su responsabilidad visual es
distinta de la sala industrial de `Visualizacion`.

## Frontera de responsabilidad

La oficina 3D pertenece a:

```text
codigo/frontend/src/components/agents/
codigo/frontend/src/lib/agentOffice3d.ts
```

No pertenece a:

```text
codigo/app/
codigo/scripts/
codigo/tests/
memoria/
recursos/
```

No debe modificar:

- API FastAPI;
- esquemas Pydantic;
- grafo LangGraph;
- agentes reales;
- ejecutores deterministas;
- persistencia de runs;
- memoria academica.

## Datos permitidos

Usar solo datos ya disponibles en frontend:

- `events: AgentRuntimeEvent[]`;
- `selectedAgentId`;
- `onSelectAgent`;
- `job`;
- `AGENT_PROFILES`;
- `eventsForAgent(...)`;
- `eventOwnerId(...)`;
- `agentLabel(...)`;
- `kindLabel(...)`;
- `sourceLabel(...)`.

Campos utiles de eventos:

- `sequence`;
- `kind`;
- `source`;
- `stage`;
- `created_at`;
- `title`;
- `summary`;
- `decision_id`;
- `memory_record_ids`;
- `retrieved_memory_record_ids`;
- `cited_memory_record_ids`;
- `ignored_memory_record_ids`;
- `payload`.

Si un campo no existe en una run concreta, la oficina debe mostrar ausencia, no
rellenar con simulaciones.

## Tecnologia

Usar:

- React + TypeScript;
- Three.js ya instalado;
- `React.lazy` y `Suspense` para cargar la oficina bajo demanda;
- `OrbitControls` con limites de camara;
- `THREE.Raycaster` para hover/click en agentes;
- CSS local con prefijo `agent-office-3d`;
- Playwright para screenshot desktop/movil.

No anadir nuevas dependencias en 10.8A salvo bloqueo real.

## Diseno funcional

Ubicacion recomendada:

- dentro de `AgentObservabilityView`;
- cerca del panel `agent-map-panel`, porque ese panel ya representa la oficina
  agentica actual en 2D;
- mantener timeline, detalle, memoria y conversacion debajo o al lado;
- no cambiar la pestaña por defecto de la aplicacion.

Forma visual inicial:

- supervisor en el centro o cabecera de la oficina;
- agentes especialistas alrededor;
- cada mesa/nodo con color por estado:
  - sin eventos;
  - activo;
  - decision;
  - memoria;
  - error;
- lineas ligeras para eventos recientes;
- pequenos indicadores para memoria/herramientas/debate;
- overlay compacto con job, eventos, ultimo agente y seleccionado.

## Subhitos

### 10.8A - Base estatica

Objetivo:

- crear `AgentOffice3D.tsx`;
- crear `agentOffice3d.ts`;
- mapear `AGENT_PROFILES` a posiciones 3D estables;
- renderizar oficina basica sin animacion compleja;
- lazy load dentro de `AgentObservabilityView`;
- fallback WebGL;
- build y screenshot.

Criterio de cierre:

- `npm run build` pasa;
- la oficina aparece en `Agentes`;
- no afecta a timeline/detalle/memoria;
- si no hay eventos, la oficina se ve en reposo;
- Playwright confirma canvas no vacio.

Estado 2026-06-06:

```text
implementado
```

Resultado:

- `AgentOffice3D.tsx` creado;
- `agentOffice3d.ts` creado;
- boton `2D`/`3D` integrado en `Agentes`;
- lazy loading y fallback WebGL activos;
- validacion Playwright desktop/movil completada.

### 10.8B - Runtime real

Objetivo:

- calcular estado visual por agente desde `AgentRuntimeEvent`;
- mostrar actividad, memoria, herramientas, errores y debate;
- dibujar conexiones reales entre supervisor/agentes cuando los eventos lo
  permitan;
- usar ultimos eventos para intensidad visual.

Criterio de cierre:

- no se inventan eventos;
- los contadores coinciden con la banda de investigacion;
- los errores reales son visibles;
- el modo sin eventos sigue honesto.

Estado 2026-06-06:

```text
implementado
```

Resultado:

- se enriquecio `agentOffice3d.ts` con conteos reales por agente;
- se añadieron transiciones recientes cuando existen eventos runtime;
- se añadieron indicadores 3D de memoria, herramientas, debate y errores;
- se muestra aviso honesto de snapshot persistido cuando no hay job vivo;
- no se simulan eventos desde `decisions.json`.

### 10.8C - Interaccion

Objetivo:

- hover sobre agente con ficha compacta;
- click sobre agente llama a `onSelectAgent(agentId)`;
- ficha 3D muestra ultimo evento y conteos;
- seleccion visual sincronizada con el detalle existente.

Criterio de cierre:

- seleccionar en 3D actualiza `AgentRuntimeDetail`;
- seleccionar desde la UI existente actualiza la oficina;
- no hay doble estado divergente.

Estado 2026-06-06:

```text
implementado
```

Resultado:

- click en una mesa selecciona el agente y enfoca la camara;
- se anadieron botones compactos de foco por agente;
- en snapshot sin runtime vivo se pueden enfocar los 7 agentes;
- con runtime vivo se reservara la lista compacta para agentes activos o con
  eventos;
- hover y seleccion quedan mas visibles en la escena;
- el overlay movil queda contenido dentro del panel 3D;
- se corrige la composicion inicial para que ninguna pared tape los agentes al
  entrar;
- se anaden agentes de pie, mas color y decoracion de oficina;
- validacion Playwright desktop/movil completada.

### 10.8D - Pulido y cierre

Objetivo:

- lanzar una run pequena si se quiere validar runtime vivo;
- comprobar transiciones y senales con `job.events`;
- revisar que los botones se reducen a agentes activos o con eventos durante
  ejecucion real;
- documentar cierre completo del Hito 10.8.

Criterio de cierre:

- escena visible en desktop y movil;
- sin solapes graves de overlay;
- canvas no vacio;
- build correcto;
- si se lanza run viva, actividad y transiciones reales visibles;
- la oficina puede ignorarse sin perder funcionalidad cientifica.

## Verificacion prevista

Comandos minimos:

```text
cd codigo/frontend
npm run build
```

Verificacion visual:

```text
abrir http://127.0.0.1:5173/
ir a Agentes
activar Oficina 3D
comprobar canvas, fallback, seleccion y responsive
```

Verificacion automatizada recomendada:

- Playwright desktop `1440x1000`;
- Playwright movil `390x844`;
- screenshot de pagina y escena;
- pixel check sobre screenshot compositado;
- confirmar que click en agente cambia el detalle.

## Riesgos

- que parezca que los agentes piensan en vivo cuando solo se muestran eventos:
  mitigar con señales derivadas de runtime real.
- que Three.js pese demasiado:
  mitigar con `React.lazy`.
- que la oficina duplique la oficina 2D actual:
  mitigar manteniendo la 3D como modo opcional o progresiva.
- que el usuario no encuentre la interaccion:
  mitigar con controles iconicos y seleccion clara, no con texto largo.

## Primer paso exacto para manana

1. Revisar `AgentObservabilityView.tsx` y `agentRuntime.ts`.
2. Definir `AgentOfficeModel` en `agentOffice3d.ts`.
3. Crear `AgentOffice3D.tsx` con escena estatica y fallback.
4. Integrarla en `agent-map-panel` con carga diferida.
5. Ejecutar `npm run build`.
6. Validar con Playwright que el canvas aparece en `Agentes`.

No empezar por animaciones, modelos complejos, backend ni contratos nuevos.
