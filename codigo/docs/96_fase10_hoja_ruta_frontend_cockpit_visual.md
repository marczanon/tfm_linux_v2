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

## Hito 10.7 - Sala 3D de visualizacion industrial

Objetivo: explorar una visualizacion 3D como sala de control, sin poner en
riesgo la app base.

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

Alcance:

- cada agente como figura o avatar simple;
- oficina o sala de trabajo;
- interacciones basadas en eventos reales;
- activaciones por timeline;
- conexiones de memoria/herramientas/debate;
- modo demo vinculado a una run real.

Advertencia:

```text
Esta vista puede vender muy bien el proyecto, pero no debe presentarse como
potencia investigatoria si no aporta evidencia nueva. Su valor principal es
comunicacion, trazabilidad visual y portfolio.
```

Criterio de cierre:

- representa eventos reales;
- no simula razonamiento inexistente;
- se puede desactivar o ignorar sin perder funcionalidad cientifica.

## Hito 10.9 - Informe, evidencia y artefactos

Objetivo: ordenar la lectura final de una run sin convertirla en la primera
experiencia del usuario.

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

## Hito 10.10 - Pulido, QA visual y Docker

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
React + Vite + TypeScript + lucide-react
```

Politica:

- no anadir librerias por estetica;
- anadir `three` solo cuando se implemente un hito 3D real;
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

Continuar con Hito 10.3:

```text
Panel principal operacional / CockpitView
```

La base de modularizacion ya esta preparada. El siguiente paso debe introducir
una vista principal clara, poco textual y orientada a control operacional,
reutilizando los modulos extraidos y sin cambiar contratos backend.
