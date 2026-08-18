# Documentacion tecnica

Esta carpeta recoge decisiones de diseno e implementacion de la aplicacion. La
memoria academica se mantiene separada en `memoria/`; aqui se documentan
contratos, rutas, artefactos y criterios tecnicos que deben guiar el codigo.

Documentos iniciales:

- `01_diseno_pipeline_datos.md`: diseno del flujo de datos para el MVP con
  CWRU Bearing Dataset y extension futura con NASA IMS.
- `02_diseno_state_langgraph.md`: contrato del estado global usado por el grafo
  y validado mediante Pydantic.
- `03_diseno_contratos_pydantic.md`: contratos Pydantic para datasets,
  decisiones de agentes y resultados de ejecutores.
- `04_ejecutor_manifest_cwru.md`: implementacion y verificacion del ejecutor
  determinista que genera `manifest.csv`.
- `05_ejecutor_profile_cwru.md`: implementacion y verificacion del perfilador
  determinista que genera `profile.json`.
- `06_ejecutor_limpieza_cwru.md`: implementacion y verificacion del ejecutor
  determinista que genera senales limpias.
- `07_ejecutor_estructuracion_cwru.md`: implementacion y verificacion del
  ejecutor que genera ventanas, features y particiones reproducibles.
- `08_ejecutor_modelado_cwru.md`: implementacion y verificacion del primer
  modelo base de deteccion de anomalias con Isolation Forest.
- `09_ejecutor_evaluacion_cwru.md`: implementacion y verificacion del ejecutor
  de metricas sobre predicciones.
- `10_adaptadores_entrada.md`: frontera ligera para leer distintos formatos de
  senal sin acoplar los ejecutores al tipo de fichero.
- `11_grafo_langgraph_minimo.md`: grafo LangGraph secuencial que encadena los
  ejecutores deterministas del MVP y prepara la entrada de agentes futuros.
- `12_supervisor_determinista.md`: primer nodo supervisor con decision
  `SupervisorDecision` validada por Pydantic, aun sin LLMs.
- `13_supervisor_llm.md`: capa LLM JSON para el supervisor, con cliente Ollama,
  validacion estricta y fallback determinista.
- `14_agente_limpiador_llm.md`: primer agente LLM especializado; genera
  `CleaningDecision` y delega la transformacion real en `cleaning.py`.
- `15_agente_estructurador_llm.md`: agente LLM que genera
  `StructuringDecision` y delega ventanas, features y splits en
  `structuring.py`.
- `16_agente_modelador_llm.md`: agente LLM que genera `ModelingDecision` y
  delega entrenamiento y prediccion en `modeling.py`, incluyendo comparacion
  agentica de modelos soportados.
- `17_agente_evaluador_llm.md`: agente LLM que genera `EvaluationDecision` a
  partir de metricas ya calculadas por `evaluation.py`.
- `18_agente_redactor_llm.md`: agente LLM que genera `ReportDecision` y
  delega la escritura del informe final en `reporting.py`.
- `19_estado_actual_mvp.md`: recopilacion del estado del MVP, capacidades
  actuales, artefactos, validaciones y siguiente paso recomendado.
- `20_hoja_ruta_fase_2.md`: hoja de ruta activa tras cerrar el MVP local;
  prioriza persistencia, trazabilidad, comparacion experimental y API minima,
  dejando SLURM para fases posteriores.
- `21_persistencia_local_runs.md`: implementacion del primer hito de Fase 2;
  guarda snapshots locales por `run_id` con estado final, decisiones,
  artefactos, metricas, evaluacion, resumen e indice.
- `22_pipeline_persistido.md`: wrapper `run_and_persist_cwru_pipeline(...)`
  que ejecuta el grafo CWRU y guarda automaticamente un snapshot local.
- `23_registro_consultable_runs.md`: servicio `run_registry.py` para listar,
  filtrar, cargar artefactos y comparar metricas entre ejecuciones persistidas.
- `24_protocolo_experimental_local.md`: servicio `experiment_protocol.py` para
  definir planes experimentales locales, ejecutar varios runs persistidos y
  generar una tabla comparativa reproducible.
- `25_api_minima_fastapi.md`: primera API FastAPI de consulta sobre runs
  persistidos, artefactos e informes.
- `26_hoja_ruta_fase_3.md`: hoja de ruta activa para ampliar el sistema hacia
  datasets mas complejos, mas modelos deterministas y agentes con mayor poder
  de decision bajo contratos estrictos.
- `27_diseno_soporte_multidataset.md`: diseno tecnico del soporte multi-dataset;
  define descriptor comun, manifiesto comun, registro de adaptadores,
  estrategia para CWRU/NASA IMS y pruebas minimas.
- `28_inspeccion_nasa_ims.md`: inspeccion local/documental del paquete NASA IMS;
  resume contenedores anidados, estructura por test, discrepancias observadas,
  requisitos de extraccion y consecuencias para la futura interfaz.
- `29_agentes_expertos_llm_locales.md`: criterio para hacer viables agentes
  expertos con LLM locales mediante expedientes de evidencia, opciones
  ejecutables, contratos estrictos, alternativas comparables propuestas por
  agentes y una extension futura de agente investigador controlado.
- `30_gestion_runs_fase_3.md`: politica ligera para conservar snapshots de
  runs, identificar evidencias canonicas y podar artefactos grandes
  regenerables sin perder trazabilidad experimental.
- `31_backlog_fase_4_memoria_agentica.md`: backlog para una futura memoria
  agentica supervisada con RAG, alimentada por post-mortems y revisiones
  humanas sin alterar metricas ni contratos de ejecucion.
- `32_hoja_ruta_fase_4.md`: hoja de ruta activa de Fase 4; define memoria
  agentica supervisada con embeddings y base vectorial por agente, modos
  conmutables de Human-in-the-loop y aprendizaje controlado de experiencias.
- `33_politica_temporal_nasa_ims.md`: politica temporal versionada para ejecutar
  NASA IMS con etiquetas proxy declaradas y sin presentarlas como oficiales.
- `34_api_ejecucion_controlada_fase4.md`: primera version de `POST /runs` con
  dry-run por defecto, raices permitidas, politica multi-dataset y ejecucion
  local controlada, incluyendo jobs locales en memoria para `background=true`.
- `35_protocolo_reutilizacion_anti_duplicacion.md`: protocolo transversal para
  buscar capacidades existentes antes de crear codigo, contratos, scripts,
  endpoints o tests nuevos.
- `36_hoja_ruta_fase_5_aplicacion.md`: hoja de ruta de Fase 5 para construir la
  aplicacion local backend/frontend, con seleccion o ingesta de datasets,
  ejecucion de runs, seguimiento de jobs, visualizacion de artefactos y memoria
  local.
- `37_frontend_local_fase5.md`: primer esqueleto frontend React/Vite para Fase
  5, conectado a `GET /health`, `GET /runs` y `POST /runs` con `dry_run=true`
  mediante la API FastAPI existente.
- `38_catalogo_datasets_fase5.md`: extension de FastAPI y frontend para listar
  adaptadores registrados, describir rutas raw permitidas y eliminar el catalogo
  local hardcodeado de la UI.
- `39_jobs_frontend_fase5.md`: conexion del frontend con `POST /runs`
  `background=true`, polling de `GET /run-jobs/{job_id}` y apertura del
  snapshot persistido al completar.
- `40_runs_detalle_fase5.md`: vista operativa de runs con filtros, detalle,
  metricas, informe Markdown, artefactos y comparacion basica usando endpoints
  de lectura existentes.
- `41_observabilidad_agentica_fase5.md`: primera capa de telemetria runtime
  para ver supervisor, agentes, memoria, ejecutores y eventos de job desde la
  nueva pestaña `Agentes` del frontend.
- `42_memoria_persistida_frontend_fase5.md`: endpoints read-only y vista
  frontend para consultar colecciones, recuerdos filtrables y detalle de
  `memory_record_id` desde la memoria agentica persistida.
- `43_human_review_ui_fase5.md`: controles de interfaz para mostrar razones de
  revision humana, recoger `human_approval` y respetar el bloqueo del modo
  `required` reutilizando los contratos existentes.
- `44_frontend_operativo_fase5.md`: cierre del frontend como dashboard local
  operativo, con vistas `Pipeline` y `Agentes` y banda fija de contexto de
  ejecucion.
- `45_visualizaciones_frontend_fase5.md`: ampliacion visual con traduccion
  legible de eventos agenticos, endpoint de visualizacion de runs, graficas de
  metricas y proyeccion PCA 2D con anomalias.
- `46_ollama_qwen_frontend_fase5.md`: activacion controlada de `use_llm=true`
  desde la aplicacion web, con `GET /llm/status`, modelo por defecto
  `qwen3.5:4b` y agentes Ollama reales en ejecuciones API.
- `47_rediseño_dashboard_frontend_fase5.md`: refactor UX/UI del frontend hacia
  un dashboard SaaS/MLOps local con shell, navegacion, paneles operativos y
  detalles tecnicos plegables sin cambiar contratos backend.
- `48_hoja_ruta_fase_6_dockerizacion.md`: hoja de ruta activa de Fase 6 para
  dockerizacion, reproducibilidad local, pruebas de humo y preparacion de demo
  final, manteniendo la metodologia de reutilizacion y contratos estrictos.
- `49_fase6_supuestos_entorno.md`: primer hito de Fase 6; fija inventario,
  puertos, variables de entorno, volumenes persistentes y decision de mantener
  Ollama externo al compose inicial.
- `50_fase6_configuracion_reproducible.md`: segundo hito de Fase 6; crea la
  plantilla de entorno de Docker, documenta `codigo/docker/` y hace configurable
  el proxy Vite de desarrollo sin cambiar el modo local.
- `51_fase6_imagen_backend.md`: tercer hito de Fase 6; define la imagen Docker
  backend FastAPI, `.dockerignore`, comandos de build/run y verificacion
  correcta de `GET /health`, adaptadores y estado LLM desde contenedor.
- `52_fase6_imagen_frontend.md`: cuarto hito de Fase 6; define la imagen Docker
  frontend con build React/Vite, Nginx, proxy `/api` hacia backend y
  verificacion de HTML, healthcheck y endpoints API a traves del contenedor.
- `53_fase6_compose_local.md`: quinto hito de Fase 6; crea el compose local
  backend/frontend, monta volumenes persistentes, mantiene Ollama externo y
  valida el stack con puertos alternativos para no interferir con el desarrollo
  local.
- `54_cierre_operativo_fase6.md`: cierre operativo de Fase 6 en el Hito 5; deja
  Docker como minimo reproducible backend/frontend y difiere smoke tests y demo
  final hasta el siguiente bloque de mejoras funcionales de la aplicacion.
- `55_recap_mejoras_fase7.md`: recap de capacidades actuales y propuestas para
  preparar Fase 7, separando mejoras imprescindibles de auditabilidad, mejoras
  importantes de producto e ideas agenticas avanzadas compatibles con la
  metodologia anti-duplicacion.
- `56_fase7_hito1_evidence_pack_reporte_agentico.md`: primer hito de Fase 7;
  extiende snapshots con evidence pack JSON/Markdown, persiste request y plan
  como artefactos de evidencia y permite que `report_writer` redacte contenido
  narrativo humano validado por contratos Pydantic.
- `57_fase7_hito1_frontend_informe_final.md`: integracion frontend del informe
  final como documento principal de cierre de run, con renderizado legible y
  evidencia tecnica separada debajo.
- `58_fase7_hito2_informe_auditoria_ejecucion.md`: segundo hito de Fase 7;
  genera y expone un informe determinista de auditoria de ejecucion separado
  del informe agentico final, con bloque propio en frontend.
- `59_fase7_hito3_verificador_agentico_informe.md`: tercer hito de Fase 7;
  introduce `report_verifier` para revisar afirmaciones no soportadas,
  exageraciones y limitaciones ausentes en el informe final, persistiendo JSON
  y Markdown de verificacion.
- `60_fase7_investigacion_debate_controlado_informe.md`: investigacion previa
  al debate controlado entre `report_writer` y `report_verifier`; define
  contratos candidatos, artefactos, encaje en grafo, auditoria y frontend antes
  de implementar.
- `61_fase7_hito4_debate_controlado_informe.md`: cuarto hito de Fase 7;
  implementa una ronda de debate controlado entre `report_writer` y
  `report_verifier`, persiste `report_debate.json`/`.md`, expone
  `/runs/{run_id}/report-debate` e incorpora una conversacion agentica limpia
  en la pestana de agentes.
- `62_fase7_hito5_catalogo_herramientas_agenticas.md`: inicio del quinto hito
  de Fase 7; crea contratos `AgentToolSpec`, `AgentToolRequest` y
  `AgentToolObservation`, un catalogo minimo de herramientas y la primera
  herramienta read-only `evidence_lookup`.
- `63_fase7_hito5_threshold_analysis_modeler_strategy.md`: segundo bloque del
  quinto hito; anade la herramienta read-only `threshold_analysis` y amplia
  `ModelingDecision` con una estrategia explicita para evitar decisiones
  centradas solo en `threshold_quantile`.
- `64_fase7_hito5_one_class_svm_modeler.md`: tercer bloque del quinto hito;
  implementa `one_class_svm` como familia no supervisada soportada por el
  ejecutor de modelado y lo incorpora al espacio de decision del `modeler`.
- `65_fase7_hito6_nasa_ims_visualizacion.md`: estabilizacion intermedia de
  NASA IMS; ajusta defaults de UI para politica temporal full y permite
  visualizacion PCA diagnostica cuando hay features pero no predicciones.
- `66_fase7_perfiles_supervision_binary_run_to_failure.md`: hoja de ruta para
  formalizar perfiles `binary_fault_classification` y
  `run_to_failure_degradation`, con contratos, metricas, visualizaciones y
  pasos de implementacion sin crear runners paralelos.
- `67_fase7_hito8_comparativa_run_to_failure.md`: primer bloque del panel de
  investigacion run-to-failure; extiende `GET /runs/compare` y el frontend para
  comparar runs por lead time, falsas alarmas nominales, tendencia del score y
  fallos perdidos, manteniendo F1 como metrica auxiliar.
- `68_fase7_hito8_monitorizacion_estado_salud.md`: segundo bloque del panel
  run-to-failure; extiende `temporal_series` con `health_index`, `risk_index` y
  `health_state` por ventana y por trayectoria para monitorizacion operacional.
- `69_fase7_cierre_base_run_to_failure.md`: checklist de cierre de la base del
  perfil principal `run_to_failure_degradation`, priorizando retoques frontend,
  cola de activos, comparacion visual de modelos, interpretacion agentica,
  politica de salud/RUL y validacion antes de pasar a industrializacion SaaS.
- `70_fase7_hito9_panel_control_run_to_failure.md`: implementacion del primer
  retoque de cierre del perfil; convierte `Visualizacion` en panel de control
  run-to-failure con metricas temporales primarias, estado de motor, tira de
  ventanas, bandas de estado y PCA como diagnostico secundario.
- `71_fase8_hoja_ruta_agentica_run_to_failure.md`: hoja de ruta de Fase 8 para
  convertir `run_to_failure_degradation` en el centro agentico del TFM,
  ampliando herramientas, contratos, debate, memoria, frontend e informes para
  que Qwen/LLM gobierne runs temporales dentro de guardarrailes estrictos.
- `72_fase8_hito1_evidence_pack_temporal_agentes.md`: implementacion del primer
  hito de Fase 8; extiende `evidence_lookup` con la seccion `temporal`, refs
  citables y contexto especifico para que `cleaner` participe en la base
  agentica run-to-failure.
- `73_fase8_hito2_herramientas_temporales_agenticas.md`: implementacion del
  segundo hito de Fase 8; anade `temporal_health_lookup` y
  `degradation_metrics_lookup` como herramientas read-only para que los agentes
  consulten salud temporal y metricas de degradacion con refs citables.
- `74_fase8_hito3_modeler_estratega_run_to_failure.md`: implementacion del
  tercer hito de Fase 8; extiende `ModelingDecisionStrategy` para que el
  `modeler` declare herramientas, objetivos, refs y politica de alerta cuando
  gobierna una run `run_to_failure_degradation`.
- `75_fase8_hito4_evaluador_operacional_debate_temporal.md`: implementacion
  del cuarto hito de Fase 8; extiende `EvaluationDecision` para que el
  `evaluator` audite defendibilidad operacional, debate temporal y guardarrails
  como RUL no estimado, picos aislados y etiquetas proxy.
- `76_fase8_hito5_recomendacion_agentica_frontend.md`: implementacion del
  quinto hito de Fase 8; extiende `GET /runs/{run_id}/visualization` y el
  frontend para mostrar recomendacion operacional agentica con confianza,
  evidencia, herramientas, cautelas, guardarrails y contexto del `modeler`.
- `77_fase8_hito6_postmortem_memoria_temporal.md`: implementacion del sexto
  hito de Fase 8; adapta `DecisionEpisode` y `MemoryCandidate` al perfil
  `run_to_failure_degradation`, genera memoria de `modeler` en el grafo y
  conserva metricas temporales, herramientas, guardarrails y cautelas en
  candidatos indexables.
- `78_fase8_hoja_ruta_memoria_rag_avanzada.md`: investigacion y hoja de ruta
  para llevar la memoria agentica a un nivel superior, aclarando el estado
  actual como RAG vectorial local con embeddings Qwen, sus limites frente a una
  base vectorial industrial y los hitos de cockpit, observabilidad, Qdrant,
  reranking, hybrid search, quality gate y consolidacion.
- `79_fase8_memoria_m1_cockpit_frontend.md`: implementacion del primer hito de
  memoria RAG avanzada; convierte la vista de memoria persistida en un cockpit
  frontend con ciclo de estados, distribuciones, runtime, registros citados y
  detalle enriquecido de cada recuerdo, sin cambiar el backend read-only.
- `80_fase8_memoria_m2_observabilidad_retrieval.md`: implementacion del segundo
  hito de memoria RAG avanzada; persiste `memory_query.json`, enriquece
  `retrieved_memory_context.json` como artefacto trazable, anade eventos runtime
  de consulta/retorno/uso/rechazo y muestra backend, embeddings, scores y
  recuerdos usados o ignorados en el cockpit frontend.
- `81_fase8_memoria_m3_modeler_transversal_gobierno.md`: implementacion del
  tercer hito de memoria RAG avanzada; lleva RAG a la decision inicial del
  `modeler`, mantiene el diseno como memoria multiagente y anade curacion
  manual de recuerdos desde API/frontend para excluir, restaurar o borrar
  memoria tras pruebas o antes de benchmarks.
- `82_fase8_memoria_m4_pre_benchmark_efecto_memoria.md`: implementacion del
  hito M4-pre de memoria RAG avanzada; anade un benchmark offline sobre
  snapshots persistidos para medir retrieval, citas, memoria ignorada, uso
  invalido y deltas frente a baseline, incluyendo un primer smoke real CWRU
  donde `structurer` y `evaluator` citan memoria sin cambio numerico de
  metricas.
- `83_fase8_memoria_m4_1_quality_gate_benchmark_controlado.md`: implementacion
  de M4.1; anade `memory_quality_gate.py`, clasifica recuerdos recuperados como
  `pass`, `caution` o `exclude_candidate`, extiende el benchmark con variantes
  controladas `memory_off/memory_full/memory_filtered` y deja fuera la memoria
  consolidada para no coartar futuras reflexiones agenticas.
- `84_fase8_memoria_m4_2_qdrant_backend_opcional.md`: implementacion de M4.2;
  anade `QdrantVectorMemoryStore`, mantiene JSON como baseline, incorpora
  `get_default_vector_memory_store(...)` para seleccionar backend por entorno y
  valida Qdrant con tests HTTP mockeados antes de un smoke real.
- `85_fase8_memoria_m4_3_migracion_qdrant_smoke.md`: implementacion de M4.3;
  anade servicio y CLI de migracion JSON -> Qdrant, profile Docker
  `memory-qdrant`, Query API de Qdrant con fallback y un smoke real que migra
  20 recuerdos con solapamiento de retrieval 1.0 frente al baseline reembebido.
- `86_fase8_memoria_m4_4_run_qdrant_retrieval_smoke.md`: comprobacion M4.4;
  adapta los runners para usar `get_default_vector_memory_store(...)`, ejecuta
  una run CWRU con `TFM_MEMORY_BACKEND=qdrant`, confirma artefactos con
  `retrieval_backend=qdrant_vector_memory_store` y clasifica la run como
  `retrieval_only` en el benchmark de efecto de memoria.
- `87_cierre_sesion_2026_06_03_recap_para_continuar.md`: handoff de cierre de
  sesion para retomar el 2026-06-04; resume la base run-to-failure, el avance
  de memoria RAG/Qdrant, el estado exacto de M4.4, documentos/artefactos clave y
  el siguiente paso M4.5 con Qwen/LLM + Qdrant.
- `88_fase8_memoria_m4_5_qwen_qdrant_citas_agenticas.md`: cierre de M4.5;
  remigra Qdrant con `qwen3-embedding:0.6b`, expone `--use-llm` en el runner
  comun, ejecuta `m4-5-qwen-qdrant-nasa-smoke-001` y valida que el `modeler`
  cita 3 recuerdos recuperados desde Qdrant sin uso invalido.
- `89_fase9_hoja_ruta_run_to_failure_maximo_nivel.md`: hoja de ruta de Fase 9
  para elevar `run_to_failure_degradation` con suite canonica agentica,
  politicas versionadas de salud/histeresis, Health Indicators avanzados,
  autoencoder PyTorch denso, readiness, RUL experimental con incertidumbre,
  visualizacion PHM y memoria metodologica.
- `90_fase9_hito1_suite_canonica_run_to_failure.md`: implementacion del primer
  hito de Fase 9; extiende `experiment_protocol.py` para definir y materializar
  una suite run-to-failure PCA/Isolation Forest/One-Class SVM con el runner
  comun, tabla temporal y planes derivados de `ModelingDecision`.
- `91_fase9_hito2_politica_temporal_evaluacion_run_to_failure.md`:
  implementacion del segundo hito de Fase 9; introduce politica temporal
  versionada `temporal_health_policy_v1`, onset confirmado, lead time
  persistente, refs citables para agentes y comparacion de runs centrada en
  degradacion sostenida en lugar de primer pico aislado.
- `92_fase9_hito3_health_indicator_avanzado.md`: implementacion del tercer
  hito de Fase 9; introduce `health_indicator_policy_v1`, Health Index bruto y
  suavizado causal, metricas de caida, monotonicidad, robustez, volatilidad
  nominal, refs `health:*` para agentes y columnas `HI drop`/`HI mono` en la
  suite run-to-failure.
- `93_fase9_hito5_readiness_modelos_temporales_avanzados.md`: implementacion
  del hito de readiness previo al autoencoder; anade
  `temporal_model_readiness_assessor`, politica `temporal_model_readiness_v1`,
  refs `readiness:*` y precondiciones para que los agentes puedan proponer
  autoencoder/RUL solo con evidencia suficiente.
- `94_fase9_hito4_autoencoder_pytorch_denso.md`: implementacion del autoencoder
  PyTorch denso; anade `autoencoder_dense` al ejecutor de modelado, valida
  hiperparametros cerrados, guarda `.pt`, scaler y curva de entrenamiento, y
  obliga al `modeler` a citar readiness antes de proponerlo.
- `95_cierre_fase9_run_to_failure_maximo_nivel.md`: cierre operativo de Fase 9;
  declara `run_to_failure_degradation` como caso PHM agentico local defendible,
  resume suite, politicas temporales, Health Indicator, readiness, autoencoder
  PyTorch, hardening de fallbacks visibles, evidencias de smoke y alcance fuera
  de fase.
- `96_fase10_hoja_ruta_frontend_cockpit_visual.md`: hoja de ruta de Fase 10
  para elevar el frontend a cockpit visual industrial, reestructurando la app
  React/Vite existente sin romper contratos, con panel principal claro,
  pestana `Agentes` profunda, sala de visualizacion 2D/3D y verificacion
  incremental por hitos.
- `97_fase10_hito1_inventario_frontend_mapa_componentes.md`: implementacion
  documental del primer hito de Fase 10; inventaria `App.tsx`, `api.ts`,
  `types.ts` y `styles.css`, fija propietarios, riesgos, estructura objetivo y
  orden de extraccion incremental antes de cambiar codigo frontend.
- `98_fase10_hito2a_shell_common_frontend.md`: primer subhito de Hito 10.2;
  extrae componentes `common` y `shell` desde `App.tsx`, crea `types/ui.ts` y
  `lib/labels.ts`, conserva estilos, APIs y comportamiento, y valida el
  frontend con `npm run build`.
- `99_fase10_hito2b_modularizacion_runs_reports_visualizacion.md`: segundo
  subhito de Hito 10.2; mueve detalle de run, paneles de informes, render
  Markdown y visualizacion 2D/run-to-failure a modulos de dominio, extrae
  helpers de formato y reduce `App.tsx` sin cambiar estilos ni contratos.
- `100_fase10_hito2c_modularizacion_agentes_memoria_constantes.md`: tercer
  subhito de Hito 10.2; separa constantes de dataset/pipeline, extrae la vista
  de agentes, el cockpit de memoria y helpers de runtime/labels, reduciendo
  `App.tsx` y manteniendo APIs, estilos y comportamiento.
- `101_fase10_hito2d_modularizacion_pipeline_runs_jobs.md`: cuarto subhito de
  Hito 10.2; extrae pipeline, preflight, jobs, historico de runs, comparacion,
  contexto de ejecucion y helpers de request/comparacion, dejando `App.tsx`
  como orquestador preparado para introducir `CockpitView`.
- `102_fase10_hito3a_cockpit_operacional_inicial.md`: primer subhito de Hito
  10.3; crea la vista `Cockpit` como entrada por defecto, con señales
  compactas de API/LLM/dataset/job, run foco, salud temporal, recomendacion
  agentica persistida e historial corto, reutilizando estado existente sin
  cambiar contratos backend.
- `103_fase10_hito3b_cockpit_run_foco_autocargada.md`: segundo subhito de Hito
  10.3; reutiliza `loadRunDetail(...)` para autocargar de forma controlada la
  ultima run foco en `Cockpit`, añade estados de carga y accesos directos a
  visualizacion, agentes e informe sin crear flujos paralelos.
- `104_fase10_hito3c_cockpit_pulido_evidencia.md`: tercer subhito de Hito
  10.3; pule el cockpit con una tarjeta compacta de evidencia para informe,
  auditoria, debate y artefactos, aclarando estados `listo`/`sin datos` sin
  añadir texto largo ni endpoints nuevos.
- `105_fase10_hito4a_nueva_run_launcher_operativo.md`: primer subhito de Hito
  10.4; reorganiza `Nueva run` como launcher operativo por pasos
  `Dataset`/`Ejecucion`/`Agentes`/`Preflight`, dejando opciones tecnicas
  plegadas en avanzado sin modificar contratos backend.
- `106_fase10_hito5a_agentes_runtime_investigativo.md`: primer subhito de
  Hito 10.5; reorganiza la pestaña `Agentes` como runtime investigativo con
  señales reales, mapa de agentes, detalle, memoria, timeline de eventos y
  conversacion derivada de eventos persistidos.
- `107_fase10_hito5b_detalle_agente_decision_memoria_payload.md`: segundo
  subhito de Hito 10.5; reorganiza el detalle de cada agente separando tarjeta
  de decision, señales/herramientas, memoria citada y payload tecnico plegado,
  sin inventar herramientas ni fallbacks.
- `108_fase10_hito5c_memoria_agentes_retrieval.md`: tercer subhito de Hito
  10.5; refuerza el cockpit de memoria dentro de `Agentes`, separando
  recuperados/usados/ignorados/excluidos, mostrando `memory_record_uses` y
  senales observables de retrieval sin cambiar backend ni contratos.
- `109_fase10_hito6a_visualizacion_2d_temporal_hi.md`: primer subhito de Hito
  10.6; refuerza `Visualizacion` con grafica secundaria de Health Index y rail
  de episodios de alerta/critico, reutilizando `TemporalRunSeries` sin cambiar
  backend ni contratos.
- `110_fase10_hito6b_comparacion_visual_runs_modelos.md`: segundo subhito de
  Hito 10.6; añade comparacion visual de runs/modelos dentro de
  `Visualizacion`, reutilizando `RunComparison`, `compareRuns(...)` y el estado
  existente del frontend sin cambiar backend ni contratos.
- `111_fase10_cierre_hito6_visualizacion_2d_avanzada.md`: cierre del Hito
  10.6; consolida la sala 2D avanzada con Health Index, episodios de alerta,
  comparacion visual y verificacion de build/proxy/endpoints con runs reales
  persistidas.
- `112_fase10_hito7a_sala_3d_base_threejs.md`: primer subhito de Hito 10.7;
  introduce una escena Three.js industrial aislada y opcional en
  `Visualizacion`, con selector `2D`/`3D`, fallback WebGL y carga diferida para
  no penalizar la sala 2D.
- `113_fase10_hito7b_mapeo_temporal_3d.md`: segundo subhito de Hito 10.7;
  conecta la escena 3D con puntos reales de `TemporalRunSeries`, barras por
  ventana coloreadas por `health_state`, altura por riesgo y marcadores de
  primer pico, aviso sostenido y fallo historico.
- `114_fase10_hito7c_interaccion_3d_ligera.md`: tercer subhito de Hito 10.7;
  añade interaccion ligera con `THREE.Raycaster`, hover, seleccion fijada y
  ficha compacta de barras/marcadores 3D sin nuevos contratos.
- `115_fase10_hito7d_cierre_sala_3d_industrial.md`: cierre de Hito 10.7;
  añade enfoque rapido de marcadores 3D, fallback de serie temporal vacia y
  consolida la sala 3D como capa opcional de inspeccion industrial, validada
  con Playwright headless, screenshots desktop/movil y analisis de pixeles.
- `116_fase10_hito8_oficina_3d_agentes_plan.md`: plan de retomada para Hito
  10.8; define la oficina 3D de agentes dentro de `Agentes`, basada en eventos
  reales, con subhitos 10.8A-D, componentes previstos, reglas de alcance y
  verificacion Playwright.
- `117_fase10_hito8a_oficina_3d_agentes_base.md`: primer subhito de Hito
  10.8; implementa una oficina 3D opcional dentro de `Agentes`, con boton
  `2D`/`3D`, carga diferida, fallback WebGL, modelo derivado de eventos runtime
  y validacion Playwright desktop/movil.
- `118_fase10_hito8b_oficina_3d_runtime_senales.md`: segundo subhito de Hito
  10.8; refuerza la oficina 3D con senales reales de actividad, memoria,
  herramientas, errores y debate cuando hay `AgentRuntimeEvent`, y muestra un
  aviso honesto de snapshot persistido cuando no hay job vivo.
- `119_fase10_hito8c_oficina_3d_interaccion_foco.md`: tercer subhito de Hito
  10.8; anade foco de camara por agente, botones compactos de seleccion,
  hover mas visible y responsive movil contenido para la oficina 3D.
- `120_fase10_hito9_identidad_visual_industrial_plan.md`: plan operativo del
  Hito 10.9; define la identidad visual industrial de la aplicacion, la
  politica de reduccion de texto visible, la paleta, el lenguaje de componentes
  y los subhitos 10.9A-F para rediseñar shell, cockpit y pestañas sin tocar
  backend ni eliminar trazabilidad.
- `121_fase10_hito9a_tokens_shell_industrial.md`: primer subhito de Hito
  10.9; implementa tokens CSS industriales, sidebar oscuro con marca
  `Agentic Control`, navegacion compacta, cabecera operacional y paneles/base
  visual con acento industrial, validado con build y Playwright desktop/movil.
- `122_fase10_hito9b_cockpit_baja_lectura.md`: segundo subhito de Hito
  10.9; rediseña `CockpitView` como command deck industrial de baja lectura,
  con señales compactas, medidor HI/riesgo, readiness por chips y accion
  agentica resumida, validado con build y Playwright desktop/movil.
- `123_fase10_hito9c_reduccion_textual_pestanas.md`: tercer subhito de Hito
  10.9; aplica la politica de texto minimo a `Nueva run`, `Visualizacion`,
  `Agentes` y runs, plegando descriptor, politica, rationale, memoria,
  informes, debate y evidencia sin perder trazabilidad; ademas compacta el
  contexto superior, pliega el registro de runs, deja memoria agentica como
  bloque provisional plegado y estructura `Visualizacion` por secciones
  internas, validado con build y Playwright desktop/movil.
- `124_fase10_hito9d_memoria_agentica_visual.md`: cuarto subhito de Hito
  10.9; implementa la subpestaña visual de memoria dentro de `Agentes`, con
  selector de agentes tipo personajes, avatar/rol/color, herramientas como
  chips, recuerdos humanos concisos y memoria tecnica bajo demanda, sin tocar
  backend ni contratos.
- `125_fase10_hito9e_metricas_visualizacion_subpantalla.md`: primer subpaso de
  Hito 10.9E; mueve `Metricas` a una subpantalla interna de `Visualizacion`,
  elimina el panel fijo de metricas de la primera lectura y queda validado con
  run real, sin tocar backend ni contratos.
- `126_fase10_hito9f_qa_visual_global.md`: cierre del Hito 10.9; valida
  coherencia visual global con Playwright desktop/movil, backend local, runs
  persistidas, ausencia de errores/overflow y build frontend correcto.
- `127_fase10_hito10_informe_evidencia_artefactos.md`: implementacion del Hito
  10.10; crea un centro de evidencia reutilizable para informe, auditoria,
  debate, evidence pack y artefactos, visible desde `Nueva run`, reutilizado en
  el registro de runs y enlazado desde `Agentes`, sin tocar backend.
- `128_fase11_hoja_ruta_industrializacion_agentica_event_driven.md`: propuesta
  historica amplia de Fase 11 para streaming simulado, cola persistente, worker,
  automatizacion y datasets no vistos. Su alcance queda diferido; la guia
  activa y acotada es `133_fase11_reenfoque_hibrido_nasa_replay_agentico.md`.
- `129_decision_backend_y_ciclo_memoria_rag_run_to_failure.md`: decision
  tecnica sobre backend vectorial, calidad del corpus y orden de validacion del
  ciclo RAG para el caso run-to-failure.
- `130_auditoria_base_agentes_pre_memoria.md`: auditoria transversal que
  separa exito operativo y exito agentico, cuantifica la evidencia historica,
  revisa los siete roles y fija la puerta `decision-only` previa a comparar
  ejecuciones con y sin memoria, ejecutable de forma segura con
  `python -m codigo.scripts.run_agent_decision_reliability --plan-only`.
- `131_fase10_sala_control_agentica_historia_visual.md`: reorganiza la vista
  `Agentes` como una historia visual progresiva, con siete roles compactos,
  ficha `Cree-Elige-Recuerda-Ocurre`, microflujo RAG, recorrido temporal
  sincronizado y auditoria completa bajo demanda, sin cambiar backend.
- `132_fase10_qa_e2e_playwright_agent_story.md`: versiona la infraestructura
  Playwright para validar la historia agentica en Chromium desktop y movil,
  define aislamiento completo de backend, Ollama y Qwen mediante fixtures API,
  congela los escenarios RAG sin actividad, `1/1`, filtrado `1/0` y no
  disponible, y cierra el gate con 16 casos correctos en escritorio y movil.
- `133_fase11_reenfoque_hibrido_nasa_replay_agentico.md`: hoja de ruta activa
  para convertir NASA IMS en una monitorizacion continua simulada mediante
  replay causal, con scoring determinista, triggers periodicos/event-driven,
  runs multiagente hijas, politicas versionadas y sala 2D/3D; separa el
  benchmark congelado de una demo adaptativa exploratoria y difiere la
  industrializacion amplia de `128`.
- `134_fase11_vertical_replay_manual_visual.md`: cierre del primer vertical P0
  de la Fase 11; documenta el replay historico manual de NASA IMS Set 2, su
  frontera causal y hashes congelados, los contratos y la API, la nueva vista
  2D y la paridad full NASA, sin atribuirle tiempo real, holdout, Qwen, RAG ni
  triggers todavia.
- `135_fase11_motor_triggers_p3_determinista.md`: cierra el motor backend P3
  sobre el replay congelado, con K/R, critical, gap, cooldown, coalescing,
  presupuesto, cierre y co-commit atomico de tick y triggers; documenta el
  ledger real de NASA Set 2 sin activar Qwen, RAG ni runs hijas.
- `136_fase11_conexion_trigger_run_multiagente.md`: cierra el puente manual
  desde un trigger emitido a una run hija consultable, con vista causal por
  whitelist, ledger de lifecycle separado, siete roles propose-only, memoria
  OFF, hashes extremo a extremo y navegacion Monitorizacion--Agentes, sin
  ejecutores ni aplicacion de politica.
- `137_fase11_gate_repetido_qwen_triggers_nasa.md`: cierra la bateria repetida
  `3 x 4 x 7` sobre todos los triggers primarios P3 con Qwen 3.5, memoria OFF,
  prerregistro, traza de 86 llamadas fisicas, publicacion hasheada, agregado
  visual y figura reproducible. Documenta v2 bloqueada por tres claims fuera de
  alcance y v3 bloqueada por dos fallbacks de referencias; no autoriza RAG ni
  adaptacion.
- `138_fase11_refuerzo_binding_evidencia_monitoring_review.md`: refuerza, sin
  ejecutar otro gate, la frontera que bloqueo V3. El LLM usa el alias cerrado
  `causal_view`, el backend lo materializa como referencia canonica y el handoff
  de registros queda ligado por hash, whitelist y cutoff; conserva V2/V3 como
  resultados inmutables y no atribuye seleccion semantica a un catalogo
  singleton.
- `139_fase11_catalogo_evidencia_causal_por_registro.md`: sustituye para nuevas
  runs el binding singleton por un catalogo sellado `E01..EN`; separa alcance
  causal, seleccion del agente y referencias canonicas por registro, integra
  fingerprints, traza y persistencia sin reescribir V3, y deja un gate
  prospectivo completo como validacion futura.
- `140_fase11_policy_proposal_consultiva.md`: proyecta las siete decisiones de
  una revision hija en una `MonitoringPolicyProposal` consultiva creada por el
  servidor, conserva cada contribucion y su evidencia, distingue unanimidad,
  desacuerdo e invalidez y declara siempre `not_applied`; no ejecuta Qwen, no
  inventa parametros ni implementa validacion, aprobacion o aplicacion de
  politicas.
- `141_fase11_campana_monitorizacion_agentiva_56h.md`: prepara una campaña P3
  histórica acelerada con pre-roll `0..352` y ventana agentiva `353..688`
  (55 h 50 min de tiempo NASA), cuatro hijas, 28 decisiones y cuatro propuestas
  consultivas esperadas; añade pacing, heartbeat, prerregistro, publicación y
  veredictos operativo/agentivo separados. La campaña oficial sigue pendiente;
  solo se ha cerrado un smoke diagnóstico separado sobre el primer trigger.
- `142_fase11_cinematica_monitorizacion_y_export_evidencia.md`: cierra una
  lectura 2D causal para no especialistas, polling incremental, storyboard de
  cuatro actos por siete roles y un exportador post-hoc de timeline, PNG y
  WebM; deja prerregistrada la receta visual sin modificar las fuentes selladas
  ni ejecutar la campaña.
