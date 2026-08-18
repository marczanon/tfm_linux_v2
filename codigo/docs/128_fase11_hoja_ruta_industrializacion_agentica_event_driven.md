# Fase 11 - Hoja de ruta industrializacion agentica event-driven

Fecha: 2026-06-07.

Estado: propuesta historica amplia. Desde 2026-08-11, la guia activa es
`133_fase11_reenfoque_hibrido_nasa_replay_agentico.md`, que conserva el replay
y la supervision por eventos, pero difiere colas, workers, nuevos datasets y
despliegue industrial para concentrar el TFM en NASA IMS.

Documentos de partida:

- `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`;
- `codigo/docs/54_cierre_operativo_fase6.md`;
- `codigo/docs/88_fase8_memoria_m4_5_qwen_qdrant_citas_agenticas.md`;
- `codigo/docs/95_cierre_fase9_run_to_failure_maximo_nivel.md`;
- `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`;
- `codigo/docs/127_fase10_hito10_informe_evidencia_artefactos.md`.

## Objetivo

Convertir la aplicacion en un prototipo industrial local defendible, capaz de
operar sobre flujos continuos simulados, colas persistentes, automatizacion de
procesos y datasets no vistos, manteniendo a los agentes Qwen/LLM como centro
de decision del sistema.

La Fase 11 no busca crear una plataforma cloud productiva ni sustituir la
arquitectura actual. Busca demostrar que el sistema puede pasar de ejecuciones
batch cerradas a una operacion industrial continua y trazable:

```text
stream continuo -> evidencia determinista -> eventos significativos
  -> agentes deciden -> ejecutores controlados actuan -> evidencia persistida
```

La idea clave es:

```text
No llamar agentes para cada muestra.
Llamar agentes para cada decision industrial.
```

## Cambio de paradigma

Hasta Fase 10, el flujo principal es una run batch:

```text
POST /runs
  -> agentes deciden configuraciones
  -> ejecutores deterministas aplican fases
  -> evaluacion
  -> informe, memoria, visualizacion y evidencia
```

En Fase 11, se anade un modo operativo continuo:

```text
StreamSession
  -> replay o ingesta incremental de ventanas
  -> scoring continuo y health/risk index
  -> deteccion de eventos
  -> revision agentica event-driven
  -> cola/worker/acciones controladas
  -> incidentes, informes, memoria y post-mortems
```

La capa continua no reemplaza a los agentes. Su funcion es generar evidencia
barata, reproducible y frecuente. Los agentes siguen siendo protagonistas en:

- inicio y validacion de una sesion industrial;
- seleccion o confirmacion de estrategia de modelo;
- interpretacion de degradacion sostenida;
- auditoria de alertas operacionales;
- decision de recalibracion, reentrenamiento o cierre de incidente;
- curacion de memoria;
- generacion y verificacion de informes;
- evaluacion de datasets no vistos.

## Principios no negociables

- No romper `POST /runs` ni las runs batch ya implementadas.
- No crear un frontend paralelo.
- No crear runners por dataset si puede extenderse el runner comun.
- No convertir la Fase 11 en un pipeline determinista sin agentes.
- No llamar al LLM en cada ventana o muestra si no hay decision que tomar.
- No permitir que los agentes escriban ni ejecuten codigo arbitrario.
- No ocultar fallbacks: si un agente no pudo decidir, debe quedar registrado.
- No presentar etiquetas proxy como ground truth oficial.
- No inferir diagnosticos nuevos en frontend sin contrato o artefacto.
- No indexar memoria especifica de un dataset nuevo antes del experimento
  cold-start.
- Mantener contratos estrictos Pydantic/JSON para toda decision agentica.
- Mantener ejecutores deterministas para lectura, scoring, persistencia y
  acciones.
- Mantener trazabilidad de eventos, colas, decisiones, memoria y artefactos.
- Mantener Docker como via de validacion reproducible cuando cambie el stack.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Industrializar la aplicacion local con streaming simulado, cola persistente,
workers, eventos agenticos, automatizacion y datasets no vistos, sin duplicar
runners, contratos, memoria ni frontend.
```

Piezas canonicas que deben revisarse antes de implementar cada hito:

- `codigo/app/services/pipeline_runner.py`: runner canonico multi-dataset;
- `codigo/app/services/api_run_jobs.py`: jobs API locales en memoria;
- `codigo/app/services/run_persistence.py`: persistencia de snapshots;
- `codigo/app/services/run_registry.py`: consulta y comparacion de runs;
- `codigo/app/services/dataset_adapters.py`: registro de adaptadores;
- `codigo/app/services/signal_adapters.py`: lectura de senales y tablas;
- `codigo/app/services/nasa_ims_temporal_policy.py`: politica temporal NASA;
- `codigo/app/services/human_review.py`: revision humana;
- `codigo/app/services/run_visualization.py`: visualizacion read-only;
- `codigo/app/services/agent_memory.py`: memoria para prompts de agentes;
- `codigo/app/services/vector_memory.py`: memoria vectorial JSON/Qdrant;
- `codigo/app/services/decision_memory.py`: episodios y candidatos;
- `codigo/app/graph/pipeline.py`: orquestacion LangGraph actual;
- `codigo/app/schemas/pipeline_run.py`: contrato comun de ejecucion;
- `codigo/app/schemas/api_runs.py`: contrato de API de runs;
- `codigo/app/schemas/api_visualization.py`: contrato de visualizacion;
- `codigo/app/api/routes.py`: frontera FastAPI existente;
- `codigo/frontend/src/api.ts`: cliente API del frontend;
- `codigo/frontend/src/types.ts`: espejo TypeScript de contratos;
- `codigo/frontend/src/components/cockpit/CockpitView.tsx`;
- `codigo/frontend/src/components/pipeline/PipelineConfig.tsx`;
- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`;
- `codigo/frontend/src/components/visualization/VisualizationView.tsx`;
- `codigo/frontend/src/components/reports/ReportPanels.tsx`;
- `codigo/docker/docker-compose.yml`: stack local reproducible.

Decision de fase:

```text
extend + adapt + new acotado
```

Motivo:

- `extend`: la ejecucion batch, memoria, visualizacion, informes y cockpit ya
  existen y deben seguir siendo la base.
- `adapt`: jobs, snapshots, visualizacion y frontend deben entender sesiones y
  eventos continuos sin perder compatibilidad.
- `new acotado`: streaming, cola persistente, worker y politicas de
  automatizacion no tienen propietario claro hoy; deben crearse como piezas
  nuevas con fronteras estrictas y sin duplicar el pipeline existente.

Impacto en compatibilidad:

- `POST /runs` sigue funcionando como hasta ahora.
- Las runs persistidas siguen siendo consultables.
- Los endpoints actuales no se eliminan.
- Las nuevas sesiones continuas pueden crear snapshots compatibles al cierre.
- Qdrant sigue siendo opcional.
- Docker minimo sigue levantando backend/frontend; worker/cola/Qdrant pueden
  anadirse como perfil o servicios documentados.

Busquedas obligatorias antes del primer hito de codigo:

```text
rg -n "job|queue|background|RunJob|worker|session|stream|event|watermark|automation|policy|trigger" codigo/app codigo/scripts codigo/tests codigo/docs
rg -n "TemporalRunSeries|health_index|risk_index|run_to_failure|visualization|compareRuns|AgentRuntimeEvent" codigo/app codigo/frontend/src codigo/tests codigo/docs
rg -n "Memory|memory|Qdrant|RetrievedMemory|DecisionEpisode|MemoryCandidate|human_review" codigo/app codigo/tests codigo/docs
rg --files codigo/app codigo/frontend/src codigo/scripts codigo/tests codigo/docs | sort
```

## Arquitectura objetivo

```text
Navegador
  -> frontend React/Vite
      -> Cockpit industrial
      -> Stream sessions
      -> Cola y workers
      -> Eventos e incidentes
      -> Agentes, memoria, visualizacion, evidencia

FastAPI
  -> endpoints actuales de runs
  -> endpoints nuevos de streams, cola, eventos y automatizacion
  -> servicios read-only de visualizacion y evidencia

Worker local
  -> consume cola persistente
  -> ejecuta replay/scoring/inferencia/acciones permitidas
  -> persiste eventos, snapshots y artefactos

Capa determinista continua
  -> lee senales por ventanas
  -> calcula features y scores
  -> actualiza Health Index / Risk Index
  -> detecta triggers
  -> no toma decisiones agenticas finales

Capa agentica event-driven
  -> recibe expedientes de evento
  -> consulta herramientas read-only
  -> recupera memoria
  -> decide mediante contratos estrictos
  -> genera recomendaciones, acciones permitidas, informes y memoria candidata

Persistencia local
  -> codigo/reports/runs
  -> codigo/reports/stream_sessions
  -> codigo/reports/industrial_events
  -> codigo/reports/reasoning_memory o Qdrant opcional
```

## Conceptos nuevos

### Asset

Representa un activo industrial observado:

- `asset_id`;
- `asset_type`;
- `dataset_id`;
- `adapter_id`;
- `supervision_profile`;
- metadatos tecnicos;
- politica operacional asociada.

Ejemplos:

- rodamiento XJTU-SY;
- rodamiento NASA IMS;
- bomba o ventilador MIMII;
- motor CWRU en modo diagnostico historico.

### StreamSession

Sesion continua simulada o real. En la Fase 11 sera, por defecto, un replay
controlado desde datos historicos.

Campos candidatos:

- `stream_session_id`;
- `asset_id`;
- `dataset_id`;
- `raw_path`;
- `adapter_id`;
- `profile_id`;
- `started_at`;
- `status`;
- `cursor`;
- `watermark`;
- `window_count`;
- `event_count`;
- `agentic_event_count`;
- `queue_job_ids`;
- `artifact_root`;
- `closed_run_id` opcional.

### StreamWindow

Unidad minima de ingesta incremental.

Campos candidatos:

- `window_id`;
- `stream_session_id`;
- `sequence`;
- `source_path`;
- `start_time`;
- `end_time`;
- `sample_count`;
- `feature_path`;
- `score`;
- `health_index`;
- `risk_index`;
- `health_state`;
- `created_at`.

### IndustrialEvent

Evento significativo que puede requerir decision agentica.

Tipos iniciales:

- `stream_started`;
- `unknown_dataset_profile`;
- `model_ready`;
- `score_spike`;
- `persistent_alert`;
- `critical_degradation`;
- `drift_detected`;
- `model_disagreement`;
- `worker_failed`;
- `queue_retry_exhausted`;
- `human_review_required`;
- `session_closed`;
- `memory_candidate_ready`.

### AgenticEventReview

Decision agentica asociada a un evento.

Campos candidatos:

- `review_id`;
- `event_id`;
- `target_agent`;
- `decision_kind`;
- `recommended_action`;
- `confidence`;
- `rationale`;
- `evidence_refs`;
- `memory_refs`;
- `tool_refs`;
- `guardrails`;
- `requires_human_review`;
- `allowed_executor_action`;
- `fallback_used`;
- `errors`.

### QueueJob

Trabajo persistente consumido por worker local.

Campos candidatos:

- `job_id`;
- `job_type`;
- `status`;
- `priority`;
- `payload`;
- `attempts`;
- `max_attempts`;
- `created_at`;
- `started_at`;
- `finished_at`;
- `last_error`;
- `idempotency_key`;
- `artifact_refs`.

### AutomationPolicy

Politica declarativa para decidir que hacer ante eventos.

Ejemplos:

- alerta persistente -> crear `AgenticEventReview` con `evaluator`;
- drift -> crear revision con `modeler`;
- error repetido de worker -> `human_review_required`;
- cierre de sesion -> informe de sesion;
- memoria candidata -> curacion antes de indexar.

## Agentes en la Fase 11

La Fase 11 mantiene los agentes existentes y solo introducira nuevos roles si
hay una responsabilidad clara que no encaje en los actuales.

Roles previstos:

- `supervisor`: gobierna el flujo y decide si se activa una revision agentica.
- `stream_supervisor`: rol conceptual para eventos de streaming; inicialmente
  puede implementarse como extension del supervisor si no justifica agente
  nuevo.
- `modeler`: decide si el modelo/umbral/estrategia sigue siendo adecuado ante
  drift, dataset nuevo o desacuerdo de modelos.
- `evaluator`: interpreta degradacion sostenida, alertas persistentes y
  defendibilidad operacional.
- `report_writer`: redacta informes de sesion, incidente y cierre.
- `report_verifier`: audita exageraciones, evidencia faltante y limites.
- `memory_curator`: rol conceptual para decidir si una experiencia se indexa,
  se excluye o queda en revision; puede empezar como contrato o servicio
  alrededor de `decision_memory.py` antes de convertirse en agente propio.

Regla de protagonismo:

```text
Un evento industrial importante no queda cerrado sin una decision agentica o
una razon explicita de fallback/human-review.
```

## Triggers agenticos

No todos los eventos llaman al LLM. La politica debe separar telemetria,
eventos y decisiones.

Triggers de alta prioridad:

- inicio de dataset no visto;
- degradacion critica;
- alerta persistente;
- cambio brusco de Health Index;
- drift persistente;
- desacuerdo entre modelos;
- fallo repetido de worker;
- cola bloqueada;
- cierre de sesion con incidente;
- memoria candidata con impacto metodologico.

Triggers de prioridad media:

- spike aislado;
- subida moderada de riesgo;
- latencia alta de worker;
- falta de memoria recuperada;
- evidencia incompleta;
- recomendacion de recalibracion.

Eventos puramente deterministas:

- ventana ingerida;
- score calculado;
- cursor actualizado;
- heartbeat de worker;
- progreso de cola;
- snapshot parcial guardado.

Mitigaciones de coste y latencia:

- cooldown por tipo de evento;
- debouncing de alertas repetidas;
- histeresis temporal;
- prioridad de cola agentica;
- resumen compacto de evidencia;
- reutilizacion de memoria recuperada en la sesion;
- fallback visible si el LLM no responde;
- human review cuando la decision sea costosa o incierta.

## Datasets candidatos

La Fase 11 debe conservar datasets actuales como regresion y anadir al menos un
dataset no visto para challenge cold-start.

### Regresion

- CWRU: diagnostico historico y compatibilidad.
- NASA IMS actual/sintetico: perfil run-to-failure ya trabajado.

### Nuevo dataset principal recomendado

`XJTU-SY Bearing Datasets`

Motivo:

- rodamientos;
- run-to-failure;
- degradacion acelerada completa;
- encaja con vibracion, Health Index, riesgo y alertas sostenidas;
- permite comprobar generalizacion sin cambiar de dominio radical.

Uso previsto:

- no indexar memoria especifica antes del primer experimento;
- ejecutar cold-start con memoria congelada;
- comparar `memory_off`, `memory_generic_on` y post-mortem;
- crear adaptador solo si `dataset_adapters.py` y `signal_adapters.py` no
  cubren el formato.

### Segundo dataset opcional

`MIMII`

Motivo:

- maquinaria industrial realista por audio;
- bombas, valvulas, ventiladores y railes;
- ruido de fabrica;
- buen reto de generalizacion fuera de vibracion.

Uso previsto:

- no mezclar con el primer bloque si retrasa XJTU-SY;
- tratarlo como expansion multimodal/audio;
- documentar limites si el pipeline actual exige adaptador nuevo de audio.

### C-MAPSS / turbofan

Interesante para PHM y RUL, pero debe tratarse como opcion condicionada a
disponibilidad local y licencia de datos. No debe bloquear la fase.

## Hitos

### Hito 11.1 - Inventario y diseno de fronteras

Objetivo: preparar la industrializacion sin tocar comportamiento.

Alcance:

- inventariar jobs, runs, memoria, visualizacion, frontend y Docker;
- decidir propietario canonico para streaming, cola, eventos y politicas;
- documentar si cada pieza sera `reuse`, `adapt`, `extend` o `new`;
- definir estructura de carpetas candidata sin crear codigo prematuramente;
- elegir persistencia inicial de cola.

Decision inicial recomendada:

```text
SQLite/local file store primero; Redis/Celery solo como perfil opcional si el
prototipo local lo necesita.
```

Criterio de cierre:

- documento `129_fase11_hito1_inventario_industrializacion.md`;
- mapa de responsabilidades;
- ninguna funcionalidad existente modificada.

### Hito 11.2 - Contratos de streaming, eventos y cola

Objetivo: crear contratos estrictos antes de implementar servicios.

Contratos candidatos:

- `AssetDescriptor`;
- `StreamSessionRequest`;
- `StreamSessionSnapshot`;
- `StreamWindowRecord`;
- `IndustrialEvent`;
- `AgenticEventReview`;
- `AutomationPolicy`;
- `QueueJobRecord`;
- `WorkerHeartbeat`;
- `StreamIncidentReport`;
- `ColdStartEvaluationPlan`.

Reglas:

- todo contrato debe ser Pydantic;
- los campos opcionales deben ser explicitos;
- no guardar datasets completos en estado;
- guardar rutas, metricas, resumenes y refs;
- mantener compatibilidad con snapshots de run.

Criterio de cierre:

- tests de esquemas;
- documentacion de campos;
- decision clara de que endpoint o servicio consume cada contrato.

### Hito 11.3 - Replay streaming local reproducible

Objetivo: simular streaming continuo desde datasets historicos sin crear
dependencia de hardware real.

Alcance:

- crear servicio de replay incremental;
- leer ventanas desde adaptadores existentes cuando sea posible;
- mantener cursor y watermark;
- persistir `StreamSessionSnapshot`;
- soportar pausa, reanudacion y cierre;
- generar artefactos por sesion en `codigo/reports/stream_sessions/`;
- exponer endpoints minimos read/write para iniciar y consultar sesiones.

No incluido:

- conectores MQTT/OPC-UA/Kafka reales;
- streaming en tiempo real estricto;
- descarga automatica de datasets grandes.

Criterio de cierre:

- una sesion replay produce ventanas y progreso;
- no llama agentes todavia salvo evento de inicio si se decide;
- no rompe `POST /runs`;
- tests unitarios de cursor, pausa y cierre.

### Hito 11.4 - Cola persistente y worker local

Objetivo: sustituir la fragilidad de jobs solo en memoria para procesos
industriales largos.

Alcance:

- crear cola persistente local;
- crear worker ejecutable por CLI;
- definir `job_type` permitidos;
- reintentos con limite;
- dead-letter para errores repetidos;
- heartbeat de worker;
- endpoints de consulta de cola;
- integracion inicial con `StreamSession`.

Compatibilidad:

- `api_run_jobs.py` no se elimina;
- las runs batch existentes pueden seguir usando jobs actuales hasta migracion
  controlada;
- el nuevo worker no duplica `pipeline_runner.py`.

Criterio de cierre:

- job `stream_replay_step` ejecutado por worker;
- reintento y dead-letter verificados;
- tests de idempotencia basica;
- documentacion de arranque local.

### Hito 11.5 - Scoring incremental y estado de salud continuo

Objetivo: calcular evidencia operacional de forma incremental sin ejecutar una
run completa por cada ventana.

Alcance:

- separar entrenamiento/carga de modelo e inferencia incremental;
- reutilizar artefactos de modelos existentes cuando sea posible;
- calcular score por ventana;
- actualizar Health Index y Risk Index;
- detectar picos, alertas sostenidas y criticidad;
- persistir series parciales compatibles con visualizacion;
- mantener refs citables para agentes.

Regla:

```text
La capa de scoring genera evidencia. No decide por si sola el cierre de un
incidente industrial.
```

Criterio de cierre:

- serie incremental visible en artefactos;
- tests con dataset pequeno;
- comparacion basica contra una run batch equivalente cuando sea posible.

### Hito 11.6 - Orquestacion agentica event-driven

Objetivo: hacer que los agentes intervengan ante eventos industriales
significativos.

Alcance:

- generar `IndustrialEvent` desde triggers;
- construir expediente compacto de evento;
- invocar agente adecuado segun `AutomationPolicy`;
- validar `AgenticEventReview`;
- persistir decision, evidencia, memoria y errores;
- exponer timeline de eventos agenticos;
- conectar fallbacks visibles y human review.

Expediente minimo para agente:

- contexto de activo y sesion;
- ventana o rango afectado;
- metricas temporales;
- estado de salud/riesgo;
- comparativa con umbrales;
- eventos previos relacionados;
- herramientas disponibles;
- memoria recuperada;
- opciones permitidas de accion.

Criterio de cierre:

- una alerta persistente activa al `evaluator`;
- un drift activa al `modeler`;
- las decisiones se validan por contrato;
- no hay texto libre como salida principal;
- la app muestra que la decision fue agentica.

### Hito 11.7 - Dataset no visto y protocolo cold-start

Objetivo: probar si el sistema razona con un dataset nuevo sin memoria
especifica previa.

Alcance:

- seleccionar dataset principal no visto, recomendado `XJTU-SY`;
- documentar licencia, estructura y limites;
- crear o adaptar descriptor/adaptador;
- congelar snapshot de memoria antes de la prueba;
- ejecutar baseline sin memoria especifica;
- ejecutar con memoria generica permitida;
- comparar decisiones, metricas, fallbacks y citas;
- generar post-mortem y memoria candidata solo al final.

Reglas:

- no indexar recuerdos de XJTU-SY antes del primer cold-start;
- declarar si se usan etiquetas proxy;
- no forzar aprobacion operacional si las metricas son malas;
- conservar errores como evidencia.

Criterio de cierre:

- informe cold-start;
- comparacion `memory_off` vs `memory_generic_on`;
- evidencia de agentes ante dataset no visto;
- memoria candidata en revision, no auto-indexada sin control.

### Hito 11.8 - Automatizacion de procesos industriales

Objetivo: definir procesos repetibles que conecten eventos, agentes, acciones
controladas y evidencia.

Automatizaciones candidatas:

- inicio de sesion -> preflight agentico si dataset es nuevo;
- alerta persistente -> revision `evaluator`;
- drift -> revision `modeler`;
- revision costosa -> `human_review`;
- fallo de worker -> incidente tecnico;
- cierre de sesion -> informe de sesion;
- memoria candidata -> curacion;
- cola bloqueada -> dead-letter y auditoria.

Acciones permitidas:

- crear evento;
- crear review agentica;
- pausar sesion;
- marcar incidente;
- solicitar revision humana;
- generar informe;
- proponer recalibracion;
- crear candidato de memoria;
- cerrar sesion.

Acciones no permitidas:

- ejecutar codigo generado por LLM;
- borrar artefactos;
- cambiar datasets raw;
- reentrenar modelos pesados sin contrato y confirmacion;
- ocultar errores.

Criterio de cierre:

- politicas versionadas;
- tests de decision de politicas;
- automatizacion visible en timeline;
- evidencia de acciones y responsables.

### Hito 11.9 - Cockpit industrial de streams, cola y eventos

Objetivo: extender el frontend para operar sesiones continuas sin saturar la
interfaz.

Alcance:

- vista o subvista de `Streams`;
- estado de sesiones activas;
- cola y workers;
- eventos recientes;
- incidentes abiertos;
- alertas agenticas;
- timeline stream + agentes;
- acceso a evidencia;
- enlace a visualizacion continua;
- mantener `Cockpit`, `Nueva run`, `Agentes`, `Visualizacion` y evidencia.

Regla visual:

```text
El usuario ve estado, cola, eventos y decision agentica en segundos.
La evidencia profunda se abre bajo demanda.
```

Criterio de cierre:

- build frontend correcto;
- desktop y movil sin overflow;
- la UI distingue telemetria determinista de decision agentica;
- no hay landing page ni textos explicativos largos.

### Hito 11.10 - Docker industrial local

Objetivo: llevar la industrializacion a un stack reproducible.

Servicios candidatos:

- backend FastAPI;
- frontend Nginx;
- worker local;
- Qdrant opcional;
- cola persistente local mediante volumen;
- Ollama externo documentado.

Reglas:

- no empaquetar datasets pesados en imagenes;
- mantener volumenes para datos, reports, modelos y experimentos;
- no descargar modelos durante build;
- perfiles Docker para servicios opcionales;
- smoke manual antes de cierre.

Criterio de cierre:

- `docker compose up --build` levanta backend/frontend;
- perfil worker levanta cola y worker;
- Qdrant opcional funciona si se activa;
- frontend alcanza backend por `/api`;
- stream replay pequeno funciona en Docker;
- decisiones agenticas funcionan si Ollama esta disponible.

### Hito 11.11 - Demo final y cierre academico

Objetivo: preparar la defensa final del sistema industrial agentico.

Demo candidata:

1. Levantar stack local.
2. Comprobar backend, frontend, worker, memoria y Ollama.
3. Abrir cockpit industrial.
4. Iniciar stream replay de dataset conocido.
5. Ver ventanas, cola, health/risk y eventos.
6. Provocar o alcanzar alerta persistente.
7. Ver decision agentica del `evaluator`.
8. Abrir evidencia, herramientas y memoria citada.
9. Cerrar sesion y generar informe.
10. Lanzar cold-start con dataset no visto.
11. Comparar memoria off/on generica.
12. Mostrar post-mortem, memoria candidata y limites.

Criterio de cierre:

- evidencia reproducible;
- screenshots o capturas Playwright;
- informe tecnico final;
- memoria academica actualizada;
- limitaciones declaradas;
- no se rompen runs batch ni frontend anterior.

## Verificacion por bloque

Para cambios de contratos:

```text
python -m unittest discover codigo/tests
```

Para cambios backend/servicios:

```text
python -m unittest discover codigo/tests
```

Para cambios frontend:

```text
cd codigo/frontend
npm run build
```

Para cambios visuales o 3D:

- revisar desktop y movil con Playwright;
- comprobar ausencia de errores de consola;
- comprobar ausencia de overflow horizontal;
- comprobar canvas no vacio si se toca Three.js.

Para streaming:

- sesion pequena de replay;
- pausa y reanudacion;
- cierre de sesion;
- cursor/watermark persistido;
- comparacion con artefactos esperados.

Para cola:

- job completado;
- reintento controlado;
- dead-letter;
- heartbeat;
- idempotencia.

Para agentes:

- decision validada por Pydantic;
- evidencia citada;
- memoria recuperada y uso declarado;
- fallback visible;
- human review cuando proceda.

Para Docker:

- backend healthy;
- frontend healthy;
- worker activo;
- proxy `/api`;
- stream replay pequeno;
- Ollama/Qdrant documentados.

## Metricas de exito

Metricas de sistema:

- latencia de ingesta;
- ventanas procesadas por minuto;
- profundidad de cola;
- tiempo medio de job;
- tasa de reintentos;
- eventos por sesion;
- eventos agenticos por sesion;
- tiempo evento -> decision agentica;
- fallbacks LLM;
- dead letters.

Metricas PHM:

- lead time persistente;
- falsa alarma nominal;
- onset confirmado;
- episodios de alerta;
- Health Index drop;
- monotonicidad;
- tendencia;
- criticidad sostenida.

Metricas agenticas:

- decisiones con refs citadas;
- herramientas usadas;
- memoria recuperada/usada/ignorada;
- uso invalido de memoria;
- guardrails activados;
- correcciones de contrato;
- decisiones con human review;
- informes verificados sin exageraciones.

Metricas cold-start:

- rendimiento sin memoria especifica;
- rendimiento con memoria generica;
- diferencias en decision del `modeler`;
- cautelas declaradas ante dataset nuevo;
- errores honestos;
- memoria candidata producida tras post-mortem.

## Fuera de alcance

No abordar en Fase 11 salvo decision explicita:

- cloud productivo;
- autenticacion multiusuario real;
- Kafka/Spark/Flink;
- OPC-UA/MQTT real contra hardware;
- SLURM/HPC;
- Redis/Celery obligatorio;
- RUL industrial validado;
- entrenamiento pesado automatico;
- fine-tuning de LLMs;
- agentes que escriben codigo;
- borrado automatico de artefactos;
- dashboards externos de observabilidad;
- empaquetar datasets grandes en Docker;
- prometer tiempo real duro.

## Riesgos y mitigaciones

### Riesgo: convertir la fase en pipeline determinista

Mitigacion: todo evento industrial relevante exige decision agentica, fallback
visible o human review. La capa determinista solo produce evidencia.

### Riesgo: demasiadas llamadas LLM

Mitigacion: triggers, cooldown, histeresis, prioridad, resumenes compactos y
llamadas solo ante decisiones.

### Riesgo: romper runs batch

Mitigacion: `POST /runs` queda intacto; streaming se anade como modo nuevo; las
runs batch se usan como regresion.

### Riesgo: cola demasiado compleja

Mitigacion: empezar con persistencia local simple. Redis/Celery solo si el
prototipo lo justifica.

### Riesgo: dataset nuevo retrasa todo

Mitigacion: usar XJTU-SY como objetivo principal y MIMII como extension
opcional. Si XJTU-SY requiere trabajo excesivo, documentar bloqueo y usar un
subconjunto local reproducible.

### Riesgo: frontend saturado

Mitigacion: vista compacta de streams/cola/eventos; evidencia profunda bajo
demanda; mantener la politica visual de Fase 10.

### Riesgo: automatizacion insegura

Mitigacion: acciones permitidas cerradas, contratos estrictos, human review y
sin ejecucion de codigo generado por agentes.

## Primer paso recomendado

Crear el hito documental de inventario:

```text
codigo/docs/129_fase11_hito1_inventario_industrializacion.md
```

Antes de escribir codigo:

```text
rg -n "job|queue|background|RunJob|worker|session|stream|event|watermark|automation|policy|trigger" codigo/app codigo/scripts codigo/tests codigo/docs
rg -n "TemporalRunSeries|health_index|risk_index|run_to_failure|visualization|compareRuns|AgentRuntimeEvent" codigo/app codigo/frontend/src codigo/tests codigo/docs
rg -n "Memory|memory|Qdrant|RetrievedMemory|DecisionEpisode|MemoryCandidate|human_review" codigo/app codigo/tests codigo/docs
rg --files codigo/app codigo/frontend/src codigo/scripts codigo/tests codigo/docs | sort
```

Despues del inventario, el primer bloque de codigo deberia ser pequeno y
vertical:

```text
Contratos StreamSession + IndustrialEvent + QueueJob
  -> tests de esquemas
  -> persistencia minima de StreamSession
  -> replay de una sesion pequena sin agentes
  -> primer trigger agentico controlado
```

La Fase 11 debe cerrar el TFM mostrando algo mas fuerte que una demo bonita:

```text
Un prototipo industrial continuo donde los agentes no procesan ruido, sino que
gobiernan decisiones trazables sobre evidencia operacional.
```
