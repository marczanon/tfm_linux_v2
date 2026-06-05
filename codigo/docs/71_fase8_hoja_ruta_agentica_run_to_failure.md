# Fase 8 - Hoja de ruta agentica run-to-failure

Fecha: 2026-06-03.

## Objetivo

La Fase 8 convierte `run_to_failure_degradation` en el centro agentico del TFM.
La Fase 7 ha preparado contratos, metricas temporales, visualizaciones,
comparacion y panel de control. La Fase 8 debe hacer que los agentes Qwen/LLM
sean quienes gobiernen de verdad este perfil: observan evidencia temporal,
formulan hipotesis, eligen configuraciones, piden herramientas, comparan
modelos, debaten resultados, recomiendan acciones y redactan conclusiones.

El objetivo no es que un LLM ejecute codigo libre ni que desaparezcan los
ejecutores deterministas. El objetivo es que cada run importante dependa de
decisiones agenticas estructuradas, trazables y verificables, con herramientas
deterministas como soporte.

## Cambio de paradigma

Hasta ahora:

```text
pipeline determinista -> agentes conscientes del perfil -> informe/verificacion
```

En Fase 8:

```text
agentes observan -> agentes planifican -> agentes seleccionan herramientas
-> ejecutores aplican decisiones -> agentes evaluan/debaten -> agentes recomiendan
```

La run ya no debe sentirse como una ejecucion determinista a la que se le anade
un comentario de Qwen al final. Debe sentirse como una investigacion agentica
controlada, donde los LLM tienen protagonismo dentro de contratos estrictos.

## Principios no negociables

- Qwen/Ollama es la linea principal de investigacion.
- Los agentes tienen poder real de eleccion, pero no ejecutan codigo arbitrario.
- Toda decision agentica pasa por contratos Pydantic o JSON estricto.
- Toda accion real la aplica un ejecutor determinista, testeable y trazable.
- Las herramientas son observaciones o simuladores controlados, no atajos para
  reescribir el pipeline.
- Los fallbacks deterministas existen, pero se etiquetan como fallback; no deben
  convertirse en la demostracion principal de la fase.
- El perfil temporal no se evalua por F1 como metrica principal.
- Las etiquetas proxy nunca se presentan como oficiales.
- RUL, histeresis y autoencoders se preparan como extensiones posteriores a la
  base agentica, no como sustitutos de ella.
- Cada hito tecnico actualiza documentacion y memoria academica en paralelo.

## Estado de partida

Ya existe:

- perfil `run_to_failure_degradation`;
- propagacion temporal hasta ventana y prediccion;
- metricas de degradacion;
- panel de control con salud/riesgo/estado;
- distincion entre primer pico, aviso sostenido y fallo historico de replay;
- comparacion run-to-failure;
- agentes conscientes del perfil;
- `evidence_lookup`;
- `report_writer`, `report_verifier` y debate controlado de informes;
- memoria agentica supervisada e infraestructura RAG ya construida en fases
  anteriores.

Falta:

- que el agente use el panel temporal como evidencia principal;
- que el modelador elija entre politicas temporales, modelos y criterios de
  alerta con herramientas especificas;
- que el evaluador debata si una deteccion temprana es defendible;
- que la run tenga una narrativa agentica de principio a fin;
- que haya post-mortem temporal y aprendizaje agentico por perfil;
- que el frontend muestre una recomendacion agentica operacional, no solo
  metricas.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Adaptar el perfil run-to-failure a una ejecucion agentica profunda, reutilizando
agentes, grafo, runner, herramientas, memoria, visualizacion y evaluacion
existentes.
```

Inventario revisado:

- `codigo/app/agents/modeler.py`;
- `codigo/app/agents/evaluator.py`;
- `codigo/app/agents/report_writer.py`;
- `codigo/app/agents/report_verifier.py`;
- `codigo/app/services/agent_tools.py`;
- `codigo/app/services/llm_agents.py`;
- `codigo/app/services/agent_memory.py`;
- `codigo/app/services/decision_memory.py`;
- `codigo/app/services/reasoning_audit.py`;
- `codigo/app/services/memory_usage_audit.py`;
- `codigo/app/services/run_visualization.py`;
- `codigo/app/services/run_registry.py`;
- `codigo/app/executors/modeling.py`;
- `codigo/app/executors/evaluation.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/frontend/src/App.tsx`;
- `codigo/docs/62_fase7_hito5_catalogo_herramientas_agenticas.md`;
- `codigo/docs/63_fase7_hito5_threshold_analysis_modeler_strategy.md`;
- `codigo/docs/69_fase7_cierre_base_run_to_failure.md`;
- `codigo/docs/70_fase7_hito9_panel_control_run_to_failure.md`.

Decision:

```text
extend
```

Motivo: ya existen agentes, grafo, herramientas, memoria y visualizacion. La
Fase 8 debe profundizar esas fronteras, no crear otra aplicacion ni un pipeline
paralelo.

## Arquitectura objetivo de Fase 8

### Agentes

Se mantiene el conjunto existente siempre que sea posible:

- `supervisor`: decide el plan de investigacion y el siguiente nodo.
- `cleaner`: conserva papel de calidad de senal y canal.
- `structurer`: elige ventanas, solape, features y granularidad temporal.
- `modeler`: elige familia de modelo, hiperparametros y politica de score.
- `evaluator`: juzga metricas temporales, falsos avisos, persistencia y
  degradacion.
- `report_writer`: redacta informe como analista industrial.
- `report_verifier`: audita afirmaciones no soportadas.

Posibles especializaciones sin crear agentes nuevos al inicio:

- `modeler` asume rol de estratega temporal cuando el perfil es
  `run_to_failure_degradation`;
- `evaluator` asume rol de auditor operacional;
- `report_writer` asume rol de analista de mantenimiento predictivo.

Solo se creara un agente nuevo si no hay propietario claro y se justifica por
frontera funcional.

### Herramientas

El catalogo de herramientas debe crecer alrededor de evidencia temporal:

- `temporal_health_lookup`: devuelve estado actual, primer pico, aviso
  sostenido, rachas, episodios, picos aislados, fallo historico y advertencias.
- `degradation_metrics_lookup`: devuelve metricas run-to-failure primarias y
  contexto de etiquetas.
- `model_comparison_lookup`: compara runs/modelos por metricas temporales.
- `threshold_analysis`: se conserva como diagnostico, pero no decide por si
  sola.
- `hysteresis_policy_simulator`: futura herramienta read-only para probar
  reglas de persistencia/histeresis sobre predicciones ya generadas.
- `rul_readiness_assessor`: futura herramienta para decidir si hay suficiente
  evidencia para intentar RUL experimental.
- `experiment_plan_lookup`: prepara candidatos de experimento que el agente
  puede aceptar, rechazar o modificar dentro de contrato.

### Contratos

La Fase 8 debe introducir contratos mas expresivos:

- `TemporalDiagnosisDecision`;
- `RunToFailureModelingStrategy`;
- `HealthPolicyDecision`;
- `AgentExperimentPlan`;
- `OperationalRecommendation`;
- `TemporalDebateRecord`;
- `RunToFailurePostMortem`.

Estos contratos deben contener:

- hipotesis;
- evidencia citada;
- herramienta usada;
- accion propuesta;
- configuracion ejecutable;
- riesgos;
- limitaciones;
- confianza;
- motivos para no usar RUL si no procede.

## Hitos propuestos

### Hito 8.1: evidence pack temporal para agentes

Estado: base implementada en
`72_fase8_hito1_evidence_pack_temporal_agentes.md`.

Objetivo:

- dar a Qwen un resumen compacto y util del perfil run-to-failure.

Implementar:

- resumen de salud temporal por run;
- primer pico vs aviso sostenido;
- episodios, racha maxima y picos aislados;
- metricas temporales principales;
- contexto de etiquetas proxy/oficiales;
- explicacion de PCA diagnostica;
- advertencias de RUL no soportado.

Criterio de aceptacion:

- `modeler`, `evaluator` y `report_writer` reciben evidencia temporal sin abrir
  CSVs completos ni depender de texto libre.
- `cleaner` recibe contexto temporal propio como puerta de calidad de senal,
  canal y continuidad de trayectoria.

### Hito 8.2: herramientas agenticas temporales

Estado: base implementada en
`73_fase8_hito2_herramientas_temporales_agenticas.md`.

Objetivo:

- ampliar el catalogo de herramientas para que los agentes puedan consultar el
  perfil temporal con precision.

Implementar:

- `temporal_health_lookup`;
- `degradation_metrics_lookup`;
- extension de `evidence_lookup` con refs temporales citables;
- tests de herramientas.

Criterio de aceptacion:

- un agente puede citar `temporal:first_persistent_alert`,
  `temporal:longest_alert_streak` o `metric:mean_lead_time_to_failure` y el
  verificador puede comprobar que existen.

### Hito 8.3: modeler como estratega run-to-failure

Estado: base implementada en
`74_fase8_hito3_modeler_estratega_run_to_failure.md`.

Objetivo:

- que el agente modelador decida la estrategia temporal, no solo el modelo.

Implementar:

- contrato `RunToFailureModelingStrategy`;
- decision entre PCA, Isolation Forest y One-Class SVM segun evidencia;
- alternativas comparables obligatorias;
- razonamiento sobre score, persistencia, falsas alarmas y tendencia;
- prohibicion explicita de optimizar F1 como objetivo principal;
- memoria recuperada especifica de run-to-failure.

Criterio de aceptacion:

- una run con Qwen puede elegir modelo y politica de alerta temporal, dejando
  alternativas y justificacion auditable.

### Hito 8.4: evaluador operacional y debate temporal

Estado: base implementada en
`75_fase8_hito4_evaluador_operacional_debate_temporal.md`.

Objetivo:

- que el evaluador no solo apruebe/rechace, sino que debata si la deteccion es
  operacionalmente defendible.

Implementar:

- criterios temporales de aprobacion agentica;
- debate controlado `modeler` / `evaluator` o `evaluator` / `verifier`;
- registro `TemporalDebateRecord`;
- bloqueo si se confunde pico aislado con fallo;
- bloqueo si se presenta RUL no calculado.

Criterio de aceptacion:

- una run puede quedar aprobada, aprobada con cautelas, pendiente de revision o
  rechazada por razones temporales explicitas.

### Hito 8.5: recomendacion agentica en frontend

Estado: implementado en `76_fase8_hito5_recomendacion_agentica_frontend.md`.

Objetivo:

- mostrar en el panel de control que dice el agente y por que.

Implementar:

- tarjeta de recomendacion operacional;
- evidencia citada por el agente;
- confianza;
- limitaciones;
- siguiente experimento recomendado;
- enlace al debate/informe.

Criterio de aceptacion:

- el usuario ve no solo `critico`, sino la interpretacion Qwen/LLM respaldada
  por evidencia.
- el panel distingue aprobacion, cautela, revision y bloqueo a partir de la
  decision persistida del `evaluator`, con contexto del `modeler`.

### Hito 8.6: post-mortem y memoria del perfil temporal

Estado: implementado en `77_fase8_hito6_postmortem_memoria_temporal.md`.

Objetivo:

- convertir errores y aciertos run-to-failure en memoria reutilizable.

Implementar:

- adaptar `DecisionEpisode` y `MemoryCandidate` al perfil temporal, en lugar
  de crear un post-mortem paralelo;
- episodios de decision para `modeler`, `structurer` y `evaluator`;
- revision humana opcional de razonamiento temporal;
- indexacion en memoria vectorial;
- auditoria de uso de memoria;
- deteccion de patrones repetidos: exceso de falsos positivos, picos aislados
  interpretados como fallo, abuso de F1 o RUL inventado.

Criterio de aceptacion:

- las runs con memoria activa generan candidato de memoria para `modeler` y
  `evaluator` con metricas temporales, herramientas, guardarrails y cautelas;
- una nueva run puede indexar esos candidatos y recuperarlos mediante los
  mecanismos RAG existentes, citando solo recuerdos recuperados.

### Eje paralelo: memoria RAG avanzada

Tras el hito 8.6 se abre una linea transversal documentada en
`78_fase8_hoja_ruta_memoria_rag_avanzada.md`. Su objetivo no es sustituir la
base agentica run-to-failure, sino hacer que la memoria sea visible, medible y
defendible:

- cockpit frontend para entender el ciclo candidato -> indexado -> recuperado
  -> usado -> auditado;
- trazabilidad de consultas RAG y recuerdos citados;
- uso de memoria en la primera decision del `modeler`, no solo en reintentos;
- evaluacion canonica de retrieval antes de introducir Qdrant, reranking o
  hybrid search;
- consolidacion/reflexion posterior para transformar episodios sueltos en
  conocimiento metodologico reutilizable.

Decision metodologica: el backend JSON local se mantiene como baseline
reproducible y auditable, mientras que Qdrant/Qwen reranking se tratan como
evolucion experimental. La memoria informa a Qwen, pero no sustituye su
decision ni convierte la run en una politica determinista cerrada.

Estado inicial: M1 se implementa en
`79_fase8_memoria_m1_cockpit_frontend.md`, convirtiendo la vista de memoria
persistida en un cockpit frontend sin cambiar todavia el backend RAG local.
M2 se implementa en `80_fase8_memoria_m2_observabilidad_retrieval.md`,
persistiendo consultas RAG, enriqueciendo eventos de retrieval y mostrando en
frontend backend, embeddings, scores y recuerdos usados o ignorados.
M3 se implementa en
`81_fase8_memoria_m3_modeler_transversal_gobierno.md`, llevando la memoria a la
decision inicial del `modeler` y anadiendo curacion manual de recuerdos desde
API/frontend. Aunque el primer uso fuerte se aplica al modelador, la decision
metodologica es transversal: cada agente conserva memoria propia y la memoria
compartida queda disponible como apoyo, siempre con citas de IDs recuperados y
sin convertir la run en una politica determinista cerrada. La curacion permite
excluir, restaurar o borrar recuerdos tras pruebas y prepara benchmarks con
memoria completa, filtrada o desactivada.
M4-pre se implementa en
`82_fase8_memoria_m4_pre_benchmark_efecto_memoria.md`, anadiendo un benchmark
offline que analiza snapshots persistidos para medir si la memoria fue
consultada, recuperada, citada, ignorada o usada de forma invalida. El primer
smoke real compara `cwru-memory-transversal-fase4-001` con
`cwru-memory-transversal-fase4-002-llm`: la memoria fue citada por
`structurer` y `evaluator`, sin cambiar metricas, por lo que se documenta un
efecto en deliberacion/trazabilidad pero no una mejora numerica.
M4.1 se implementa en
`83_fase8_memoria_m4_1_quality_gate_benchmark_controlado.md`: anade un quality
gate determinista que marca recuerdos como `pass`, `caution` o
`exclude_candidate`, y permite etiquetar variantes `memory_off`, `memory_full`,
`memory_filtered`, `memory_conflict_excluded` o `retrieval_only`. Por decision
metodologica no se introduce memoria consolidada en este punto, para no fijar
reflexiones que puedan coartar futuras decisiones de Qwen.
M4.2 se implementa en
`84_fase8_memoria_m4_2_qdrant_backend_opcional.md`: anade un backend
`QdrantVectorMemoryStore` compatible con el contrato `VectorMemoryStore` y una
fabrica `get_default_vector_memory_store(...)` para seleccionar `json` o
`qdrant` por entorno. JSON queda como baseline reproducible y Qdrant como via
experimental hacia RAG industrial, pendiente de migracion, smoke real y
comparativa de retrieval.
M4.3 se implementa en
`85_fase8_memoria_m4_3_migracion_qdrant_smoke.md`: anade migracion
`LocalJsonVectorMemoryStore -> Qdrant`, comparacion de retrieval con un espejo
local reembebido, servicio Docker opcional `memory-qdrant` y smoke real contra
Qdrant. La prueba migra 20 recuerdos a `evaluator_memory`, `modeler_memory` y
`structurer_memory`, con 3/3 queries coincidentes y solapamiento medio 1.0. El
siguiente paso es activar Qdrant dentro de una run agentica real, no solo como
indice migrado.
M4.4 se implementa en
`86_fase8_memoria_m4_4_run_qdrant_retrieval_smoke.md`: los runners usan ahora
`get_default_vector_memory_store(...)`, por lo que `TFM_MEMORY_BACKEND=qdrant`
activa Qdrant dentro del pipeline. La comprobacion CWRU
`cwru-memory-qdrant-m4-4-smoke-001` termina aprobada, persiste contextos de
memoria con `retrieval_backend=qdrant_vector_memory_store` y queda clasificada
como `retrieval_only` en el benchmark. Al ejecutarse sin LLM, no valida todavia
citas ni deliberacion Qwen; eso queda para M4.5.
M4.5 se implementa en
`88_fase8_memoria_m4_5_qwen_qdrant_citas_agenticas.md`: Qdrant se remigra con
`qwen3-embedding:0.6b`, el runner comun expone `--use-llm` y la run
`m4-5-qwen-qdrant-nasa-smoke-001` valida Qwen/LLM + Qdrant en
`run_to_failure_degradation`. El `modeler` recupera 3 recuerdos desde Qdrant,
los cita y declara uso alineado; la run queda no aprobada por FPR alto, lo que
se conserva como cautela metodologica.

### Hito 8.7: suite canonica agentica run-to-failure

Objetivo:

- demostrar que el perfil depende de decisiones agenticas y no de una unica
  politica fija.

Implementar:

- runs Qwen comparables sobre el mismo protocolo;
- al menos PCA, Isolation Forest y One-Class SVM;
- decisiones, herramientas, debate, informe y verificacion persistidos;
- comparacion final por metricas temporales;
- resumen de que decisiones agenticas mejoraron o empeoraron la run.

Criterio de aceptacion:

- existe una demo local donde Qwen decide, ejecuta mediante contratos, evalua,
  debate y genera memoria sobre run-to-failure.

## Siguientes extensiones despues de la base agentica

Cuando Fase 8 cierre la base agentica, el siguiente nivel podra abordar:

- histeresis avanzada y politicas de persistencia versionadas;
- RUL experimental;
- autoencoder denso;
- LSTM/temporal autoencoder;
- small multiples y cola de activos;
- datasets run-to-failure adicionales;
- industrializacion SaaS, streaming, usuarios e integraciones.

Estas mejoras no deben adelantarse hasta que los agentes tengan herramientas,
contratos, debate y memoria suficientes para protagonizar el perfil.

## Verificacion minima por hito

Cada hito debe incluir:

- tests de contratos Pydantic;
- tests de herramientas agenticas;
- tests de agentes con cliente LLM fake;
- una run o smoke local con Qwen cuando sea viable;
- build frontend si cambia UI;
- actualizacion de `codigo/docs/`;
- actualizacion de `memoria/capitulos/05_implementacion.tex`;
- si cambia la metodologia, actualizacion de
  `memoria/capitulos/04_metodologia.tex`.

## Criterio de cierre de Fase 8

La Fase 8 quedara cerrada cuando se pueda hacer esta demo:

1. Lanzar una run `run_to_failure_degradation` con `use_llm=true`.
2. Ver que Qwen consulta herramientas temporales.
3. Ver que Qwen elige modelo, estrategia y cautelas dentro de contrato.
4. Ejecutar el pipeline con ejecutores deterministas.
5. Ver debate o verificacion temporal entre agentes.
6. Ver recomendacion operacional en frontend.
7. Leer informe agentico con evidencia citada.
8. Guardar post-mortem y memoria reutilizable.
9. Comparar varias runs por decisiones agenticas y metricas temporales.

Si esto se cumple, el perfil run-to-failure quedara preparado para ampliar el
siguiente nivel: histeresis avanzada, RUL experimental, autoencoders y
validacion con mas datasets.
