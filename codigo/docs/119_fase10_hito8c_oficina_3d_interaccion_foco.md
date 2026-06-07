# Fase 10 - Hito 10.8C - Oficina 3D interaccion y foco

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Mejorar la oficina 3D de agentes para que no sea solo una escena informativa,
sino una vista navegable:

- hover mas visible sobre cada mesa/agente;
- click directo en la escena con seleccion sincronizada;
- botones compactos de foco por agente;
- movimiento de camara hacia el agente seleccionado;
- overlay responsive sin recortes en movil.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Permitir inspeccionar y enfocar agentes en la oficina 3D reutilizando el estado
de seleccion existente de la pestana Agentes.
```

Piezas reutilizadas:

- `AgentObservabilityView`;
- `AgentOffice3D`;
- `agentOffice3d.ts`;
- `selectedAgentId`;
- `onSelectAgent(agentId)`;
- `THREE.Raycaster`;
- `OrbitControls`;
- estilos `agent-office-3d` creados en los subhitos anteriores.

Decision:

```text
extend
```

Motivo: `10.8A` y `10.8B` ya tenian la escena, el modelo derivado de eventos y
la integracion con `Agentes`. El hito solo necesitaba enriquecer la interaccion
sin crear nuevas fuentes de datos ni componentes paralelos.

## Cambios implementados

En `AgentOffice3D.tsx`:

- se anade foco de camara por agente con `focusCameraOnNode(...)`;
- el click sobre una mesa selecciona el agente y mueve la camara;
- se anade `AgentOfficeFocusActions` con botones compactos para enfocar agentes;
- en snapshot sin eventos runtime vivos se muestran los 7 agentes como
  destinos de foco;
- con runtime vivo, los botones se limitan a agentes con eventos o al agente
  seleccionado;
- el hover aumenta mesa y baliza sin recrear el canvas;
- la seleccion usa una baliza mas marcada y mantiene sincronizado
  `selectedAgentId`;
- la ficha 3D usa `latestSummary` cuando existe y anade la fase del ultimo
  evento.

En `styles.css`:

- se anaden estilos `agent-office-3d-focus-*`;
- los botones de foco usan icono, color del agente y contador de eventos;
- en movil el overlay pasa a contribuir al alto del panel 3D para evitar
  recortes;
- en movil los botones de foco se muestran en una fila desplazable horizontal;
- se sube la altura minima movil del panel 3D para mantener escena y controles
  dentro del contenedor.

## Criterios metodologicos

- La oficina 3D sigue siendo opcional mediante el boton `2D`/`3D`.
- No se simulan eventos desde `decisions.json`.
- La seleccion 3D reutiliza `onSelectAgent`; no se crea un segundo estado de
  agente activo.
- Los snapshots historicos siguen mostrando ausencia de runtime vivo de forma
  explicita.
- La implementacion queda acotada al frontend modular.

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

Servicios locales:

- Vite activo en `http://127.0.0.1:5173/`;
- backend activo en `http://127.0.0.1:8010`;
- `GET /api/health` responde `ok`;
- `GET /health` responde `ok`.

Validacion Playwright desktop:

- viewport `1440x1100`;
- ruta: abrir app, ir a `Agentes`, activar `3D`, pulsar `Enfocar Modelador`;
- botones de foco detectados: `7`;
- detalle textual sincronizado: `Modelador`;
- errores de consola: `[]`;
- panel 3D: `1194x460`;
- overlay dentro del panel: `1168x447.6875`.

Validacion Playwright movil:

- viewport `390x920`;
- ruta: abrir app, ir a `Agentes`, activar `3D`, pulsar `Enfocar Evaluador`;
- botones de foco detectados: `7`;
- detalle textual sincronizado: `Evaluador`;
- errores de consola: `[]`;
- panel 3D: `320x818.375`;
- overlay dentro del panel: `318x816.375`.

Screenshots:

```text
/tmp/tfm-frontend-agent-office3d-c-desktop-page.png
/tmp/tfm-frontend-agent-office3d-c-desktop-scene.png
/tmp/tfm-frontend-agent-office3d-c-mobile-page.png
/tmp/tfm-frontend-agent-office3d-c-mobile-scene.png
```

Pixel check sobre capturas Playwright:

```text
desktop scene: 1194x461, 3614 colores, OK
mobile scene: 640x1640, 3390 colores, OK
```

Nota: el `readPixels` directo sobre el framebuffer WebGL de Chromium headless
devolvio una muestra vacia en esta sesion, por lo que el pixel check operativo
se hizo sobre la captura Playwright del panel 3D.

## Ajuste visual posterior

Fecha: 2026-06-06.

Motivo: en la primera composicion, la pared trasera estaba situada delante de
la camara inicial y podia tapar la oficina nada mas entrar. Ademas, la escena
necesitaba mas presencia visual como oficina real.

Cambios:

- se mueve la pared principal al fondo real de la escena;
- se dejan laterales parciales y frente abierto para no bloquear la vista;
- se acerca y centra la camara inicial;
- se compacta la distribucion de mesas para que los agentes aparezcan en el
  primer encuadre;
- se anaden agentes de pie junto a cada mesa;
- se anaden acentos de color por agente en mesa, monitor y badge;
- se incorpora decoracion de oficina: alfombra, pizarra, plantas, estanteria y
  paneles luminosos laterales;
- se mantiene la seleccion/foco ya validada en 10.8C.

Verificacion adicional:

```text
cd codigo/frontend
npm run build
OK
```

Playwright:

- captura inicial sin pulsar foco: `Oficina 3D / Supervisor`, sin errores de
  consola;
- desktop `1440x1100`: foco `Modelador`, 7 botones, detalle sincronizado;
- movil `390x920`: foco `Evaluador`, 7 botones, detalle sincronizado;
- capturas con mayor variedad cromatica:

```text
/tmp/tfm-frontend-agent-office3d-polish-initial-scene.png
/tmp/tfm-frontend-agent-office3d-polish-desktop-scene.png
/tmp/tfm-frontend-agent-office3d-polish-mobile-scene.png
```

Pixel check sobre capturas:

```text
desktop scene: 1194x461, 9101 colores, OK
mobile scene: 640x1640, 6274 colores, OK
```

Retoque final:

- se eliminan la silla y la antigua baliza esferica que podian leerse como
  monigotes sentados;
- se mantiene solo la figura de agente de pie;
- cada tipo de agente recibe un color fijo de camiseta para diferenciarse aun
  cuando todos estan en reposo;
- el supervisor se refuerza como jefe con camiseta propia, plataforma dorada,
  aro de liderazgo e insignia superior;
- las balizas de mesa pasan a ser indicadores planos pequenos, no figuras.

Verificacion final:

```text
npm run build
OK
initial scene: 1194x461, 10325 colores, OK
supervisor focus: 1194x461, 9314 colores, OK
```

Retoque de display compacto:

- al activar modo `3D` se ocultan la banda `Job/Eventos/Ultimo`, el panel largo
  de detalle del agente y las tarjetas extensas sobre el canvas;
- la informacion no se elimina del estado ni de la vista `2D`, solo se deja de
  renderizar en el modo 3D para priorizar el display;
- los focos de agente pasan a abreviaturas compactas:
  `SUP`, `LIM`, `EST`, `MOD`, `EVA`, `RED`, `VER`;
- al seleccionar o inspeccionar un agente aparece solo una etiqueta breve con
  nombre, rol, estado y eventos.

Verificacion del display compacto:

```text
npm run build
OK
3D desktop: sin agent-live-band, sin agent-detail-panel, sin tarjetas largas
3D desktop: mini tag Modelador -> "Modelos · reposo · 0 ev"
3D movil: mini tag Evaluador -> "Metricas · reposo · 0 ev"
```

## Limitacion

La verificacion de este hito se hizo sobre un snapshot sin eventos runtime vivos.
Esto valida navegacion, foco, seleccion y responsive, pero no vuelve a probar
transiciones reales entre agentes. Ese escenario requiere lanzar una run viva
para poblar `job.events`.

## Siguiente paso

Hito 10.8D:

- lanzar una run pequena si se quiere validar runtime vivo;
- comprobar que los botones de foco se reducen a agentes activos/con eventos;
- revisar transiciones y senales durante el job;
- cerrar Hito 10.8 como oficina 3D opcional de agentes.
