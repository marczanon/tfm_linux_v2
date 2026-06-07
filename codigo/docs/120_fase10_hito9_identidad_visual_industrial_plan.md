# Fase 10 - Hito 10.9 - Identidad visual industrial y reduccion de texto

Fecha: 2026-06-06.

Estado: cerrado. Los subhitos `10.9A`, `10.9B`, `10.9C`, `10.9D`, `10.9E` y
`10.9F` quedan implementados y documentados entre
`codigo/docs/121_fase10_hito9a_tokens_shell_industrial.md` y
`codigo/docs/126_fase10_hito9f_qa_visual_global.md`.

## Objetivo

Dar a la aplicacion una identidad visual propia, moderna e industrial, evitando
que parezca una libreta blanca generica. La interfaz debe sentirse como un
cockpit de deteccion industrial y sistema multiagente, no como una pagina de
formularios.

El cambio debe mantener toda la trazabilidad, documentacion, informes, memoria,
payloads y evidencia, pero reducir drasticamente el texto visible en las zonas
funcionales de la aplicacion.

Regla central:

```text
Ver primero estado y accion.
Leer solo al inspeccionar.
Auditar solo al abrir detalle.
```

## Alcance

Incluido:

- identidad visual de producto;
- paleta industrial propia;
- tokens CSS y lenguaje comun de componentes;
- rediseño progresivo de shell, cockpit y pestañas;
- reduccion de texto visible en vistas funcionales;
- uso de estados, chips, LEDs, railes, metricas compactas y tooltips;
- detalles largos plegados, en drawers, acordeones o secciones de evidencia.

Fuera de alcance:

- cambiar backend;
- cambiar contratos API;
- eliminar informacion o evidencia;
- reescribir todo el frontend;
- crear landing page;
- simular diagnosticos o razonamiento no persistido;
- sustituir informes, memoria o trazas por visuales sin evidencia.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Convertir el frontend existente en una aplicacion con identidad visual
industrial, menor carga textual y cockpit mas funcional sin romper flujos.
```

Piezas canonicas a reutilizar:

- `codigo/frontend/src/components/shell/AppShell.tsx`;
- `codigo/frontend/src/components/shell/ViewTabs.tsx`;
- `codigo/frontend/src/components/cockpit/CockpitView.tsx`;
- `codigo/frontend/src/components/pipeline/PipelineConfig.tsx`;
- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`;
- `codigo/frontend/src/components/visualization/VisualizationView.tsx`;
- `codigo/frontend/src/styles.css`;
- `codigo/frontend/src/types/ui.ts`;
- componentes comunes existentes: `StatusPill`, `StatusItem`, botones,
  paneles, tarjetas y toggles.

Decision:

```text
extend + adapt
```

Motivo: la app ya tiene las capacidades, rutas y estado necesarios. El problema
actual es de lenguaje visual, jerarquia, densidad de texto y composicion. No se
deben crear vistas paralelas ni duplicar flujos.

## Direccion visual

Nombre de trabajo:

```text
Industrial Agentic Cockpit
```

Concepto:

- sala de control industrial;
- telemetria de vibracion;
- deteccion de anomalias;
- supervision multiagente;
- evidencia cientifica bajo demanda.

Tono visual:

- moderno, tecnico y sobrio;
- base clara industrial, no blanco puro;
- zonas de control con contraste;
- color usado para estado y significado, no como decoracion aleatoria;
- tarjetas mas densas y funcionales;
- menos parrafos;
- mas indicadores compactos.

Evitar:

- apariencia de libreta/documento;
- fondos blancos sin estructura;
- tarjetas grandes con texto explicativo;
- paletas de un solo color;
- gradientes decorativos sin funcion;
- hero marketing;
- exceso de morado/azul oscuro como tema dominante.

## Paleta propuesta

Base:

- fondo app: gris tecnico claro;
- superficies: blanco roto o gris muy claro;
- bordes: azul grisaceo suave;
- texto principal: grafito industrial;
- texto secundario: gris acero.

Estados:

- `ok`: verde petroleo;
- `data`: azul electrico;
- `warning`: ambar industrial;
- `danger`: rojo tecnico;
- `model`: violeta controlado;
- `neutral`: gris pizarra.

Aplicacion:

- verde petroleo como acento principal de sistema;
- azul para datos, memoria y señal;
- ambar para revision, incertidumbre y avisos;
- rojo solo para errores, anomalias o critico;
- violeta solo para modelado/agente modelador, no como fondo dominante.

## Lenguaje visual comun

Elementos reutilizables:

- LEDs de estado;
- chips compactos;
- railes de salud;
- medidores pequenos;
- tarjetas metricas densas;
- bandas de estado;
- iconos lucide en botones;
- tooltips para informacion secundaria;
- paneles plegables de evidencia;
- drawers o detalles bajo demanda para texto largo;
- graficas como protagonistas cuando haya datos.

Principio:

```text
Un usuario debe entender el estado de la run en 5 segundos sin leer un parrafo.
```

## Politica de texto

Texto visible permitido:

- titulos cortos;
- etiquetas de estado;
- valores metricos;
- acciones;
- microcopy de una linea si evita confusion;
- tooltips.

Texto visible a ocultar por defecto:

- explicaciones largas;
- rutas tecnicas;
- payloads JSON;
- rationale completo;
- debate completo;
- memoria detallada;
- informes extensos;
- instrucciones de uso;
- documentacion narrativa.

Ubicacion de texto profundo:

- paneles plegables;
- modal/drawer de evidencia;
- vista de informe;
- detalle de agente;
- seccion de auditoria;
- payload tecnico colapsado.

La informacion no se elimina. Se conserva y se muestra bajo demanda.

## Estrategia por vistas

### Cockpit

Debe pasar a ser la consola operativa principal.

Prioridad visual:

- estado global del sistema;
- run foco;
- salud/riesgo del activo;
- job activo;
- recomendacion agentica condensada;
- acciones principales;
- evidencia lista;
- historial corto.

Reducir:

- parrafos;
- explicaciones de contexto;
- bloques de texto estaticos.

### Nueva run

Debe sentirse como un launcher guiado.

Prioridad visual:

- pasos claros;
- dataset;
- modo de ejecucion;
- agentes/LLM;
- preflight;
- accion de lanzamiento;
- estado de job.

Reducir:

- formularios largos visibles;
- configuracion tecnica no usada;
- opciones avanzadas abiertas por defecto.

### Visualizacion

Debe funcionar como sala de analisis.

Prioridad visual:

- series, HI, riesgo, bandas y 3D;
- comparacion de runs;
- metricas compactas;
- leyendas minimas;
- seleccion interactiva.

Reducir:

- notas largas bajo las graficas;
- explicaciones de como leer la vista;
- rutas o detalles tecnicos visibles.

### Agentes

Debe conservar profundidad, pero la vista funcional debe ser menos textual.

Prioridad visual:

- modo 3D limpio ya iniciado;
- mapa/timeline compactos;
- señal de memoria, tools, decision, error;
- detalle completo solo al inspeccionar.

Reducir:

- tarjetas con mucho texto abiertas por defecto;
- payloads visibles;
- conversacion completa si no se solicita.

### Runs, informes y evidencia

Debe actuar como archivo tecnico, no como primera experiencia.

Prioridad visual:

- lista densa de runs;
- estado;
- metrica principal;
- acceso a informe;
- acceso a artefactos;
- evidencia plegada.

Reducir:

- informes renderizados siempre visibles;
- bloques de artefactos abiertos por defecto;
- rutas largas sin accion asociada.

## Subhitos propuestos

### 10.9A - Tokens visuales y shell industrial

Objetivo:

- definir variables CSS de identidad;
- actualizar fondo general, sidebar, topbar, tabs, paneles y botones;
- introducir lenguaje de LEDs/chips industriales;
- mantener layouts y datos actuales.

Criterio de cierre:

- `npm run build` OK;
- la app deja de parecer una libreta blanca;
- no se rompe ninguna vista;
- el cockpit se percibe como aplicacion industrial.

Estado 2026-06-06:

```text
implementado
```

Resultado:

- tokens CSS industriales creados;
- sidebar oscuro con marca `Agentic Control`;
- navegacion compacta;
- header operacional `Control de anomalias`;
- paneles, botones y status cards con acento industrial;
- build y Playwright desktop/movil OK;
- scroll horizontal movil corregido.

### 10.9B - Cockpit funcional de baja lectura

Objetivo:

- rediseñar `CockpitView`;
- reducir texto visible;
- reforzar metricas, estados y acciones;
- mover evidencia a bloques compactos o plegables.

Criterio de cierre:

- el usuario entiende estado, run foco y accion principal sin leer parrafos;
- no se pierde acceso a informe, auditoria, debate ni artefactos.

Estado 2026-06-06:

```text
implementado
```

Resultado:

- `CockpitView` se reorganiza como command deck;
- estado dominante, HI y riesgo pasan al primer plano;
- readiness chips compactan API, LLM, datos, run y evidencia;
- recomendacion agentica pasa a accion breve;
- señales y metricas ganan color semantico;
- build y Playwright desktop/movil OK;
- sin scroll horizontal movil.

### 10.9C - Reduccion textual por pestañas

Objetivo:

- aplicar politica de texto a `Nueva run`, `Visualizacion`, `Agentes` y runs;
- ocultar detalles largos por defecto;
- mantener datos bajo demanda.

Criterio de cierre:

- las vistas funcionales son mas visuales;
- la documentacion tecnica sigue accesible;
- no se elimina trazabilidad.

Estado 2026-06-06:

```text
implementado
```

Resultado:

- `Nueva run` y `Preflight` muestran señales compactas y pliegan descriptor,
  politica, bloqueos y motivos;
- `Visualizacion` pliega notas tecnicas, contexto del motor, motivo temporal y
  evidencia/debate de recomendacion;
- `Agentes` pliega rationale, payloads y consultas/uso de memoria;
- runs pliega informe, auditoria, debate y artefactos;
- se corrige una key duplicada en artefactos;
- se ajusta `agent-workspace` para eliminar overflow con sidebar;
- se oculta el resumen global fuera de `Cockpit`;
- el contexto de ejecucion queda como linea plegable;
- el registro de runs queda plegado por defecto;
- la memoria agentica queda plegada provisionalmente hasta rediseñarla como
  subpestaña propia;
- `Visualizacion` pasa a secciones internas (`Estado`, `Agente`, `Comparar`,
  `Serie`, `Mapa`) para evitar una cascada de graficas;
- build y Playwright desktop/movil OK;
- sin scroll horizontal desktop/movil.

Pendientes de producto detectados:

- seguir madurando `Visualizacion` hacia una vista de inspeccion industrial mas
  guiada y menos secuencial.

### 10.9D - Memoria agentica visual

Objetivo:

- crear subpestaña `Memoria` dentro de `Agentes`;
- entrar mediante boton/icono de cerebro;
- mostrar agentes como selector de personajes;
- visualizar avatar, rol, herramientas y recuerdos concisos;
- mantener memoria tecnica bajo demanda.

Criterio de cierre:

- seleccion de agente clara y visual;
- recuerdos en frases humanas cortas;
- herramientas/capacidades visibles como chips;
- detalle tecnico accesible sin ocupar la primera lectura;
- build y Playwright desktop/movil OK.

Estado 2026-06-06:

```text
implementado y verificado
```

Documento:

```text
codigo/docs/124_fase10_hito9d_memoria_agentica_visual.md
```

Resultado:

- selector interno `Runtime | Memoria` en `Agentes`;
- boton `Memoria` con icono de cerebro;
- componente modular `AgentMemoryShowcase`;
- selector visual de 7 agentes;
- avatar/personaje de pie para el agente seleccionado;
- supervisor diferenciado como jefe;
- color propio por tipo de agente;
- tools/capacidades como chips;
- recuerdos concisos derivados de `MemoryRecordSummary.summary`;
- detalle tecnico de `AgentMemoryPanel` plegado;
- build y Playwright desktop/movil OK.

### 10.9E - Visualizacion industrial guiada

Objetivo:

- seguir madurando `Visualizacion`;
- evitar lectura secuencial de demasiadas graficas;
- guiar la inspeccion por estado, metricas, agente, comparacion, serie y mapa;
- mantener 3D opcional sin saturacion.

Criterio de cierre:

- el usuario entiende rapidamente que grafica mira y para que sirve;
- solo se muestran graficas relevantes por seccion;
- responsive desktop/movil sin scroll horizontal.

Estado 2026-06-06:

```text
implementado y cerrado
```

Resultado:

- `Metricas` pasa a subpantalla interna de `Visualizacion`;
- el panel fijo de metricas se elimina de la primera lectura;
- `VisualizationMetricsPanel` se reutiliza sin cambios backend;
- build correcto;
- Playwright desktop/movil OK a nivel de layout;
- validacion manual posterior con backend activo y run real;
- sin pendientes funcionales en `10.9E`.

### 10.9F - Sistema visual coherente y QA

Objetivo:

- unificar estilos repetidos;
- corregir solapes;
- validar desktop/movil;
- preparar cierre visual de Fase 10.

Criterio de cierre:

- build correcto;
- capturas desktop/movil;
- contraste y jerarquia coherentes;
- sin textos largos invadiendo el flujo principal.

Estado 2026-06-06:

```text
implementado y cerrado
```

Documento:

```text
codigo/docs/126_fase10_hito9f_qa_visual_global.md
```

Resultado:

- QA visual global tras `10.9A-E`;
- backend local y `/runs` correctos;
- Playwright desktop/movil sobre vistas principales;
- sin errores de consola;
- sin respuestas fallidas;
- sin overflow horizontal;
- `npm run build` correcto;
- Hito `10.9` cerrado.

## Primer paso de implementacion

El bloque `10.9` queda cerrado. Nota posterior: `10.10 - Informe, evidencia y
artefactos` tambien queda implementado en
`codigo/docs/127_fase10_hito10_informe_evidencia_artefactos.md`.

Continuar con `10.11 - Pulido, QA visual y Docker`.

Orden recomendado:

1. Ejecutar smoke local de frontend/API.
2. Revisar responsive y solapes tras el cierre visual.
3. Verificar escenas 3D si se incluyen en la demo.
4. Rebuild Docker si se decide cerrar con evidencia reproducible.
5. Documentar cierre de Fase 10.

## Verificacion

Minimo:

```text
cd codigo/frontend
npm run build
```

Si se cambia layout relevante:

- captura desktop;
- captura movil;
- revisar que no haya solapes;
- revisar que botones y textos caben;
- revisar que modo 3D sigue limpio.

## Nota metodologica

Este hito cambia presentacion y experiencia, no capacidades cientificas. La
evidencia, memoria, informes, decisiones, runs y payloads siguen siendo la base
de auditabilidad del TFM. La mejora consiste en hacer que la aplicacion sea mas
usable, reconocible y demostrable sin sacrificar trazabilidad.
