# Fase 10 - Hito 10.9C - Reduccion textual por pestanas

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Aplicar la politica de baja lectura fuera del cockpit: `Nueva run`,
`Visualizacion`, `Agentes` y runs deben mostrar primero estado, accion y
metricas, dejando descriptor tecnico, rationale, informes, debate, auditoria,
payloads y artefactos bajo demanda.

## Alcance

Incluido:

- `Nueva run` y `Preflight`;
- `Visualizacion`;
- `Agentes` y memoria agentica;
- detalle de runs, informes, auditoria, debate y evidencia;
- estilos compartidos para detalles compactos;
- ajuste de overflow en `Agentes`;
- ajuste posterior del bloque superior, registro de runs y estructura de
  `Visualizacion`.

No incluido:

- cambios backend;
- cambios en contratos API;
- eliminacion de informes, memoria o evidencia;
- rediseño final de QA visual completo.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Reducir texto visible en vistas funcionales reutilizando componentes y datos
existentes, sin perder trazabilidad.
```

Piezas revisadas y reutilizadas:

- `PipelineConfig`;
- `PlanView`;
- `VisualizationView`;
- `AgentObservabilityView`;
- `AgentMemoryPanel`;
- `RunDetailView`;
- `ReportPanels`;
- `styles.css`.

Decision:

```text
adapt
```

Motivo: todas las vistas ya tenian la informacion necesaria. El hito cambia la
presentacion y la jerarquia visual, no crea propietarios nuevos ni duplica
funcionalidad.

## Cambios implementados

En `Nueva run` y `Preflight`:

- motivos de Human Review plegados por defecto;
- descriptor tecnico plegado por defecto;
- resumen del descriptor en señales compactas;
- politica, bloqueos y revision humana del plan bajo `details`.

En `Visualizacion`:

- notas de proyeccion y warnings bajo demanda;
- contexto tecnico del motor plegado;
- motivo del estado temporal plegado;
- recomendacion agentica mantiene resumen/meta visibles y mueve evidencia,
  herramientas, guardarrailes, cautelas y debate a detalle.
- se añade una navegacion interna por secciones:
  `Estado`, `Agente`, `Comparar`, `Serie` y `Mapa`;
- solo se muestra una seccion grafica principal cada vez;
- el panel de metricas queda acotado en desktop para no empujar toda la vista;
- se corrige overflow movil en el rail de ventanas.

En `Agentes`:

- rationale del evento plegado;
- payload tecnico sigue bajo detalle;
- resumen de evento y conversacion se recortan visualmente;
- resumen de uso de memoria y consulta RAG bajo detalle;
- se ajustan columnas de `agent-workspace` para evitar overflow con sidebar.
- el cockpit de memoria queda plegado provisionalmente para no invadir la
  pestaña principal hasta rediseñarlo como subpestaña propia.

En runs:

- informes, auditoria y debate quedan plegados por defecto;
- evidencia tecnica queda plegada por defecto;
- se corrige key duplicada en la lista de artefactos.
- el registro completo de runs queda plegado por defecto como drawer de
  auditoria.

En shell/contexto:

- se oculta el resumen global de salud fuera de `Cockpit`;
- el contexto de ejecucion queda como linea compacta plegable.

En `styles.css`:

- se añade `compact-disclosure` como patron visual compartido;
- se añaden `plan-signal-grid` y `plan-signal`;
- se añaden recortes de texto de dos lineas en zonas conversacionales;
- se mantiene responsive movil sin scroll horizontal.

## Verificacion

Build:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Playwright desktop:

- `Nueva run`: `1440/1440/1440`, sin scroll horizontal;
- `Visual`: `1440/1440/1440`, sin scroll horizontal;
- `Agentes`: `1440/1440/1440`, sin scroll horizontal;
- errores de consola: `[]`.

Playwright movil:

- `Nueva run`: `390/390/390`, sin scroll horizontal;
- `Agentes`: `390/390/390`, sin scroll horizontal;
- `Visual`: `390/390/390`, sin scroll horizontal;
- errores de consola: `[]`.

Capturas:

```text
/tmp/tfm-frontend-109c-pipeline-desktop-v2.png
/tmp/tfm-frontend-109c-visual-desktop-v2.png
/tmp/tfm-frontend-109c-agents-desktop-v2.png
/tmp/tfm-frontend-109c-pipeline-mobile-v2.png
/tmp/tfm-frontend-109c-agents-mobile-v2.png
/tmp/tfm-frontend-109c-polish2-pipeline-desktop.png
/tmp/tfm-frontend-109c-polish2-agents-desktop.png
/tmp/tfm-frontend-109c-polish2-visual-desktop.png
/tmp/tfm-frontend-109c-polish2-visual-serie-desktop.png
/tmp/tfm-frontend-109c-polish2-pipeline-mobile.png
/tmp/tfm-frontend-109c-polish4-visual-mobile.png
```

## Limitacion

El hito reduce lectura visible y mejora el cockpit funcional, pero aun queda
unificar estilos repetidos, revisar contraste, pequenos solapes y coherencia
global antes de cerrar el bloque visual.

Quedaba pendiente como mejora de producto:

- seguir puliendo `Visualizacion` con una composicion mas guiada si se quiere
  convertirla en una vista de inspeccion industrial completa.

Nota posterior: la memoria agentica visual queda implementada y verificada en
`codigo/docs/124_fase10_hito9d_memoria_agentica_visual.md`.

Nota posterior adicional: la primera iteracion de visualizacion industrial
guiada queda implementada y validada con run real en
`codigo/docs/125_fase10_hito9e_metricas_visualizacion_subpantalla.md`.

## Siguiente paso

Hito 10.9F:

- QA visual global del bloque `10.9A-E`;
- revisar contraste, responsive y solapes;
- comprobar que no hay texto largo invadiendo vistas funcionales;
- validar desktop/movil;
- documentar cierre de `10.9F`.
