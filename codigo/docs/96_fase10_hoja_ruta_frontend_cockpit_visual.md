# Fase 10 - Hoja de ruta frontend cockpit visual

Fecha: 2026-06-05.

Estado: planificada tras el cierre operativo de Fase 9.

Documento de partida: `codigo/docs/95_cierre_fase9_run_to_failure_maximo_nivel.md`.

## Objetivo

Elevar el frontend de la aplicacion a un cockpit visual industrial claro,
profesional y facil de operar, sin romper la app existente y sin desplazar el
protagonismo de los agentes Qwen/LLM.

La Fase 10 no debe crear una landing page ni una interfaz de marketing. La
primera pantalla debe seguir siendo la aplicacion real: un panel principal de
control para lanzar, monitorizar, comparar y entender runs agenticas. La
informacion profunda debe quedar disponible en pestanas especializadas, pero el
panel principal no debe estar saturado de texto.

## Principios no negociables

- No reescribir la aplicacion desde cero.
- No eliminar flujos existentes hasta que su reemplazo este verificado.
- No cambiar contratos backend salvo que falte un dato imprescindible.
- No crear otro frontend paralelo.
- No hacer que la UI invente diagnosticos que no vengan de contratos,
  artefactos o decisiones agenticas persistidas.
- No convertir las visualizaciones deterministas en sustitutas de los agentes.
- Mantener `POST /runs`, jobs, runs persistidas, memoria, informes y
  visualizacion sobre las APIs actuales.
- Mantener el dashboard como herramienta de trabajo, no como pagina explicativa.
- Usar texto minimo en el panel principal y en visualizacion.
- Reservar texto largo para la pestana `Agentes`, informes y detalles
  desplegables.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Reestructurar el frontend existente como cockpit visual industrial con panel
principal claro, pestana de agentes rica y sala de visualizacion 2D/3D.
```

Busquedas realizadas:

```text
rg -n "Fase 10|frontend|cockpit|visualizacion|agentes|React|Vite|dashboard|panel|Three|3D|run-to-failure|run_to_failure" codigo/docs codigo/app codigo/frontend memoria/capitulos
rg --files codigo | rg "(frontend|web|vite|react|package.json|src|components|pages|app|dashboard|visual|agent)"
wc -l codigo/frontend/src/App.tsx codigo/frontend/src/styles.css codigo/frontend/src/api.ts codigo/frontend/src/types.ts
```

Piezas canonicas encontradas:

- `codigo/frontend/src/App.tsx`: aplicacion React/Vite actual. Contiene shell,
  estado, vistas `Pipeline`, `Agentes` y `Visualizacion`, formularios, runs,
  memoria, comparacion, detalles e integracion con jobs.
- `codigo/frontend/src/api.ts`: cliente API existente para health, LLM, runs,
  jobs, artefactos, informes, memoria, comparacion y visualizacion.
- `codigo/frontend/src/types.ts`: espejo TypeScript de contratos backend,
  incluyendo `RunVisualizationData`, `TemporalRunSeries`,
  `AgentOperationalRecommendation`, memoria y jobs.
- `codigo/frontend/src/styles.css`: estilos actuales del dashboard.
- `codigo/app/services/run_visualization.py`: derivador read-only de
  visualizacion de runs.
- `codigo/app/schemas/api_visualization.py`: contrato backend de
  visualizacion.
- `codigo/docs/47_rediseño_dashboard_frontend_fase5.md`: antecedente del
  dashboard SaaS/MLOps local.
- `codigo/docs/70_fase7_hito9_panel_control_run_to_failure.md`: panel de
  control temporal run-to-failure.
- `codigo/docs/76_fase8_hito5_recomendacion_agentica_frontend.md`: exposicion
  de recomendacion operacional agentica.
- `codigo/docs/79_fase8_memoria_m1_cockpit_frontend.md`: cockpit de memoria
  agentica.

Observacion importante:

```text
App.tsx tiene mas de 5000 lineas y styles.css mas de 3000 lineas.
```

Decision:

```text
extend + modularize
```

Motivo: las capacidades estan implementadas y conectadas. La mejora necesaria
es ordenar la experiencia, extraer componentes, mejorar la jerarquia visual y
anadir visualizaciones avanzadas sobre contratos existentes.

## Vision de producto

La interfaz debe organizarse como una sala de control local para investigacion
agentica industrial:

- El usuario entra y entiende el estado del sistema en segundos.
- Puede lanzar una run con pocas decisiones claras.
- Puede ver si el backend, Ollama, memoria y dataset estan listos.
- Puede seguir el progreso de la run sin leer logs crudos.
- Puede entender el resultado operacional de una run run-to-failure sin leer
  todo el informe.
- Puede abrir la pestana `Agentes` para ver decisiones, pensamiento
  estructurado, memoria usada, debates y guardarrailes.
- Puede abrir `Visualizacion` para inspeccionar series, salud, riesgo,
  comparaciones, PCA y escenas 2D/3D con muy poco texto.

## Arquitectura de informacion objetivo

### Panel principal

Debe ser la primera vista y el centro de control diario.

Contenido recomendado:

- estado API;
- estado LLM/Ollama;
- estado memoria;
- dataset activo;
- run activa o ultima run;
- estado de salud operacional;
- recomendacion agentica condensada;
- metricas primarias del perfil;
- acciones principales;
- historial corto de runs;
- avisos criticos;
- acceso directo a agentes, visualizacion e informe.

Criterio de diseno: poco texto, mucha jerarquia visual, estados claros,
botones con iconos y detalles bajo demanda.

### Nueva run

Debe quedar como flujo operativo, no como formulario largo.

Contenido recomendado:

- seleccion de dataset;
- modo de ejecucion;
- selector LLM/agentico;
- revision humana;
- preflight;
- ejecucion;
- progreso;
- resultado.

Las opciones tecnicas avanzadas pueden permanecer, pero plegadas y con menos
presencia visual.

### Agentes

Puede ser la pestana mas rica en texto porque aqui vive la investigacion
agentica.

Contenido recomendado:

- jerarquia de agentes;
- timeline de runtime;
- decisiones estructuradas;
- confianza y rationale;
- herramientas invocadas;
- evidencia citada;
- memoria recuperada, usada y descartada;
- guardarrailes;
- debate `report_writer` / `report_verifier`;
- correcciones de contrato;
- fallbacks solo cuando sean reales y visibles;
- conversacion o trazas humanizadas cuando existan datos persistidos.

Aqui encaja la futura visualizacion 3D de agentes en oficina: puede tener valor
de portfolio y demostracion, pero debe mantenerse separada del nucleo
metodologico. Debe representar eventos reales, no simular pensamiento no
persistido.

### Visualizacion

Debe ser una sala de inspeccion visual. Poco texto y mucha lectura grafica.

Contenido recomendado:

- serie temporal de score;
- Health Index;
- Risk Index;
- bandas de salud;
- onset confirmado;
- alerta persistente;
- fallo de referencia;
- episodios de alerta;
- comparacion de modelos;
- PCA 2D como diagnostico secundario;
- vista compacta de metricas temporales;
- visualizacion 3D opcional para sala de control industrial.

La visualizacion no debe explicar demasiado en pantalla. Los detalles deben
quedar en tooltips, leyendas compactas, paneles plegables o enlaces al informe.

### Informes y evidencia

Debe mantener el informe agentico final, auditoria, evidence pack, artefactos y
debate como material trazable.

No debe ocupar el centro del panel principal, pero debe ser facil abrirlo desde
una run.

## Metodologia de implementacion

Cada hito debe seguir este orden:

1. Inventariar componentes, contratos y estilos existentes.
2. Decidir `reuse`, `adapt`, `extend` o `new`.
3. Implementar una mejora vertical pequena.
4. Mantener compatibilidad con la vista previa mientras se migra.
5. Compilar frontend.
6. Verificar manualmente la pantalla afectada.
7. Documentar el cambio.

Regla practica: si una mejora requiere tocar backend, primero comprobar si el
dato ya existe en `RunSnapshot`, `RunVisualizationData`, jobs, memoria,
artefactos o comparacion de runs.

## Hito 10.1 - Inventario frontend y mapa de componentes

Objetivo: preparar la reestructuracion sin tocar comportamiento.

Estado 2026-06-05: implementado documentalmente en
`codigo/docs/97_fase10_hito1_inventario_frontend_mapa_componentes.md`.

Alcance:

- mapear bloques actuales de `App.tsx`;
- mapear bloques de `styles.css`;
- identificar componentes internos reutilizables;
- identificar estado compartido que no debe duplicarse;
- identificar vistas y secciones que pueden extraerse sin cambiar logica;
- listar endpoints consumidos por cada vista;
- definir estructura objetivo de carpetas frontend.

Estructura candidata:

```text
codigo/frontend/src/
  components/
  views/
  hooks/
  lib/
  styles/
```

Criterio de cierre:

- documento breve de inventario;
- ninguna funcionalidad eliminada;
- `npm run build` sigue pasando si se toca algun archivo.

## Hito 10.2 - Shell y navegacion de cockpit

Objetivo: convertir la estructura global en cockpit claro.

Estado 2026-06-05: iniciado con el subhito
`codigo/docs/98_fase10_hito2a_shell_common_frontend.md`. Se han extraido
componentes `common`/`shell` y tipos UI sin cambiar comportamiento. Queda
pendiente introducir `CockpitView` como panel principal. El subhito
`codigo/docs/99_fase10_hito2b_modularizacion_runs_reports_visualizacion.md`
reduce ademas `App.tsx` moviendo detalle de run, informes y visualizacion a
modulos de dominio. El subhito
`codigo/docs/100_fase10_hito2c_modularizacion_agentes_memoria_constantes.md`
extrae agentes, memoria, constantes y helpers runtime, dejando pendiente la
modularizacion de `Pipeline/Runs/Jobs`. El subhito
`codigo/docs/101_fase10_hito2d_modularizacion_pipeline_runs_jobs.md` cierra ese
corte, extrae pipeline, preflight, jobs, historico de runs, comparacion y
helpers de request, y deja `App.tsx` como orquestador de 715 lineas.

Alcance:

- revisar navegacion principal;
- hacer del panel principal la vista por defecto;
- mantener accesibles `Pipeline`, `Agentes` y `Visualizacion`;
- separar acciones principales de detalles tecnicos;
- mejorar responsive sin cambiar APIs;
- conservar la banda de estado de backend/LLM/memoria.

Criterio de cierre:

- el usuario entiende donde lanzar, donde observar agentes y donde visualizar;
- no se pierde acceso a runs, memoria, informes ni artefactos;
- build correcto.

## Hito 10.3 - Panel principal operacional

Objetivo: crear un panel principal limpio, entendible y rapido.

Estado 2026-06-05: iniciado con el subhito
`codigo/docs/102_fase10_hito3a_cockpit_operacional_inicial.md`. Se ha creado
la vista `Cockpit` como entrada por defecto, reutilizando estado existente de
runs, health, LLM, job, run seleccionada y visualizacion persistida sin cambiar
contratos backend. El subhito
`codigo/docs/103_fase10_hito3b_cockpit_run_foco_autocargada.md` añade carga
automatica controlada de la ultima run foco, estados de carga y accesos a
visualizacion, agentes e informe. El subhito
`codigo/docs/104_fase10_hito3c_cockpit_pulido_evidencia.md` pule la jerarquia
del cockpit con una tarjeta compacta de evidencia, estados `listo`/`sin datos`
y una accion clara para abrir el detalle existente. Queda pendiente el rediseño
del flujo `Nueva run`.

Alcance:

- tarjetas compactas de estado;
- run activa o ultima run relevante;
- recomendacion agentica resumida;
- salud temporal cuando exista;
- metricas primarias del perfil;
- acciones principales;
- avisos de entorno;
- historial corto.

Regla de diseno:

```text
El panel principal no debe parecer un informe. Debe parecer una consola.
```

Criterio de cierre:

- una run completada puede entenderse a alto nivel sin abrir el informe;
- los detalles tecnicos siguen disponibles bajo demanda;
- no hay texto largo ocupando la primera vista.

## Hito 10.4 - Flujo de nueva run y preflight

Objetivo: hacer que lanzar runs agenticas sea claro y dificil de usar mal.

Estado 2026-06-05: iniciado con el subhito
`codigo/docs/105_fase10_hito4a_nueva_run_launcher_operativo.md`. Se ha
reordenado `Nueva run` como launcher operativo de cuatro pasos
(`Dataset`, `Ejecucion`, `Agentes`, `Preflight`), manteniendo opciones
tecnicas en avanzado y sin cambiar contratos backend.

Alcance:

- selector de dataset con capacidades visibles;
- modo `full` / `diagnostic`;
- activacion LLM clara;
- estado Ollama/modelo;
- revision humana;
- preflight visual;
- ejecucion en background;
- progreso y resultado.

La UI debe evitar caidas silenciosas a fallback. Si el sistema cae a fallback,
debe mostrarse como evento real, no esconderse.

Criterio de cierre:

- el usuario sabe antes de ejecutar si va con agentes LLM o sin ellos;
- el preflight separa riesgos de configuracion y detalles secundarios;
- la ejecucion conserva polling y apertura de snapshot.

## Hito 10.5 - Pestana Agentes nivel investigacion

Objetivo: hacer visible la toma de decisiones agentica sin saturar el panel
principal.

Estado 2026-06-05: iniciado con el subhito
`codigo/docs/106_fase10_hito5a_agentes_runtime_investigativo.md`. Se ha
reorganizado la pestaña `Agentes` como runtime investigativo con banda de
señales reales, mapa de agentes, detalle estructurado, memoria, timeline de
eventos y conversacion derivada de eventos persistidos. El subhito
`codigo/docs/107_fase10_hito5b_detalle_agente_decision_memoria_payload.md`
mejora el detalle de agente separando decision, señales/herramientas, memoria
citada y payload tecnico plegado. El subhito
`codigo/docs/108_fase10_hito5c_memoria_agentes_retrieval.md` refuerza el
cockpit de memoria dentro de `Agentes`, separando recuerdos recuperados,
usados, ignorados y excluidos, mostrando `memory_record_uses` y señales
observables de retrieval sin tocar backend ni contratos.

Alcance:

- jerarquia supervisor-agentes;
- timeline de eventos;
- decisiones por agente;
- herramientas usadas;
- evidencia citada;
- memoria recuperada/usada/descartada;
- guardarrailes;
- contrato reparado frente a fallback real;
- debate del informe;
- detalle de razonamiento estructurado.

Criterio de cierre:

- los agentes no aparecen como decoracion;
- cada recomendacion importante puede rastrearse a decisiones y evidencias;
- el usuario puede diferenciar decision LLM, herramienta determinista y
  ejecutor.

## Hito 10.6 - Visualizacion 2D avanzada

Objetivo: convertir `Visualizacion` en una sala de analisis clara y potente.

Estado 2026-06-06: cerrado y verificado en
`codigo/docs/111_fase10_cierre_hito6_visualizacion_2d_avanzada.md`. El subhito
`codigo/docs/109_fase10_hito6a_visualizacion_2d_temporal_hi.md` refuerza la
lectura temporal 2D con una grafica secundaria de Health Index y un rail de
episodios de alerta/critico, reutilizando `TemporalRunSeries` sin cambiar
backend ni contratos. El subhito
`codigo/docs/110_fase10_hito6b_comparacion_visual_runs_modelos.md` añade
comparacion visual de runs/modelos dentro de `Visualizacion`, reutilizando
`RunComparison`, `compareRuns(...)` y el estado existente del frontend sin
cambiar backend ni contratos.

Alcance:

- serie temporal de score e HI;
- bandas de estado;
- umbral;
- onset confirmado;
- alerta persistente;
- fallo de referencia;
- episodios de alerta;
- comparacion visual de modelos;
- PCA 2D secundaria;
- tooltips y leyendas compactas.

Decision tecnica inicial:

- usar SVG/canvas nativo o componentes propios si basta con el contrato actual;
- introducir una libreria de graficas solo si reduce complejidad real.

Criterio de cierre:

- la visualizacion temporal se entiende sin parrafos explicativos;
- no se inventan metricas en frontend;
- los datos salen de `RunVisualizationData` o comparacion existente.
- `npm run build` pasa y los endpoints locales de health, runs, visualizacion
  y comparacion responden con runs reales persistidas.

## Hito 10.7 - Sala 3D de visualizacion industrial

Objetivo: explorar una visualizacion 3D como sala de control, sin poner en
riesgo la app base.

Estado 2026-06-06: cerrado con
`codigo/docs/115_fase10_hito7d_cierre_sala_3d_industrial.md`. Iniciado con
`codigo/docs/112_fase10_hito7a_sala_3d_base_threejs.md`. Se anade una escena
Three.js aislada, cargada bajo demanda desde `Visualizacion`, con fallback
WebGL, selector `2D`/`3D`, camara orbit limitada y escena industrial minima.
La sala 2D sigue siendo el modo por defecto. El subhito
`codigo/docs/113_fase10_hito7b_mapeo_temporal_3d.md` conecta la escena con
puntos reales de `TemporalRunSeries`, coloreando barras por `health_state`,
escalando altura por `risk_index`/`score_ratio` y mostrando marcadores 3D de
primer pico, aviso sostenido y fallo historico. El subhito
`codigo/docs/114_fase10_hito7c_interaccion_3d_ligera.md` anade hover,
seleccion fijada y ficha compacta de barras/marcadores mediante `THREE.Raycaster`.
El subhito `codigo/docs/115_fase10_hito7d_cierre_sala_3d_industrial.md`
anade enfoque rapido de marcadores, fallback de serie temporal vacia y cierre
documental de la sala 3D.

Alcance:

- escena Three.js aislada;
- vista de activo/sala industrial;
- indicadores de estado sobre el activo;
- puntos temporales o bandas representadas en 3D;
- controles simples;
- fallback visual limpio si WebGL no esta disponible.

Regla de alcance:

```text
La escena 3D debe ser una capa de inspeccion, no el unico modo de entender una run.
```

Criterio de cierre:

- build correcto;
- escena no queda en blanco;
- funciona en desktop y movil razonable;
- no bloquea las vistas 2D;
- verificacion visual con capturas si se incorpora Playwright.

## Hito 10.8 - Oficina 3D de agentes

Objetivo: prototipar una vista visual de agentes como recurso demostrativo y de
portfolio, manteniendo honestidad metodologica.

Estado 2026-06-06: iniciado. Los subhitos `10.8A`, `10.8B` y `10.8C` quedan
implementados en `codigo/docs/117_fase10_hito8a_oficina_3d_agentes_base.md`,
`codigo/docs/118_fase10_hito8b_oficina_3d_runtime_senales.md` y
`codigo/docs/119_fase10_hito8c_oficina_3d_interaccion_foco.md`. La guia
operativa general del hito queda en
`codigo/docs/116_fase10_hito8_oficina_3d_agentes_plan.md`.

Alcance:

- ubicar la vista dentro de `Agentes`, no dentro de `Visualizacion`;
- mantener la oficina 3D como modo opcional, sin sustituir timeline, detalle,
  memoria ni conversacion;
- representar cada agente persistido como mesa/nodo de trabajo:
  `supervisor`, `cleaner`, `structurer`, `modeler`, `evaluator`,
  `report_writer` y `report_verifier`;
- usar eventos reales de `AgentRuntimeEvent` para actividad, enlaces,
  memoria, herramientas, errores y debate;
- permitir seleccionar un agente desde la escena reutilizando `onSelectAgent`;
- cargar Three.js bajo demanda mediante `React.lazy`;
- reutilizar el patron de fallback WebGL y verificacion Playwright del Hito
  10.7.

Subhitos propuestos:

- `10.8A`: base de oficina 3D en `Agentes`, escena estatica, lazy loading,
  fallback WebGL y boton `2D`/`3D`. Estado: implementado.
- `10.8B`: mapeo de eventos reales a estados visuales: agente activo, conteo
  de eventos, errores, memoria, herramientas y debate. Estado: implementado.
- `10.8C`: interaccion ligera con `Raycaster`: hover/click de agente, ficha
  compacta, foco de camara, botones por agente y sincronizacion con el detalle
  existente. Estado: implementado.
- `10.8D`: cierre/pulido con runtime vivo: lanzar una run pequena si se decide,
  comprobar transiciones reales, senales durante `job.events` y documentacion
  final de cierre.

Arquitectura prevista:

- `codigo/frontend/src/components/agents/AgentOffice3D.tsx`;
- `codigo/frontend/src/lib/agentOffice3d.ts`;
- estilos nuevos en `codigo/frontend/src/styles.css`, acotados con prefijo
  `agent-office-3d`;
- integracion en `AgentObservabilityView`, junto al panel actual
  `agent-map-panel`, con selector de modo o bloque plegable.

Fuentes de datos permitidas:

- `AGENT_PROFILES`, `agentLabel(...)`, `eventsForAgent(...)` y
  `eventOwnerId(...)` desde `agentRuntime.ts`;
- `AgentRuntimeEvent.sequence`, `kind`, `source`, `stage`, `created_at`,
  `decision_id`, `memory_record_ids`, `retrieved_memory_record_ids`,
  `cited_memory_record_ids`, `ignored_memory_record_ids` y payloads existentes;
- `selectedAgentId` y `onSelectAgent` ya recibidos por `AgentObservabilityView`;
- memoria ya expuesta por `AgentMemoryPanel`, sin crear endpoints nuevos.

Advertencia:

```text
Esta vista puede vender muy bien el proyecto, pero no debe presentarse como
potencia investigatoria si no aporta evidencia nueva. Su valor principal es
comunicacion, trazabilidad visual y portfolio.
```

Reglas de alcance:

- no simular pensamiento ni conversaciones no persistidas;
- no inventar herramientas, memoria ni decisiones;
- no crear backend nuevo en el primer bloque;
- no mezclar la oficina de agentes con la sala industrial de `Visualizacion`;
- no duplicar estado de agentes si puede derivarse de `AgentRuntimeEvent`;
- si no hay eventos, mostrar oficina en reposo con estado vacio honesto.

Criterio de cierre:

- representa eventos reales;
- no simula razonamiento inexistente;
- se puede desactivar o ignorar sin perder funcionalidad cientifica;
- el build pasa;
- la escena no queda en blanco;
- se valida con Playwright/screenshot al menos en desktop y movil;
- la seleccion en 3D actualiza el detalle de agente ya existente.

## Hito 10.9 - Identidad visual industrial y reduccion de texto

Objetivo: convertir la app en un producto con identidad propia de deteccion
industrial y cockpit multiagente, reduciendo texto visible en zonas
funcionales sin eliminar trazabilidad.

Estado 2026-06-06: cerrado como bloque visual. El plan operativo queda en
`codigo/docs/120_fase10_hito9_identidad_visual_industrial_plan.md`. Los
subhitos `10.9A`, `10.9B`, `10.9C`, `10.9D`, `10.9E` y `10.9F` quedan
implementados en
`codigo/docs/121_fase10_hito9a_tokens_shell_industrial.md`,
`codigo/docs/122_fase10_hito9b_cockpit_baja_lectura.md`,
`codigo/docs/123_fase10_hito9c_reduccion_textual_pestanas.md`,
`codigo/docs/124_fase10_hito9d_memoria_agentica_visual.md`,
`codigo/docs/125_fase10_hito9e_metricas_visualizacion_subpantalla.md` y
`codigo/docs/126_fase10_hito9f_qa_visual_global.md`.

Direccion visual:

- `Industrial Agentic Cockpit` como nombre de trabajo;
- base clara industrial, no blanco puro;
- superficies tecnicas, bordes finos y jerarquia compacta;
- acentos por significado:
  - verde petroleo para OK/aprobado;
  - azul electrico para datos, memoria y señal;
  - ambar para revision, incertidumbre y avisos;
  - rojo tecnico para error, anomalia o critico;
  - violeta solo para modelado, no como tema dominante;
- LEDs, chips, railes, medidores y estados compactos como lenguaje visual;
- texto profundo bajo demanda.

Regla central:

```text
Ver primero estado y accion.
Leer solo al inspeccionar.
Auditar solo al abrir detalle.
```

Alcance:

- tokens CSS y sistema visual de app;
- shell/sidebar/topbar con identidad industrial;
- cockpit mas funcional y menos textual;
- reduccion de texto visible en `Nueva run`, `Visualizacion`, `Agentes` y
  runs;
- detalles largos plegados, en drawers, acordeones o secciones de evidencia;
- mantener toda la informacion existente en estado, informes, memoria,
  artefactos y detalles bajo demanda.

Subhitos propuestos:

- `10.9A`: tokens visuales y shell industrial.
- `10.9B`: cockpit funcional de baja lectura.
- `10.9C`: reduccion textual por pestañas.
- `10.9D`: memoria agentica visual.
- `10.9E`: visualizacion industrial guiada.
- `10.9F`: sistema visual coherente y QA.

Estado de subhitos:

- `10.9A`: implementado;
- `10.9B`: implementado;
- `10.9C`: implementado;
- `10.9D`: implementado;
- `10.9E`: implementado;
- `10.9F`: implementado y cerrado.

Nota posterior a `10.9C`:

- el resumen global queda oculto fuera de `Cockpit`;
- el contexto de ejecucion se compacta en una linea plegable;
- `Runs locales` queda como drawer plegado por defecto;
- la memoria agentica queda plegada provisionalmente y se reserva para una
  subpestaña propia dentro de `Agentes`;
- `Visualizacion` incorpora secciones internas (`Estado`, `Agente`,
  `Comparar`, `Serie`, `Mapa`) para evitar una sucesion larga de graficas.

Nota posterior a `10.9D`:

- `Agentes` incorpora selector interno `Runtime | Memoria`;
- `Memoria` se activa con boton de cerebro;
- la memoria se muestra como selector visual de agentes;
- cada agente tiene color, rol, avatar de pie, herramientas y recuerdos
  concisos;
- el supervisor queda diferenciado con corona/rol de jefe;
- la memoria tecnica sigue disponible en detalle plegado;
- build y Playwright desktop/movil correctos.

Nota posterior a `10.9E`:

- `Visualizacion` mantiene secciones internas y añade `Metricas` como
  subpantalla propia;
- el panel fijo de metricas deja de ocupar la primera lectura;
- el usuario valida manualmente la vista con una run real y confirma que no
  queda pendiente funcional en `10.9E`;
- el cierre visual global se completa posteriormente en `10.9F`.

Nota posterior a `10.9F`:

- QA visual global documentado en
  `codigo/docs/126_fase10_hito9f_qa_visual_global.md`;
- Playwright revisa desktop `1440x1100` y movil `390x920`;
- vistas revisadas: `Cockpit`, `Nueva run`, `Agentes Runtime`, `Agentes
  Memoria`, `Visualizacion Estado` y `Visualizacion Metricas`;
- sin errores de consola, sin respuestas fallidas y sin overflow horizontal;
- `npm run build` correcto;
- el bloque `10.9` queda cerrado.

### 10.9D - Memoria agentica visual

Objetivo: convertir la memoria de agentes en una subpestaña propia dentro de
`Agentes`, accesible mediante un boton de cerebro, con una experiencia tipo
selector de personajes.

Alcance:

- selector superior de agentes;
- avatar/personaje visual por agente;
- color y rol del agente;
- herramientas/capacidades como chips;
- recuerdos humanos concisos en tarjetas;
- memoria tecnica y payloads bajo demanda;
- reutilizacion de `AgentMemoryPanel`, eventos runtime y records existentes.

Criterio de cierre:

- se puede abrir `Memoria` desde `Agentes`;
- se puede seleccionar cada agente;
- la vista superior tiene muy poco texto;
- los recuerdos principales son frases humanas cortas;
- la memoria tecnica sigue accesible;
- build y validacion visual desktop/movil correctos.

Estado 2026-06-06: implementado y verificado en
`codigo/docs/124_fase10_hito9d_memoria_agentica_visual.md`.

### 10.9E - Visualizacion industrial guiada

Objetivo: evolucionar `Visualizacion` desde secciones internas hacia una vista
de inspeccion industrial mas guiada, donde el usuario entienda rapidamente que
grafica esta mirando y por que importa.

Alcance:

- priorizar una narrativa visual por estado;
- reducir graficas simultaneas;
- mejorar selector de `Estado`, `Metricas`, `Agente`, `Comparar`, `Serie` y
  `Mapa`;
- mantener 3D opcional y sin saturar la vista.

Estado 2026-06-06:

- `10.9E-A` implementado en
  `codigo/docs/125_fase10_hito9e_metricas_visualizacion_subpantalla.md`;
- el apartado `Metricas` pasa a ser subpantalla interna;
- el panel fijo de metricas deja de ocupar la primera lectura;
- validado posteriormente con backend activo y run real;
- `10.9E` queda cerrado.

### 10.9F - Sistema visual coherente y QA

Objetivo: cerrar el bloque visual tras memoria y visualizacion, unificando
estilos, contraste, responsive y evidencias de verificacion.

Criterio de cierre:

- la app deja de parecer una libreta blanca generica;
- el cockpit se percibe como consola industrial real;
- las vistas funcionales muestran poco texto por defecto;
- la evidencia sigue accesible;
- build correcto y validacion visual desktop/movil.

Estado 2026-06-06: implementado y cerrado en
`codigo/docs/126_fase10_hito9f_qa_visual_global.md`.

## Hito 10.10 - Informe, evidencia y artefactos

Objetivo: ordenar la lectura final de una run sin convertirla en la primera
experiencia del usuario.

Estado 2026-06-06: implementado y verificado en
`codigo/docs/127_fase10_hito10_informe_evidencia_artefactos.md`.

Alcance:

- informe final legible;
- auditoria determinista;
- debate agentico;
- evidence pack;
- artefactos;
- metricas;
- rutas tecnicas ocultas o plegadas;
- enlaces desde panel principal y agentes.

Criterio de cierre:

- el usuario puede pasar de recomendacion a evidencia en pocos clics;
- el informe no compite con el cockpit principal;
- se mantiene trazabilidad completa.

Resultado:

- `RunEvidenceHub` visible en `Nueva run` para la run foco;
- informe, auditoria, debate y artefactos quedan como documentos plegados;
- rutas tecnicas de artefactos se ocultan bajo demanda;
- `RunDetailView` reutiliza el mismo centro de evidencia;
- `Agentes` añade acceso corto a evidencia;
- build y Playwright desktop/movil correctos.

## Hito 10.11 - Pulido, QA visual y Docker

Objetivo: cerrar la fase con verificacion de producto.

Alcance:

- `npm run build`;
- smoke local del frontend;
- verificacion de proxy `/api`;
- responsive desktop/movil;
- revision de solapes de texto;
- capturas Playwright si se anade;
- canvas-pixel check para escenas 3D si se anaden;
- rebuild Docker frontend si hay cambios relevantes.

Criterio de cierre:

- el cockpit queda como vista principal;
- las vistas antiguas siguen accesibles o migradas sin perdida;
- el panel principal es claro y poco textual;
- `Agentes` concentra la profundidad agentica;
- `Visualizacion` ofrece analisis 2D/3D sin saturacion textual;
- build y smoke son correctos.

## Dependencias visuales

Estado actual:

```text
React + Vite + TypeScript + lucide-react + three
```

Politica:

- no anadir librerias por estetica;
- `three` ya esta incorporado por Hito 10.7 y debe seguir cargado bajo demanda;
- Playwright/Chromium ya estan disponibles como verificacion visual local;
- anadir libreria de graficas solo si evita codigo fragil;
- mantener iconografia con `lucide-react`;
- evitar un sistema de componentes pesado si no aporta productividad real.

## Verificacion minima por hito

Para cambios solo frontend:

```text
cd codigo/frontend
npm run build
```

Para cambios con backend:

```text
python -m unittest discover codigo/tests
cd codigo/frontend
npm run build
```

Para cambios de visualizacion:

- abrir frontend local;
- cargar una run persistida;
- revisar `Panel principal`;
- revisar `Agentes`;
- revisar `Visualizacion`;
- comprobar desktop y movil;
- confirmar que no hay texto solapado;
- confirmar que la UI no muestra rutas locales innecesarias;
- confirmar que no hay estados falsamente optimistas.

## Fuera de alcance

- autenticacion multiusuario;
- despliegue cloud;
- SLURM;
- landing page;
- reescritura completa del frontend;
- nuevo backend de visualizacion paralelo;
- estimacion RUL nueva;
- nuevas metricas PHM no implementadas;
- simulaciones visuales que no esten conectadas a datos reales;
- eliminar la trazabilidad textual de agentes.

## Riesgos y mitigaciones

### Riesgo: romper flujos existentes

Mitigacion: migrar por vistas, conservar accesos y compilar en cada hito.

### Riesgo: exceso visual sin valor metodologico

Mitigacion: toda visualizacion debe responder a una pregunta operacional o
mostrar una decision/evidencia real.

### Riesgo: panel principal demasiado textual

Mitigacion: mover rationale, conversaciones, debates y JSON a `Agentes` o
detalles plegables.

### Riesgo: 3D costoso

Mitigacion: tratarlo como hito aislado y opcional, despues de tener 2D solido.

### Riesgo: la UI quite protagonismo a los LLM

Mitigacion: el cockpit resume decisiones agenticas, no las reemplaza. Las
herramientas y visualizaciones se presentan como soporte para que los agentes
decidan y el usuario audite.

## Primer paso recomendado

Retomar con Hito 10.11:

```text
Pulido, QA visual y Docker
```

La identidad visual base, el shell industrial, el cockpit de baja lectura y la
reduccion textual por pestañas ya estan implementados. La subpestaña visual de
memoria dentro de `Agentes` tambien queda implementada, y `Visualizacion` queda
validada tras `10.9E`. El QA visual global `10.9F` queda cerrado con capturas
desktop/movil y build correcto. `10.10` deja informe, evidencia, auditoria,
debate y artefactos ordenados bajo demanda. El siguiente paso recomendado es
el cierre de fase: smoke local, revision visual final y, si se decide, rebuild
Docker frontend/backend.
