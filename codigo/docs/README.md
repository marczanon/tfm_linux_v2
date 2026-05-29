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
- `36_hoja_ruta_fase_5_aplicacion.md`: hoja de ruta activa para construir la
  aplicacion local backend/frontend, con seleccion o ingesta de datasets,
  ejecucion de runs, seguimiento de jobs, visualizacion de artefactos y memoria
  local.
