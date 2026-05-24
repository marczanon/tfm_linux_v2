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
  delega entrenamiento y prediccion en `modeling.py`.
- `17_agente_evaluador_llm.md`: agente LLM que genera `EvaluationDecision` a
  partir de metricas ya calculadas por `evaluation.py`.
- `18_agente_redactor_llm.md`: agente LLM que genera `ReportDecision` y
  delega la escritura del informe final en `reporting.py`.
- `19_estado_actual_mvp.md`: recopilacion del estado del MVP, capacidades
  actuales, artefactos, validaciones y siguiente paso recomendado.
- `20_hoja_ruta_fase_2.md`: hoja de ruta activa tras cerrar el MVP local;
  prioriza persistencia, trazabilidad, comparacion experimental y API minima,
  dejando SLURM para fases posteriores.
