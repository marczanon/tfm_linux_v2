# Fase 8 - Hoja de ruta para memoria RAG agentica avanzada

Fecha: 2026-06-03.

## Objetivo

Llevar el sistema de memoria del TFM a un nivel superior: mas intuitivo en
frontend, mas medible, mas gobernado por agentes y mas cercano a practicas
actuales de RAG/agent memory, manteniendo la metodologia del proyecto:

- agentes Qwen/LLM con protagonismo real;
- contratos Pydantic/JSON estrictos;
- ejecutores y stores deterministas;
- trazabilidad de decisiones, recuperaciones, citas y auditorias;
- separacion limpia entre memoria academica, codigo y artefactos.

## Respuesta directa sobre el estado actual

El sistema actual si implementa una memoria RAG estructurada. Al inicio de esta
hoja de ruta no usaba aun una base de datos vectorial externa tipo Qdrant,
Weaviate, Chroma, Milvus o pgvector. Tras M4.2, Qdrant queda implementado como
backend opcional, aunque `LocalJsonVectorMemoryStore` sigue siendo el baseline
por defecto y falta una validacion end-to-end con servidor Qdrant real.

Estado actual:

- contratos:
  - `DecisionEpisode`;
  - `MemoryCandidate`;
  - `ReasoningMemoryRecord`;
  - `AgentMemoryQuery`;
  - `RetrievedMemoryContext`;
- colecciones por agente:
  - `cleaner_memory`;
  - `structurer_memory`;
  - `modeler_memory`;
  - `evaluator_memory`;
  - `report_writer_memory`;
  - `shared_methodology_memory`;
- backend actual:
  - `LocalJsonVectorMemoryStore`;
  - persiste colecciones como JSON;
  - calcula similitud coseno localmente;
  - soporta filtro por agente, dataset, rol de memoria y reutilizacion;
  - `QdrantVectorMemoryStore` desde M4.2 como opcion experimental compatible
    con el mismo contrato `VectorMemoryStore`;
  - `get_default_vector_memory_store(...)` para seleccionar `json` o `qdrant`
    por variables de entorno;
- embeddings:
  - por defecto `OllamaEmbeddingProvider`;
  - modelo por defecto `qwen3-embedding:0.6b`;
  - llama a Ollama `/api/embed`;
  - fallback/reproducibilidad: `LocalHashEmbeddingModel`;
- frontend actual:
  - consulta colecciones y recuerdos;
  - permite ver registros, pero todavia no explica bien el ciclo
    candidato -> indexado -> recuperado -> usado -> auditado.

Conclusion: es una memoria vectorial funcional y auditable, con embeddings Qwen
si Ollama esta disponible. Desde M4.2 ya existe una puerta de entrada a Qdrant,
pero el sistema no aprovecha todavia tecnicas avanzadas como hybrid search,
reranking, consolidacion, retrieval grading avanzado o comparativas sistematicas
JSON frente a Qdrant.

## Fuentes y patrones estudiados

### Agent memory como write-manage-read loop

La literatura reciente formaliza la memoria de agentes como un ciclo de
escritura, gestion y lectura acoplado a percepcion/accion. La taxonomia util
para este TFM separa:

- memoria episodica: que paso, que decision se tomo, que resultado hubo;
- memoria semantica: hechos o conocimiento estable;
- memoria procedimental: instrucciones, politicas y habilidades;
- politica de control: cuando escribir, consolidar, olvidar o recuperar.

Fuente:

- `Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers`
  - https://arxiv.org/abs/2603.07670

Aplicacion al TFM:

- nuestra memoria ya es principalmente episodica;
- falta distinguir con claridad memoria procedimental/metodologica;
- falta una politica de control explicita: promocion, consolidacion, caducidad,
  conflictos y uso obligatorio/opcional.

### Generative Agents: memoria, reflexion y planificacion

Generative Agents propone almacenar experiencias, sintetizarlas en reflexiones
de nivel superior y recuperarlas dinamicamente para planificar. El patron clave
no es solo guardar recuerdos, sino consolidarlos y convertirlos en reflexiones
accionables.

Fuente:

- `Generative Agents: Interactive Simulacra of Human Behavior`
  - https://arxiv.org/abs/2304.03442

Aplicacion al TFM:

- nuestros `DecisionEpisode` son buenos recuerdos episodicos;
- falta generar `ReflectionSummary` o memoria consolidada por perfil:
  "en run-to-failure, PCA dio lead time pero no RUL", "no aprobar por F1",
  "los picos aislados generan falsos positivos";
- esas reflexiones deberian alimentar `modeler` y `evaluator`.

### MemGPT: memoria jerarquica y contexto virtual

MemGPT plantea gestion jerarquica de memoria para superar la ventana de
contexto, moviendo informacion entre niveles rapidos/lentos. La idea aplicable
es separar memoria caliente, memoria recuperada y memoria fria/indexada.

Fuente:

- `MemGPT: Towards LLMs as Operating Systems`
  - https://arxiv.org/abs/2310.08560

Aplicacion al TFM:

- memoria caliente: decisiones y evidencia de la run actual;
- memoria recuperada: top-k insertado en prompt;
- memoria fria: colecciones vectoriales completas;
- memoria consolidada: lecciones de alto nivel por perfil/agente.

### LangGraph/Deep Agents: memoria persistente por alcance

Las guias de LangChain/Deep Agents separan memoria corta y larga, memoria
episodica/semantica/procedimental, alcance por agente/usuario/organizacion y
consolidacion en background.

Fuente:

- `Deep Agents Memory`
  - https://docs.langchain.com/oss/python/deepagents/memory

Aplicacion al TFM:

- nuestro alcance natural no es usuario, sino agente, perfil, dataset y activo;
- conviene crear vistas:
  - memoria del agente;
  - memoria compartida metodologica;
  - memoria del perfil `run_to_failure_degradation`;
  - memoria del activo/run si se amplia a SaaS industrial.

### Embeddings y reranking Qwen

Qwen3 Embedding/Reranker ofrece modelos de embedding y reranking de 0.6B, 4B y
8B, con soporte multilingue, contexto largo e instrucciones de busqueda. En el
TFM encaja especialmente porque mantiene la linea de investigacion con modelos
Qwen locales.

Fuentes:

- `Qwen/Qwen3-Embedding-8B` model card
  - https://huggingface.co/Qwen/Qwen3-Embedding-8B
- `Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models`
  - https://arxiv.org/abs/2506.05176

Aplicacion al TFM:

- mantener `qwen3-embedding:0.6b` como baseline local ligero;
- evaluar `Qwen3-Embedding-4B` si la maquina/servidor lo permite;
- anadir reranking Qwen para ordenar top-k despues de recuperacion inicial;
- usar prompts/instrucciones de embedding especificas para consultas de memoria
  industrial, si el backend elegido lo soporta.

### Hybrid search y bases vectoriales

Los sistemas actuales de RAG suelen combinar:

- busqueda densa por embeddings;
- busqueda sparse/keyword tipo BM25;
- fusion de rankings;
- filtros por metadatos;
- reranking final.

Qdrant soporta consultas hibridas y fusion `rrf`/`dbsf`; Weaviate documenta
hybrid search con vector + BM25 y estrategias de fusion.

Fuentes:

- Qdrant hybrid queries:
  - https://qdrant.tech/documentation/concepts/hybrid-queries/
- Weaviate hybrid search:
  - https://docs.weaviate.io/weaviate/concepts/search/hybrid-search

Aplicacion al TFM:

- `LocalJsonVectorMemoryStore` debe quedarse como baseline reproducible;
- Qdrant es el candidato mas natural para el siguiente backend local/Docker:
  - colecciones por agente;
  - payload filters por dataset/perfil/rol/veredicto;
  - busqueda densa;
  - posible sparse/hybrid;
  - facil de levantar en Docker Compose;
- hybrid search importa porque nuestros recuerdos tienen tokens criticos:
  `rul_not_estimated`, `proxy_labels`, `pca_reconstruction_error`,
  `mean_lead_time_to_failure`, `isolated_spike_not_failure`.

### Self-RAG y CRAG: recuperar solo si aporta, evaluar lo recuperado

Self-RAG critica el uso indiscriminado de un top-k fijo y propone recuperar de
forma adaptativa y reflexionar sobre la evidencia. CRAG anade un evaluador de
retrieval para decidir si el contexto recuperado es bueno o si debe corregirse.

Fuentes:

- `Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection`
  - https://arxiv.org/abs/2310.11511
- `Corrective Retrieval Augmented Generation`
  - https://arxiv.org/abs/2401.15884

Aplicacion al TFM:

- no siempre se debe inyectar memoria;
- cada agente debe declarar:
  - si recupero memoria;
  - si la uso;
  - que recuerdo influyo;
  - que riesgo mitigó;
  - por que algun recuerdo recuperado no era aplicable;
- añadir `retrieval_quality_score` antes de permitir que un recuerdo condicione
  una decision.

### Evaluacion RAG

RAGAS separa dimensiones de evaluacion: relevancia/foco del contexto, uso fiel
del contexto y calidad de generacion. Aunque el TFM no es QA general, este
marco sirve para evaluar memoria agentica:

- precision@k de recuerdos recuperados;
- recall@k de recuerdos esperados en casos controlados;
- citation faithfulness: el agente cita solo recuerdos recuperados;
- memory influence consistency: el efecto declarado coincide con el contenido;
- negative memory compliance: no repite una decision marcada como warning.

Fuente:

- `Ragas: Automated Evaluation of Retrieval Augmented Generation`
  - https://arxiv.org/abs/2309.15217

Aplicacion al TFM:

- crear una suite de evaluacion de memoria separada de metricas de deteccion;
- medir retrieval, uso, auditoria, latencia y coste local de Qwen embeddings.

### GraphRAG y memoria relacional

GraphRAG diferencia busqueda local, global y DRIFT Search sobre indices con
entidades/comunidades. Para este TFM no es prioridad inicial, pero es relevante
para el futuro SaaS industrial: activos, runs, fallos, decisiones, modelos y
guardarrails son entidades conectadas.

Fuente:

- Microsoft GraphRAG query overview:
  - https://microsoft.github.io/graphrag/query/overview/

Aplicacion al TFM:

- fase posterior: grafo de memoria industrial;
- nodos: agente, run, activo, modelo, politica, fallo, memoria, decision;
- consultas globales: "que politicas temporales fallan mas en NASA IMS",
  "que modelos generan mas falsas alarmas nominales".

## Diagnostico del sistema actual

Fortalezas:

- contratos fuertes y auditables;
- memoria por agente;
- roles de memoria (`positive_example`, `warning`, `boundary_case`, etc.);
- exclusion/reutilizacion controlada;
- Qwen embeddings via Ollama ya contemplado;
- fallback determinista para tests;
- API de colecciones y registros;
- auditoria de uso de memoria en reintentos;
- reciente incorporacion de memoria temporal run-to-failure.

Debilidades:

- frontend poco intuitivo:
  - no muestra ciclo de vida de memoria;
  - no diferencia bien candidato, indexado, recuperado, usado y auditado;
  - no permite entender por que un recuerdo afecto a una decision;
- no hay base vectorial externa:
  - JSON local esta bien para TFM/reproducibilidad;
  - no escala ni permite hybrid search real;
- no hay reranking;
- no hay evaluador de calidad de retrieval;
- `modeler` en decision inicial aun no recupera memoria normal;
- no hay consolidacion/reflexion de recuerdos;
- no hay forgetting/decay ni resolucion de contradicciones;
- no hay benchmark canonico de memoria;
- no hay vista por perfil/activo/fallo;
- la memoria no esta todavia conectada a una UI estilo "control center".

## Principios de rediseño

1. No sustituir agentes por memoria determinista.
   La memoria debe informar a Qwen, no convertir la run en reglas fijas.

2. La memoria no aprueba decisiones.
   Solo aporta evidencia; la decision sigue siendo del agente y se valida por
   contrato.

3. Todo recuerdo debe tener estado.
   Candidato, revisado, indexado, recuperado, usado, auditado, excluido,
   consolidado.

4. Todo uso debe ser citable.
   El agente solo puede citar `memory_record_id` realmente recuperados.

5. La UI debe explicar el ciclo.
   El usuario debe ver que memoria existe, por que se recupero y como influyo.

6. Baseline reproducible antes de industrializacion.
   Mantener `LocalJsonVectorMemoryStore` como baseline y comparar contra Qdrant.

7. Qwen como linea principal.
   Embeddings/reranking con Qwen cuando sea viable; fallback local solo para
   tests/reproducibilidad.

## Hoja de ruta propuesta

### Hito M1: mapa y cockpit de memoria en frontend

Estado 2026-06-03: primera version implementada en
`79_fase8_memoria_m1_cockpit_frontend.md`.

Objetivo:

- convertir la memoria en una vista intuitiva y operable.

Implementar:

- panel "Memoria" como cockpit:
  - colecciones por agente;
  - contadores por rol;
  - reutilizables/excluidos;
  - recuerdos recientes;
  - recuerdos usados en la run seleccionada;
  - recuerdos candidatos pendientes;
  - recuerdos consolidados;
- timeline de una run:
  - candidato generado;
  - indexacion;
  - recuperacion;
  - decision que lo uso;
  - auditoria posterior;
- detalle visual:
  - summary;
  - content;
  - metrics;
  - tags;
  - when_to_reuse;
  - when_not_to_reuse;
  - risk_if_misused.

Criterio de aceptacion:

- una persona puede abrir una run y entender que recuerdos existian, cuales se
  recuperaron, cuales se usaron y si el uso fue correcto.

### Hito M2: observabilidad de retrieval

Estado 2026-06-03: primera version implementada en
`80_fase8_memoria_m2_observabilidad_retrieval.md`.

Objetivo:

- hacer auditable cada consulta RAG.

Implementar:

- persistir `memory_query.json`;
- persistir `retrieved_memory_context.json`;
- mostrar top-k con:
  - similitud;
  - rol;
  - fuente;
  - dataset/perfil;
  - razon de filtrado;
  - embedding model;
  - backend;
- evento runtime especifico:
  - retrieval_requested;
  - retrieval_returned;
  - retrieval_used;
  - retrieval_rejected_by_agent;
- enlazar en frontend decision <-> recuerdos.

Criterio de aceptacion:

- toda decision con memoria puede reconstruirse desde UI y snapshot sin abrir
  ficheros manualmente.

### Hito M3: RAG inicial para `modeler`

Estado 2026-06-03: primera version implementada en
`81_fase8_memoria_m3_modeler_transversal_gobierno.md`.

Objetivo:

- que el `modeler` use memoria no solo en reintentos, sino en su primera
  decision de modelo/politica.

Implementar:

- `build_modeler_memory_query`;
- `retrieve_modeler_memory_context`;
- ampliar `ModelingDecision` con:
  - `memory_context_id`;
  - `used_memory_context`;
  - `memory_record_ids`;
  - `memory_usage_summary`;
  - `memory_record_uses`;
- prompt Qwen:
  - recuerdos de modelo;
  - warnings;
  - politicas temporales previas;
  - ejemplos de `run_to_failure_degradation`;
- validacion:
  - no puede citar memoria no recuperada;
  - warning/boundary requiere mitigacion de riesgo.

Criterio de aceptacion:

- una run nueva puede elegir PCA/OCSVM/IF o politica de alerta citando memoria
  temporal previa.
- la memoria se mantiene como capacidad transversal: `modeler_memory` es el
  primer caso fuerte, pero el cockpit, el store, la API y las colecciones por
  agente soportan tambien `cleaner`, `structurer`, `evaluator`,
  `report_writer`, `researcher` y `shared_methodology`.
- los recuerdos pueden excluirse, restaurarse o borrarse desde API/frontend
  para preparar benchmarks con memoria filtrada o limpiar pruebas no deseadas.

Decision metodologica:

- Qwen/LLM conserva protagonismo: la memoria informa la decision, pero el
  agente debe declarar si la uso, que IDs uso y como mitigo riesgos de casos
  frontera o advertencias.
- La curacion manual es el primer nivel de gobierno. La exclusion automatica se
  aplaza hasta tener criterios medibles de benchmark y calidad de retrieval.

### Hito M4-pre: benchmark de efecto de memoria

Estado 2026-06-03: primera version implementada en
`82_fase8_memoria_m4_pre_benchmark_efecto_memoria.md`.

Objetivo:

- responder de forma auditable si la memoria esta haciendo algo.

Implementar:

- evaluacion offline sobre snapshots persistidos;
- lectura de `{agent}_retrieved_memory_context`;
- contraste de recuerdos recuperados, citados e ignorados;
- deteccion de citas inventadas o declaraciones incompletas;
- comparacion opcional frente a `baseline_run_id`;
- informe JSON/Markdown con modo de memoria por run y por agente.

Criterio de aceptacion:

- se puede distinguir entre memoria no observada, retrieval sin uso, memoria
  usada de forma valida y memoria usada de forma invalida;
- se pueden documentar deltas de configuracion y metricas frente a baseline sin
  afirmar causalidad automaticamente;
- existe al menos un smoke real que demuestre el mecanismo.

Primer resultado:

- `cwru-memory-transversal-fase4-002-llm` recupera y cita memoria de
  `structurer` y `evaluator`;
- no hay uso invalido;
- las metricas frente a `cwru-memory-transversal-fase4-001` no cambian;
- conclusion: la memoria aporta deliberacion/trazabilidad en ese par, no mejora
  numerica demostrada.

### Hito M4.1: quality gate y benchmark controlado

Estado 2026-06-03: primera version implementada en
`83_fase8_memoria_m4_1_quality_gate_benchmark_controlado.md`.

Objetivo:

- evaluar la calidad de cada recuerdo recuperado sin consolidar memoria ni
  limitar futuras reflexiones de los agentes.

Implementar:

- `memory_quality_gate.py`;
- recomendacion por recuerdo:
  - `pass`;
  - `caution`;
  - `exclude_candidate`;
- razones de cautela o exclusion candidata:
  - baja similitud;
  - dataset/perfil incompatible;
  - warning o caso frontera;
  - veredicto parcial;
  - tags de exclusion manual o contaminacion de benchmark;
- etiquetas de variante controlada en `benchmark_memory_effect`:
  - `memory_off`;
  - `memory_full`;
  - `memory_filtered`;
  - `memory_conflict_excluded`;
  - `retrieval_only`.

Criterio de aceptacion:

- el informe de benchmark muestra por agente cuantos recuerdos pasan el gate,
  cuantos entran con cautela y cuantos son candidatos a exclusion;
- el gate no borra, no consolida y no sustituye la decision Qwen;
- el smoke CWRU memory off/full queda etiquetado como benchmark controlado y
  muestra cero advertencias del quality gate.

### Hito M4: backend vectorial Qdrant como opcion avanzada

Objetivo:

- pasar de JSON local a una base vectorial real sin perder reproducibilidad.

Implementar:

- interfaz actual `VectorMemoryStore` se mantiene;
- nuevo `QdrantVectorMemoryStore`;
- colecciones por agente;
- payload:
  - `target_agent`;
  - `dataset`;
  - `supervision_profile`;
  - `memory_role`;
  - `human_verdict`;
  - `reusable_as_context`;
  - `exclude_from_context`;
  - `source_type`;
  - `run_id`;
  - `decision_id`;
  - `tags`;
- Docker Compose opcional con Qdrant;
- script de migracion JSON -> Qdrant;
- tests con Qdrant opcionales o mockeados.

Criterio de aceptacion:

- el mismo codigo de agentes funciona con `LocalJsonVectorMemoryStore` y con
  `QdrantVectorMemoryStore`.

Estado 2026-06-03:

- M4.2 implementa `QdrantVectorMemoryStore`;
- `get_default_vector_memory_store(...)` selecciona backend por entorno con
  `TFM_MEMORY_BACKEND=json|qdrant`;
- los tests mockean Qdrant y validan upsert, query, scroll, delete y seleccion
  de backend;
- M4.3 implementa migracion JSON -> Qdrant, script operativo, servicio Docker
  opcional y smoke real contra `http://127.0.0.1:6333`;
- el smoke migra 20 recuerdos a `evaluator_memory`, `modeler_memory` y
  `structurer_memory`, con 3/3 queries de verificacion y solapamiento medio
  1.0 cuando JSON y Qdrant usan el mismo embedding;
- M4.4 adapta los runners para usar `get_default_vector_memory_store(...)` y
  ejecuta una run CWRU con `TFM_MEMORY_BACKEND=qdrant`, confirmando artefactos
  con `retrieval_backend=qdrant_vector_memory_store`;
- el benchmark clasifica esa run como `retrieval_only`: Qdrant recupera memoria
  sin uso invalido, pero al no usar LLM no hay citas agenticas;
- M4.5 remigra Qdrant con `qwen3-embedding:0.6b`, expone `--use-llm` en el
  runner comun y ejecuta `m4-5-qwen-qdrant-nasa-smoke-001` sobre
  `run_to_failure_degradation`;
- el benchmark clasifica M4.5 como `memory_used`: el `modeler` recupera 3
  recuerdos desde `qdrant_vector_memory_store`, los cita y declara uso sin uso
  invalido, aunque la run queda no aprobada por falsas alarmas altas.

### Hito M5: Qwen embeddings y reranking

Objetivo:

- usar Qwen embeddings/reranking de forma medida, no solo declarativa.

Implementar:

- matriz de embeddings:
  - `local_hash_embedding` para tests;
  - `qwen3-embedding:0.6b` baseline local;
  - `qwen3-embedding:4b` opcional;
- normalizar instrucciones de embedding:
  - query instruction;
  - document instruction;
  - idioma español/ingles tecnico;
- nuevo `QwenRerankerProvider`;
- pipeline:
  - retrieve top-20;
  - rerank top-5;
  - inyectar top-3;
- registrar:
  - embedding model;
  - dimension;
  - reranker model;
  - latencia;
  - memoria recuperada antes/despues de rerank.

Criterio de aceptacion:

- comparativa reproducible: hash vs Qwen 0.6B vs Qwen 4B vs reranking.

### Hito M6: hybrid search y filtros industriales

Objetivo:

- combinar semantica con coincidencias exactas y metadatos.

Implementar:

- BM25/sparse local o Qdrant hybrid si esta disponible;
- fusion RRF o DBSF;
- filtros estrictos antes de ranking:
  - agente;
  - perfil;
  - dataset;
  - rol de memoria;
  - veredicto;
- boosting por tags criticos:
  - `rul_not_estimated`;
  - `proxy_labels_not_official`;
  - `isolated_spike_not_failure`;
  - `mean_lead_time_to_failure`;
  - `false_alarm_rate_nominal`;
- registrar explicacion de ranking.

Criterio de aceptacion:

- consultas con tokens tecnicos recuperan recuerdos exactos aunque la similitud
  semantica no sea perfecta.

### Hito M7: retrieval quality gate estilo CRAG/Self-RAG

Objetivo:

- impedir que malos recuerdos condicionen decisiones.

Implementar:

- `MemoryRetrievalAssessment`;
- evaluador ligero de contexto recuperado:
  - relevant;
  - weak;
  - contradictory;
  - unsafe;
  - not_applicable;
- acciones:
  - use;
  - ignore;
  - rewrite_query;
  - lower_confidence;
  - require_human_review;
- agente debe declarar por que ignora recuerdos recuperados;
- auditoria posterior comprueba consistencia.

Criterio de aceptacion:

- el sistema puede recuperar memoria y decidir no usarla de forma trazable.

### Hito M8: consolidacion/reflexion de memoria

Objetivo:

- pasar de recuerdos sueltos a conocimiento reutilizable.

Implementar:

- `MemoryConsolidationRecord`;
- consolidacion por:
  - agente;
  - perfil;
  - dataset;
  - modelo;
  - fallo/guardrail;
- agente consolidador Qwen:
  - lee episodios recientes;
  - agrupa duplicados;
  - detecta contradicciones;
  - crea reflexiones de alto nivel;
- modo determinista inicial:
  - consolidacion por reglas y tags;
- memoria consolidada como `shared_methodology_memory` o
  `run_to_failure_profile_memory`.

Criterio de aceptacion:

- tras varias runs, el sistema puede recuperar una reflexion general, no solo
  episodios aislados.

### Hito M9: evaluacion canonica de memoria

Objetivo:

- medir si la memoria mejora o perjudica a los agentes.

Implementar:

- benchmark fijo de consultas:
  - recuperar warning de RUL;
  - recuperar politica de aviso sostenido;
  - recuperar caso de falsas alarmas nominales;
  - recuperar PCA como score temporal;
  - no recuperar memoria de otro perfil incompatible;
- metricas:
  - hit@k;
  - MRR;
  - recall@k;
  - precision@k por rol;
  - citation faithfulness;
  - memory influence consistency;
  - latency;
  - token budget;
  - decision delta con/sin memoria;
- informe en frontend:
  - comparativa stores/modelos;
  - recuerdos utiles vs dañinos;
  - mejoras por agente.

Criterio de aceptacion:

- se puede defender experimentalmente si la memoria ayuda al TFM.

### Hito M10: memoria relacional y GraphRAG industrial

Objetivo:

- preparar el salto a SaaS industrial sin adelantar industrializacion completa.

Implementar:

- grafo de relaciones:
  - run -> decision -> memory -> model -> asset -> fault mode;
  - memory -> contradicts/supports -> memory;
  - asset -> has_profile -> run_to_failure;
- consultas globales:
  - que decisiones se repiten;
  - que modelos generan mas falsas alarmas;
  - que guardarrails se violan mas;
- vista frontend:
  - grafo de memoria;
  - comunidades por fallo/modelo/politica;
  - resumen global de aprendizaje.

Criterio de aceptacion:

- la memoria deja de ser una lista de recuerdos y pasa a ser una base de
  conocimiento investigable.

## Orden recomendado

Orden practico para no perder foco:

1. M1 cockpit frontend de memoria.
2. M2 observabilidad de retrieval.
3. M3 RAG inicial para `modeler`.
4. M4-pre benchmark de efecto de memoria.
5. M4.1 quality gate y benchmark controlado.
6. M4.2 Qdrant opcional.
7. M4.3 migracion y smoke Qdrant real.
8. M4.4 run de retrieval real con backend Qdrant.
9. M4.5 run Qwen/LLM con backend Qdrant. Completado en
   `88_fase8_memoria_m4_5_qwen_qdrant_citas_agenticas.md`.
10. M5 Qwen reranking.
11. M6 hybrid search.
12. M7 retrieval quality gate avanzado.
13. M8 consolidacion/reflexion, aplazado por decision metodologica.
14. M9 benchmark canonico ampliado.
15. M10 GraphRAG industrial.

Motivo: primero hay que ver y medir la memoria. Despues se mejora el backend.
Si se introduce Qdrant/hybrid/reranking antes de tener cockpit y benchmark, el
sistema parecera mas avanzado pero seguira siendo dificil de defender.

## Primer paso logico

El primer paso recomendado es M1:

```text
Construir un cockpit de memoria en frontend que muestre el ciclo completo:
candidato -> indexado -> recuperado -> usado -> auditado.
```

Razon:

- la memoria ya existe;
- el usuario ya detecta que no es intuitiva;
- antes de optimizar embeddings o bases vectoriales hay que entender que esta
  pasando;
- el cockpit servira tambien para evaluar Qdrant, reranking y consolidacion.

## Preguntas de investigacion para la memoria del TFM

- Los agentes Qwen locales toman mejores decisiones con memoria que sin
  memoria?
- Que tipo de recuerdos ayudan mas: positivos, warnings, boundary cases o
  metodologia compartida?
- Qwen embeddings 0.6B son suficientes para memoria industrial tecnica?
- Un reranker Qwen mejora la recuperacion con pocos recuerdos?
- La memoria causa "experience-following" peligroso, repitiendo decisiones
  pasadas aunque el contexto haya cambiado?
- Como afecta la memoria a latencia local?
- Puede un agente explicar correctamente como uso un recuerdo?
- Cuantos recuerdos son demasiados para Qwen local?

## Decision metodologica

La memoria debe pasar a ser un eje central de la Fase 8, pero siempre como
herramienta agentica:

- los agentes recuperan recuerdos;
- los agentes declaran uso;
- los agentes justifican influencia;
- los ejecutores persisten, indexan y auditan;
- la UI hace visible el ciclo;
- la memoria nunca sustituye la decision Qwen/LLM.
