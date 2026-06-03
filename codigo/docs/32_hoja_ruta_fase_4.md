# Hoja de ruta Fase 4

Fecha de inicio propuesta: 2026-05-27.
Fecha de cierre operativo: 2026-05-29.

## Nombre de la fase

Fase 4: Memoria agentica supervisada y aprendizaje controlado de experiencias.

## Punto de partida

La Fase 3 deja cerrada una base multiagente local defendible:

- CWRU funciona como benchmark de regresion;
- NASA IMS entra mediante contratos comunes, adaptadores, perfilado y
  diagnosticos sin forzar metricas supervisadas no defendibles;
- los agentes Qwen locales toman decisiones a partir de expedientes expertos;
- el estructurador y el modelador pueden proponer alternativas comparables;
- existe un benchmark NASA sintetico con metricas no perfectas;
- el modelador puede reintentar de forma acotada tras analizar errores;
- el razonamiento de los agentes queda auditado mediante post-mortems;
- existe una plantilla de revision humana, pero todavia no una memoria
  agentica reutilizable.

La Fase 4 debe convertir esa evidencia acumulada en memoria operacional para
los agentes, sin caer en fine-tuning prematuro ni en reglas hardcodeadas.

## Cierre operativo

La Fase 4 queda cerrada como fase de infraestructura agentica supervisada. Sus
resultados principales son:

- memoria vectorial local por agente;
- indexacion de post-mortems, revisiones y episodios de decision;
- recuperacion RAG para modelador, estructurador y evaluador;
- auditoria de uso de memoria;
- runner comun multi-dataset;
- politica temporal NASA IMS versionada;
- `POST /runs` controlado;
- jobs API locales en memoria;
- Human Review inicial `off/passive/required`;
- protocolo anti-duplicacion obligatorio.

La guia operativa activa pasa a ser:

```text
codigo/docs/36_hoja_ruta_fase_5_aplicacion.md
```

Esta hoja queda como referencia historica y tecnica de la Fase 4. Las nuevas
decisiones de aplicacion, backend/frontend e interfaz deben documentarse en la
hoja de ruta de Fase 5.

## Objetivo de la Fase 4

Construir una memoria agentica supervisada basada en embeddings, bases
vectoriales locales y revisiones humanas opcionales, para que los agentes
puedan recuperar experiencias anteriores relevantes antes de decidir.

El objetivo no es que la memoria ejecute, apruebe o modifique resultados. El
objetivo es que aporte contexto trazable:

- que se intento antes;
- que metricas produjo;
- que razonamiento declaro el agente;
- que veredicto humano recibio, si existe;
- que patrones deben reutilizarse, tratarse con cautela o evitarse.

## Definicion operativa de RAG en este proyecto

En Fase 4, RAG no significa solo leer ficheros Markdown o buscar texto con
coincidencias literales. RAG significa:

```text
documentos / post-mortems / revisiones humanas
-> fragmentacion controlada
-> embeddings locales versionados
-> base vectorial local
-> retrieval por agente y contexto de decision
-> contexto compacto citado
-> decision JSON/Pydantic del agente
```

Cada agente podra tener su propia memoria vectorial o coleccion:

- `cleaner_memory`;
- `structurer_memory`;
- `modeler_memory`;
- `evaluator_memory`;
- `report_writer_memory`;
- `researcher_memory`, si se incorpora el agente investigador;
- `shared_methodology_memory` para conocimiento comun validado.

La separacion por agente es importante: un caso util para el modelador no tiene
por que ser adecuado para el limpiador. El retrieval debe respetar el rol del
agente, el tipo de decision y el dataset.

## Principios de diseno

- La memoria recupera contexto, no ejecuta acciones.
- La memoria no puede cambiar metricas ni aprobar una run.
- La memoria no puede saltarse contratos Pydantic ni validaciones de ejecutor.
- Los embeddings deben generarse localmente por defecto.
- Cada embedding debe registrar modelo, version, fecha, texto de origen y hash
  del documento.
- Cada fragmento recuperado debe citar `run_id`, artefacto, tipo de veredicto y
  metricas principales cuando existan.
- La memoria debe distinguir ejemplos positivos, negativos, parciales,
  inseguros y casos que requieren mas evidencia.
- Los tests automatizados deben poder ejecutarse con Human-in-the-loop apagado.
- La redaccion academica debe actualizarse en paralelo a cada hito canonico.
- Antes de implementar una pieza nueva debe hacerse inventario previo de codigo,
  contratos, scripts, tests y documentacion existentes.

## Protocolo anti-duplicacion

A partir de este punto de Fase 4, ninguna ampliacion tecnica debe empezar
creando codigo directamente. Primero se aplicara el protocolo descrito en:

```text
codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md
```

La regla operativa es:

```text
buscar -> identificar propietario canonico -> reutilizar/adaptar/extender -> crear solo si no existe frontera adecuada
```

Esto afecta especialmente a API, runners, contratos Pydantic, Human Review,
memoria RAG y scripts de ejecucion. Si una pieza historica tiene un nombre
especifico, por ejemplo CWRU, no se crea automaticamente otra paralela: primero
se evalua si debe mantenerse como wrapper especifico, si conviene generalizarla
o si ya existe una capa comun como `pipeline_runner.py`.

## Human-in-the-loop conmutable

Human-in-the-loop sera un modo opcional, no una obligacion permanente del
pipeline. La aplicacion debe poder ejecutarse en tres modos:

```text
off
passive
required
```

Semantica propuesta:

- `off`: no se espera intervencion humana; las pruebas automatizadas usaran
  este modo por defecto.
- `passive`: el sistema genera solicitudes y plantillas de revision humana,
  pero no bloquea la ejecucion.
- `required`: ciertas decisiones quedan pendientes hasta que exista una
  aprobacion o rechazo humano.

Regla de Fase 4:

```text
Los tests y ejecuciones canonicas iniciales mantendran Human-in-the-loop en off.
```

El modo `required` se reservara para experimentos demostrativos, ejecuciones
costosas, inclusion de memoria supervisada o futuras acciones desde API.

## Fuera de alcance de Fase 4

No se abordara todavia:

- fine-tuning de LLMs;
- escritura o ejecucion de codigo generado por agentes;
- aprobacion automatica de decisiones por la memoria;
- uso obligatorio de servicios cloud para embeddings;
- indexacion indiscriminada de todos los documentos sin curacion;
- interfaz grafica completa;
- SLURM o HPC;
- Docker Compose como requisito operativo;
- evaluacion supervisada sobre NASA IMS real sin politica temporal validada.

## Hito 1: Contratos de memoria y revision humana

Objetivo: formalizar que entra y que no entra en memoria.

Trabajo previsto:

- consolidar `HumanReasoningReview` como artefacto final, no solo plantilla;
- definir `ReasoningMemoryRecord`;
- definir `AgentMemoryQuery`;
- definir `RetrievedMemoryContext`;
- separar veredicto humano de metrica tecnica;
- registrar `reusable_as_context`, `exclude_from_context` y motivo.

Criterio de aceptacion:

- los contratos validan JSON estricto;
- un post-mortem sin revision humana no entra automaticamente como ejemplo
  positivo;
- un caso `unsafe` o `exclude_from_context=true` no puede recuperarse como
  recomendacion.

## Hito 2: Base vectorial local por agente

Objetivo: implementar la primera memoria RAG real con embeddings.

Trabajo previsto:

- crear una interfaz local `VectorMemoryStore`;
- elegir backend local inicial, por ejemplo FAISS, Chroma o alternativa local
  ligera;
- persistir colecciones por agente;
- generar embeddings con un modelo local versionado;
- guardar metadatos trazables junto a cada vector;
- permitir reconstruir el indice desde artefactos fuente.

Criterio de aceptacion:

- existe al menos una coleccion vectorial para `modeler_memory`;
- se indexan post-mortems y revisiones humanas de Fase 3;
- una consulta por fallo de recall recupera casos relacionados;
- la reconstruccion del indice es reproducible.

## Hito 3: Memoria supervisada para el modelador

Objetivo: que el agente modelador pueda decidir con experiencia recuperada.

Trabajo previsto:

- recuperar 1-3 casos relevantes antes de un reintento;
- incluir en el prompt contexto compacto con citas;
- exigir que `ModelingRetryDecision` declare si uso memoria;
- registrar que memorias fueron consultadas;
- comparar una run con memoria frente a una run sin memoria.

Criterio de aceptacion:

- el modelador puede recibir ejemplos de sobrecorreccion y casos parciales;
- la decision final cita los `memory_record_id` usados;
- la memoria no permite elegir modelos sin ejecutor;
- el flujo sigue funcionando con memoria desactivada.

## Hito 4: Human-in-the-loop opcional

Objetivo: convertir la revision humana en un mecanismo conmutable y trazable.

Trabajo previsto:

- anadir configuracion `human_review_mode`;
- mantener `off` como valor por defecto en tests;
- en modo `passive`, generar solicitud sin bloquear;
- en modo `required`, bloquear solo acciones explicitamente marcadas;
- persistir revisor, fecha, veredicto y motivo cuando exista revision.

Criterio de aceptacion:

- la suite automatizada pasa con Human-in-the-loop apagado;
- existe un test de modo `passive` que genera solicitud sin bloquear;
- existe un test de modo `required` con revision simulada;
- la memoria solo incluye casos aprobados para reutilizacion.

Estado inicial implementado:

- la API reutiliza `HumanReviewSettings` y `HumanApproval`;
- la logica queda centralizada en `codigo/app/services/human_review.py`;
- `passive` devuelve razones de revision sin bloquear la ejecucion;
- `required` bloquea ejecucion API si no llega `human_approval.approved=true`;
- una aprobacion simulada se pasa al estado inicial y se persiste en el snapshot;
- Human-in-the-loop sigue apagado por defecto.

Interpretacion: el hito queda iniciado de forma pequena y coherente con la API,
sin modificar todavia el supervisor LangGraph ni introducir colas de aprobacion.

## Hito 5: Agente investigador con RAG local

Objetivo: resolver dudas de otros agentes usando evidencia, no navegacion libre.

Trabajo previsto:

- definir `ResearchRequest`;
- definir `EvidenceReport`;
- empezar con RAG local sobre `codigo/docs/`, `memoria/` y `recursos/`;
- usar coleccion `researcher_memory`;
- exigir citas, fecha, fuente y nivel de confianza;
- impedir que el investigador ejecute codigo o cambie configuraciones.

Criterio de aceptacion:

- un agente puede pedir evidencia sobre una duda metodologica;
- el investigador devuelve un informe citado y validado;
- el agente solicitante decide despues mediante su contrato normal;
- no hay acceso a internet por defecto.

## Hito 6: Tercer modelo ejecutable

Objetivo: ampliar el espacio real de decision del modelador.

Orden recomendado:

1. Local Outlier Factor.
2. One-Class SVM.
3. Autoencoder denso, solo si el coste y la memoria experimental lo justifican.

Criterio de aceptacion:

- el modelo elegido tiene ejecutor determinista;
- hay tests focalizados;
- las predicciones tienen el mismo contrato que Isolation Forest y PCA;
- existe comparacion persistida frente a modelos anteriores;
- la memoria puede recuperar casos por familia de modelo.

## Hito 7: Politica temporal para NASA IMS real

Objetivo: avanzar hacia una evaluacion defendible de datos run-to-failure.

Trabajo previsto:

- definir particion cronologica sin fuga;
- separar tramo inicial nominal y tramo de degradacion;
- documentar que etiquetas son metodologicas y no etiquetas originales por
  ventana;
- validar diagnosticos no supervisados antes de metricas supervisadas;
- decidir si la evaluacion sera supervisada, semisupervisada o solo de
  tendencia.

Criterio de aceptacion:

- existe un documento metodologico especifico de NASA IMS real;
- ninguna metrica supervisada se presenta sin explicar la politica temporal;
- los agentes reciben la limitacion como contexto, no como verdad escondida.

Estado inicial implementado:

- se ha creado `codigo/docs/33_politica_temporal_nasa_ims.md`;
- se ha definido `dataset_policy_id = "nasa_ims_temporal_v1"`;
- el runner comun bloquea NASA IMS completo si no se declara politica temporal
  o etiquetas sinteticas/controladas;
- con `nasa_ims_temporal_v1`, el manifiesto NASA IMS se deriva a
  `manifest_temporal_policy_v1.csv`;
- las etiquetas quedan marcadas como `label_source=temporal_proxy`,
  `label_policy_id=nasa_ims_temporal_v1`, `official_nasa_labels=false` y
  `official_window_labels=false`;
- la estructuracion respeta `split_hint` desde `metadata_json` cuando todos los
  registros lo declaran;
- la ejecucion
  `nasa-runner-temporal-policy-v1-completed-low-metrics-002` alcanzo modelado,
  evaluacion e informe final; termino como `completed` con `approved=false`
  por FPR 1.0000.

Interpretacion: el hito queda abierto. La infraestructura y la trazabilidad ya
permiten ejecuciones completas NASA IMS con politica declarada, pero falta
mejorar o justificar el protocolo experimental antes de tratar esas metricas
como evidencia principal.

Decision operativa anadida: una evaluacion con metricas bajas no se considera
fallo tecnico del pipeline. El supervisor debe completar la run y generar
informe con `approved=false`; `failed` queda reservado para errores de
infraestructura, contratos o artefactos.

## Hito 8: API controlada de ejecucion

Objetivo: abrir `POST /runs` sin romper seguridad ni reproducibilidad.

Trabajo previsto:

- definir contrato de solicitud;
- limitar datasets, modelos, rutas y coste;
- integrar `human_review_mode`;
- permitir modo `dry_run`;
- persistir estado y resultado como cualquier run local.

Criterio de aceptacion:

- `POST /runs` no acepta rutas arbitrarias;
- Human-in-the-loop esta apagado por defecto;
- las ejecuciones costosas pueden requerir revision;
- los runs generados por API quedan en el mismo registro local.

Estado inicial implementado:

- se ha creado `ApiRunRequest` y `ApiRunResponse`;
- `POST /runs` reutiliza `PipelineRunRequest` y `DatasetPipelinePlan`;
- `dry_run=true` por defecto devuelve solo el plan;
- con `dry_run=false`, la API ejecuta el runner comun si la politica lo permite;
- `raw_path` se limita a raices permitidas (`codigo/data/raw` por defecto);
- `use_llm=true` y memoria RAG quedan bloqueados en ejecucion API inicial;
- un `run_id` existente responde `409` para evitar sobrescrituras;
- las ejecuciones API persistidas aparecen en el mismo registro local que los
  scripts;
- Human Review `off/passive/required` queda integrado en la puerta de ejecucion
  de la API usando los contratos existentes;
- `background=true` permite aceptar ejecuciones como jobs locales observables
  sin crear un runner paralelo.

Interpretacion: el hito queda iniciado, no cerrado. Falta integrar
cola persistida, cancelacion y una politica de ejecucion con LLM/memoria antes
de usar la API como interfaz completa.

## Hito 9: Campana experimental con memoria

Objetivo: demostrar si la memoria agentica aporta valor.

Campanas candidatas:

- NASA sintetico: reintento sin memoria frente a reintento con memoria;
- CWRU: eleccion de modelo con memoria frente a politica determinista;
- caso de sobrecorreccion: comprobar si la memoria advierte al modelador.

Criterio de aceptacion:

- hay plan experimental;
- hay runs persistidas;
- hay tabla comparativa;
- hay conclusion academica sobre si la memoria ayudo, fue neutra o introdujo
  ruido.

## Hito 10: Actualizacion academica paralela

Objetivo: que la memoria del TFM avance al mismo ritmo que el codigo.

Regla operativa:

```text
Ninguna run canonica de Fase 4 se considera cerrada hasta tener:
  - snapshot persistido;
  - tabla o resumen tecnico;
  - reflejo en memoria academica;
  - verificacion reproducible;
  - clasificacion como evidencia principal, fallo util o caso frontera.
```

Capitulos afectados:

```text
memoria/capitulos/03_arquitectura.tex
memoria/capitulos/04_metodologia.tex
memoria/capitulos/05_implementacion.tex
memoria/capitulos/06_experimentos.tex
memoria/capitulos/07_resultados.tex
memoria/capitulos/08_conclusiones.tex
```

## Orden recomendado de ejecucion

1. Crear contratos de memoria y revision humana final.
2. Implementar base vectorial local minima para `modeler_memory`.
3. Indexar post-mortems y revisiones humanas de Fase 3.
4. Integrar retrieval opcional en el reintento del modelador.
5. Mantener Human-in-the-loop apagado en pruebas canonicas iniciales.
6. Anadir modo `passive` para generar solicitudes sin bloquear.
7. Comparar reintento con memoria frente a reintento sin memoria.
8. Extender memoria a evaluador y estructurador.
9. Introducir agente investigador con RAG local.
10. Implementar un tercer modelo ejecutable.
11. Definir politica temporal NASA IMS real.
12. Evaluar si `POST /runs` ya tiene suficientes guardarrailes.

## Primer paso concreto siguiente

El primer paso de Fase 4 ha sido implementar los contratos de memoria:

```text
HumanReasoningReview
HumanReviewSettings
ReasoningMemoryRecord
AgentMemoryQuery
RetrievedMemoryContext
```

Estos contratos deben permitir construir despues una base vectorial local por
agente sin acoplar todavia el pipeline a un backend concreto. La primera prueba
debe validar que un caso `overcorrected` de Fase 3 puede quedar registrado como
memoria negativa o caso frontera, pero no como recomendacion positiva.

## Avance inicial de implementacion

Se han incorporado los contratos base en:

```text
codigo/app/schemas/reasoning.py
codigo/tests/test_reasoning_memory_schema.py
```

La implementacion fija las siguientes reglas:

- `HumanReviewSettings` usa `mode = "off"` por defecto;
- un caso `overcorrected` puede guardarse como `boundary_case` o `warning`,
  pero no como `positive_example`;
- un ejemplo positivo requiere veredicto humano `correct`;
- un caso `unsafe` no puede recuperarse como contexto positivo;
- los registros `excluded` no pueden recuperarse como contexto;
- `RetrievedMemoryContext` valida que los recuerdos recuperados pertenecen al
  agente consultado o a `shared_methodology`.

En ese momento todavia no existia backend vectorial ni generacion de embeddings;
el siguiente avance tecnico aborda precisamente esa capa.

## Avance de base vectorial local

Se ha implementado el primer backend local de memoria vectorial en:

```text
codigo/app/services/vector_memory.py
codigo/tests/test_vector_memory_store.py
```

La implementacion introduce:

- `VectorMemoryStore`, una interfaz minima para backends de memoria vectorial;
- `LocalHashEmbeddingModel`, un embedding local determinista por hashing;
- `LocalJsonVectorMemoryStore`, un backend JSON reproducible con similitud
  coseno;
- colecciones canonicas por agente mediante `collection_for_agent(...)`;
- persistencia de metadatos de embedding en cada `ReasoningMemoryRecord`;
- reconstruccion completa del indice mediante `rebuild(...)`;
- consulta vectorial que devuelve `RetrievedMemoryContext`;
- filtrado por agente, dataset, rol de memoria, veredicto humano y similitud;
- conversion `memory_record_from_postmortem(...)` para transformar
  post-mortems y revisiones humanas en registros de memoria.

Este backend no pretende ser el backend definitivo si mas adelante se adopta
FAISS o Chroma. Su funcion es dejar fijada la semantica de memoria vectorial de
forma local, testeable y sin dependencias externas. Los tests validan que:

- `modeler_memory` puede persistirse y consultarse;
- `evaluator_memory` y el resto de colecciones quedan cubiertas por el mismo
  contrato, no por una implementacion especifica del modelador;
- los casos `unsafe` quedan excluidos por defecto;
- los recuerdos de otros agentes no aparecen en consultas del modelador;
- la memoria metodologica compartida si puede recuperarse;
- la reconstruccion del indice es reproducible;
- un post-mortem `overcorrected` sin revision queda como caso frontera no
  reutilizable, y con revision humana parcial puede entrar como contexto de
  frontera.

El siguiente avance tecnico aborda la indexacion reproducible de artefactos
reales de Fase 3, empezando por `reasoning_postmortem.json` y, cuando exista,
`human_reasoning_review.json` para `modeler_memory`.

## Decision de modelo de embeddings

Para el uso real local se adopta como modelo por defecto:

```text
qwen3-embedding:0.6b
```

Motivos:

- esta disponible en Ollama como modelo especifico de embeddings;
- pertenece a la familia Qwen, coherente con los agentes Qwen usados en Fase 3;
- la variante `0.6b` mantiene un tamano moderado frente a `4b` y `8b`;
- ofrece ventana de contexto amplia para fragmentos tecnicos largos;
- declara soporte multilingue amplio, util para documentacion y memoria en
  castellano, ingles tecnico y codigo;
- permite separar el LLM conversacional del modelo de embeddings sin perder
  coherencia de familia.

Alternativas consideradas:

- `embeddinggemma`: alternativa ligera y multilingue, adecuada si se prioriza
  despliegue en equipos pequenos;
- `all-minilm`: muy pequeno y rapido, pero con ventana menor y menos adecuado
  como memoria semantica principal del TFM;
- `bge-m3`: robusto y multilingue, pero menos alineado con la familia Qwen y
  potencialmente mas pesado para el objetivo local inicial.

Regla obligatoria:

```text
No mezclar vectores generados por modelos de embeddings distintos dentro de la
misma coleccion sin reconstruir el indice o versionar la coleccion.
```

Cada `ReasoningMemoryRecord` registra:

```text
embedding_model
embedding_version
embedding_dimension
vector_id
```

La implementacion incorpora:

```text
DEFAULT_OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
OllamaEmbeddingProvider
get_default_embedding_provider()
```

Variables de entorno:

```text
TFM_EMBEDDING_PROVIDER=ollama | local_hash
TFM_EMBEDDING_MODEL=qwen3-embedding:0.6b
TFM_EMBEDDING_TIMEOUT_SECONDS=60
TFM_EMBEDDING_DIMENSION=128  # solo local_hash
OLLAMA_HOST=http://127.0.0.1:11434
```

En pruebas automatizadas se puede usar `TFM_EMBEDDING_PROVIDER=local_hash`.
En ejecuciones reales se usara Ollama y sera necesario tener el modelo
descargado localmente:

```text
ollama pull qwen3-embedding:0.6b
```

## Avance de indexacion supervisada

Se ha implementado el indexador inicial de memoria agentica en:

```text
codigo/app/services/reasoning_memory_index.py
codigo/scripts/index_reasoning_memory.py
codigo/tests/test_reasoning_memory_index.py
```

El indexador recorre `codigo/reports/` buscando `reasoning_postmortem.json` y,
por defecto, solo convierte un post-mortem en memoria reutilizable si existe
una revision final `human_reasoning_review.json` junto al artefacto original.
Esta regla evita que un razonamiento generado automaticamente entre como
evidencia positiva sin validacion humana. Cuando se active
`--include-unreviewed`, los casos sin revision pueden indexarse como memoria de
frontera o advertencia, pero no como recomendacion positiva.

Ademas, el indexador puede incorporar auditorias de uso de memoria mediante
`--include-memory-usage-audits`. Estas auditorias no sustituyen a la revision
humana: entran como `warning`, `boundary_case` o `evidence` segun el resultado
de la auditoria. Asi se evita que un agente que haya usado mal una memoria
convierta ese fallo en una recomendacion positiva.

El resultado se persiste por defecto en:

```text
codigo/reports/reasoning_memory/
```

y genera `reasoning_memory_index_report.json`, con registros indexados,
post-mortems omitidos y revisiones ausentes. La ejecucion real usara
`qwen3-embedding:0.6b`; las pruebas unitarias usan el proveedor determinista
`local_hash` para no depender de Ollama. En esta estacion de trabajo el modelo
`qwen3-embedding:0.6b` ya se ha descargado en Ollama y se ha verificado que
produce vectores de dimension 1024.

Comando canonico para reconstruir la memoria revisada:

```text
python -m codigo.scripts.index_reasoning_memory \
  --reports-root codigo/reports \
  --memory-dir codigo/reports/reasoning_memory \
  --clear-existing
```

Comando canonico para reconstruir la memoria con auditorias de uso:

```text
python -m codigo.scripts.index_reasoning_memory \
  --reports-root codigo/reports \
  --memory-dir codigo/reports/reasoning_memory \
  --clear-existing \
  --include-memory-usage-audits
```

El siguiente paso tecnico de Fase 4 pasa a ser integrar retrieval opcional en
el reintento del modelador: el agente debera recibir 1-3 recuerdos relevantes,
citar los `memory_record_id` usados y seguir devolviendo su decision bajo el
contrato Pydantic existente.

## Avance de retrieval opcional para el modelador

Se ha integrado la memoria supervisada en el reintento del agente modelador sin
activarla por defecto. La decision `ModelingRetryDecision` incorpora ahora:

```text
memory_context_id
used_memory_context
memory_record_ids
```

Con esto, el agente debe declarar explicitamente si uso la memoria recuperada y
citar los recuerdos concretos que influyeron en su decision. Si intenta citar un
`memory_record_id` que no aparece en el contexto recuperado, la decision se
rechaza y se activa el fallback conservador.

La integracion esta en:

```text
codigo/app/agents/modeler.py
codigo/scripts/run_nasa_ims_agentic_retry.py
codigo/tests/test_modeler_agent.py
codigo/tests/test_agent_decisions_schema.py
```

El flujo de retry sigue funcionando sin memoria. Para activarla en una
ejecucion real:

```text
python -m codigo.scripts.run_nasa_ims_agentic_retry \
  --use-memory \
  --memory-dir codigo/reports/reasoning_memory \
  --memory-top-k 3
```

Cuando se activa, el sistema genera una consulta `AgentMemoryQuery`, recupera
memoria de `modeler_memory` y `shared_methodology_memory`, persiste el contexto
en `retrieved_memory_context.json` y lo pasa al prompt del modelador como
evidencia citada. La memoria no ejecuta cambios, no aprueba metricas y no puede
ampliar el espacio de modelos soportados por el ejecutor.

Estado del hito:

- retrieval opcional implementado;
- memoria apagada por defecto;
- decision del agente obligada a declarar uso de memoria;
- validacion de citas contra el contexto recuperado;
- memoria canonica poblada con un primer caso frontera revisado;
- primera comparacion con memoria ejecutada;
- auditoria de uso de memoria implementada.

## Primera memoria canonica revisada

Se ha creado una revision final para el post-mortem del segundo reintento NASA
sintetico:

```text
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/iteration/human_reasoning_review.json
```

El veredicto es `partially_correct`: la direccion del razonamiento era util
porque redujo falsos negativos, pero la magnitud fue excesiva porque la tasa de
falsos positivos subio hasta `1.0`. Por tanto, no entra como ejemplo positivo,
sino como `boundary_case` reutilizable por el modelador.

La memoria canonica reconstruida queda en:

```text
codigo/reports/reasoning_memory/modeler_memory.json
codigo/reports/reasoning_memory/reasoning_memory_index_report.json
```

Resultado de indexacion inicial:

- registros indexados: `1`;
- coleccion: `modeler_memory`;
- modelo de embeddings: `qwen3-embedding:0.6b`;
- dimension: `1024`;
- post-mortems pendientes de revision final: `1`.

Una consulta de humo sobre sobrecorreccion de umbral recupera este recuerdo con
uso `boundary_context` y similitud aproximada `0.6868`. Esto confirma el primer
circuito completo de Fase 4:

```text
post-mortem -> revision humana -> embedding Qwen -> memoria vectorial -> retrieval
```

## Primer experimento con memoria activada

Se ha lanzado una ejecucion de humo con memoria activada:

```text
python -m codigo.scripts.run_nasa_ims_agentic_retry \
  --model qwen3.5:4b \
  --source-run-id nasa-ims-synth-agentic-qwen-fase3 \
  --run-id-prefix nasa-ims-synth-agentic-qwen-fase4-memory \
  --max-attempts 1 \
  --use-memory \
  --memory-dir codigo/reports/reasoning_memory \
  --memory-top-k 3
```

Run generada:

```text
nasa-ims-synth-agentic-qwen-fase4-memory-attempt-01
```

Resultado:

- la memoria se recupero correctamente desde `modeler_memory`;
- el agente declaro `used_memory_context=true`;
- cito el recuerdo
  `nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02:reasoning_postmortem:002:memory:modeler`;
- aun asi propuso `threshold_quantile=0.5`, que reproduce la misma
  sobrecorreccion advertida por la memoria;
- metricas finales: precision `0.7143`, recall `1.0000`, F1 `0.8333`, FPR
  `1.0000`;
- el evaluador rechazo la run y el bucle se detuvo por presupuesto agotado.

Interpretacion:

La memoria RAG funciona tecnicamente, pero el LLM local no siempre transforma
una advertencia recuperada en una decision mas prudente. Este resultado es
academicamente valioso: demuestra que no basta con recuperar recuerdos; el
agente debe razonar sobre el uso de la memoria y justificar por que no repite
acciones asociadas a casos frontera o sobrecorrecciones.

Siguiente ajuste recomendado:

- convertir la auditoria especifica de uso de memoria en un nuevo recuerdo
  reutilizable de tipo advertencia.

## Auditoria especifica de uso de memoria

Se ha implementado el ajuste anterior. `ModelingRetryDecision` ahora exige una
declaracion mas rica cuando usa memoria:

```text
memory_usage_summary
memory_record_uses[]
  - memory_record_id
  - usage: followed | adapted | contradicted | ignored
  - influence_summary
  - risk_mitigation
```

Si el recuerdo recuperado es `boundary_case` o `warning`, el modelador debe
explicar como evita repetir el fallo. El sistema valida que cada recuerdo
citado tenga una declaracion de uso y que no se citen recuerdos no recuperados.

Ademas, se ha creado una auditoria automatica:

```text
codigo/app/services/memory_usage_audit.py
codigo/tests/test_memory_usage_audit.py
```

La auditoria genera:

```text
memory_usage_audit.json
memory_usage_audit.md
```

Nueva ejecucion de verificacion:

```text
nasa-ims-synth-agentic-qwen-fase4-memory-audit-attempt-01
```

En esta ejecucion, Qwen declaro que usaba la memoria como `adapted`, explico que
el recuerdo advertia contra bajar el umbral sin control y propuso una
mitigacion. Sin embargo, volvio a elegir `threshold_quantile=0.5`; las metricas
finales repitieron FPR `1.0000`. La auditoria clasifico el resultado como:

```text
memory_repeated_boundary_failure
```

Este artefacto es especialmente util para el TFM porque separa tres niveles:

- retrieval correcto;
- comunicacion declarada por el agente;
- contraste automatico entre esa declaracion y la evidencia experimental.

Estado aplicado y siguientes ajustes:

- esta auditoria ya puede alimentarse como memoria supervisada negativa o de
  frontera;
- endurecer el prompt para que un `boundary_case` no pueda ser usado como
  apoyo de una accion identica sin una diferencia cuantitativa explicita;
- considerar un campo de decision tipo `memory_safety_check_passed` antes de
  ejecutar el reintento.

## Memoria transversal y auditorias como fuente RAG

Se ha aplicado el siguiente paso: las auditorias de uso de memoria pueden
convertirse en nuevos `ReasoningMemoryRecord` mediante:

```text
memory_record_from_memory_usage_audit(...)
```

La conversion recibe siempre `target_agent`, por lo que no esta acoplada al
modelador. Una auditoria futura del limpiador podria alimentar
`cleaner_memory`, una del evaluador `evaluator_memory`, y una metodologia
transversal `shared_methodology_memory`. Los tests validan que una consulta del
evaluador recupera su propia memoria y la memoria compartida, pero no recuerdos
privados del modelador.

Tambien se ha ampliado `MemorySourceType` con:

```text
memory_usage_audit
```

Reconstruccion canonica ejecutada:

```text
python -m codigo.scripts.index_reasoning_memory \
  --reports-root codigo/reports \
  --memory-dir codigo/reports/reasoning_memory \
  --clear-existing \
  --include-memory-usage-audits
```

Resultado actual de la memoria canonica:

- registros indexados: `2`;
- fuentes: `human_review` y `memory_usage_audit`;
- coleccion afectada por ahora: `modeler_memory`;
- nuevo recuerdo de auditoria: `warning`;
- modelo de embeddings: `qwen3-embedding:0.6b`;
- dimension: `1024`;
- post-mortems pendientes de revision final: `3`.

Consulta de humo tras reconstruir:

```text
threshold quantile recall false positive repeated boundary failure
```

Resultado relevante:

- primer recuerdo recuperado: `memory_usage_audit`, rol `warning`, uso
  `negative_warning`, similitud aproximada `0.6852`;
- segundo recuerdo recuperado: `human_review`, rol `boundary_case`, uso
  `boundary_context`, similitud aproximada `0.6559`.

Esto cierra el primer bucle de aprendizaje controlado:

```text
revision humana -> memoria de frontera -> uso por agente -> auditoria del uso
-> memoria de advertencia -> siguiente decision agentica
```

## Nueva iteracion con memoria ampliada

Se ha ejecutado la prueba prevista con la memoria ampliada:

```text
python -m codigo.scripts.run_nasa_ims_agentic_retry \
  --model qwen3.5:4b \
  --source-run-id nasa-ims-synth-agentic-qwen-fase3 \
  --run-id-prefix nasa-ims-synth-agentic-qwen-fase4-memory-fed \
  --max-attempts 1 \
  --timeout-seconds 120 \
  --use-memory \
  --memory-dir codigo/reports/reasoning_memory \
  --memory-top-k 3
```

Run generada:

```text
nasa-ims-synth-agentic-qwen-fase4-memory-fed-attempt-01
```

Resultado agentico:

- Qwen recupero y cito los dos recuerdos disponibles;
- uso el caso frontera como `adapted`;
- uso la auditoria previa como `adapted`;
- no repitio `threshold_quantile=0.50`;
- propuso `threshold_quantile=0.95` como ajuste conservador.

Metricas del reintento:

- precision: `0.8846`;
- recall: `0.6571`;
- F1: `0.7541`;
- FPR: `0.2143`;
- matriz de confusion: TN=`11`, FP=`3`, FN=`12`, TP=`23`.

Comparado con la run base, el reintento mejora recall (`0.6000 -> 0.6571`) y
F1 (`0.7241 -> 0.7541`), pero empeora precision (`0.9130 -> 0.8846`) y FPR
(`0.1429 -> 0.2143`). El evaluador rechaza la ejecucion, correctamente, porque
la mejora es insuficiente y el FPR supera el objetivo operativo.

La auditoria de memoria clasifica el uso como:

```text
memory_aligned
```

Interpretacion:

La memoria ampliada si ha modificado la conducta del agente: ha evitado repetir
el cambio radical que ya habia fallado. Sin embargo, el ajuste conservador de
umbral tampoco resuelve el problema. Esto sugiere que el siguiente avance no
debe ser insistir solo en `threshold_quantile`, sino ampliar la deliberacion
del modelador hacia alternativas soportadas, especialmente cambio de familia de
modelo o comparacion entre Isolation Forest y PCA reconstruction error.

El siguiente paso natural es preparar un reintento agentico que pueda comparar
configuraciones candidatas antes de ejecutar una sola, o activar memoria
opcional para el evaluador de modo que este pueda justificar con mas detalle
por que una mejora parcial sigue sin ser aceptable.

## Contrato general de episodios de decision

Para evitar que la memoria quede reducida a ajustes de umbral, se ha
implementado un contrato transversal para almacenar episodios completos de
decision agentica:

```text
DecisionEpisode
DecisionOption
MemoryCandidate
```

La idea es que la unidad de memoria no sea un parametro aislado, sino una
historia tecnica compacta:

- que agente decidio;
- que tipo de decision era;
- que contexto tenia;
- que alternativas considero;
- que accion eligio;
- que efecto esperaba;
- que evidencia uso;
- que resultado produjo la ejecucion;
- que metricas cambiaron;
- que trade-offs aparecieron;
- que modos de fallo quedaron claros;
- cuando se debe reutilizar;
- cuando no se debe reutilizar;
- que riesgo hay si se usa mal.

`DecisionEpisode` queda pensado para cualquier agente:

- limpiador: canal, remuestreo, normalizacion, tratamiento de datos;
- estructurador: ventana, solape, particion temporal, features;
- modelador: familia de modelo, hiperparametros, umbral, alternativas;
- evaluador: motivo de aprobacion o rechazo;
- redactor: forma de explicar un resultado;
- investigador: evidencia recuperada y nivel de confianza.

`MemoryCandidate` es la version destilada del episodio para RAG. No sustituye al
episodio completo: extrae la leccion reutilizable y obliga a declarar:

```text
when_to_reuse
when_not_to_reuse
risk_if_misused
memory_role
target_agent
```

Reglas de seguridad:

- un `positive_example` requiere `human_verdict=correct`;
- un candidato reutilizable debe declarar `when_to_reuse`;
- un `warning` o `negative_example` debe incluir condicion de no reutilizacion
  o riesgo;
- un candidato excluido no puede entrar como contexto recuperable.

El flujo automatizable queda asi:

```text
decision agentica
-> DecisionEpisode
-> MemoryCandidate
-> embedding local
-> ReasoningMemoryRecord
-> coleccion vectorial del agente
```

El indexador ya recoge automaticamente artefactos:

```text
memory_candidate.json
```

y los convierte en memoria vectorial mediante:

```text
memory_record_from_candidate(...)
```

Por tanto, el futuro proceso de retroalimentacion queda claro: los agentes o el
post-mortem generan episodios, el sistema destila candidatos, el humano puede
aprobar o descartar cuando proceda, y el indexador genera embeddings y almacena
la memoria en la coleccion adecuada.

Tests incorporados:

- validacion de episodios con alternativas y modos de fallo;
- rechazo de candidatos positivos sin revision humana correcta;
- conversion `DecisionEpisode -> MemoryCandidate -> ReasoningMemoryRecord`;
- indexacion automatica de `memory_candidate.json`;
- recuperacion vectorial del candidato como `boundary_context`.

## Generacion automatica desde post-mortems

Se ha aplicado el siguiente paso: los post-mortems de reintento del modelador ya
generan automaticamente episodios y candidatos de memoria.

Implementacion:

```text
codigo/app/services/decision_memory.py
codigo/tests/test_decision_memory.py
```

Cuando una ejecucion de retry escribe `reasoning_postmortem.json`, el flujo
tambien persiste:

```text
decision_episode.json
decision_episode.md
memory_candidate.json
memory_candidate.md
```

Estos artefactos quedan registrados en el snapshot de la run como:

```text
decision_episode
decision_episode_report
memory_candidate
memory_candidate_report
```

El candidato se marca como reutilizable cuando no se ha pedido revision humana
bloqueante. Si se solicita revision humana, el candidato queda persistido como
evidencia, pero no debe entrar automaticamente como contexto hasta que el
humano lo valide o lo descarte. El indexador ya sabe leer `memory_candidate.json`
y convertirlo en embedding local.

El episodio generado contiene:

- resumen del contexto y metricas previas;
- configuracion elegida como alternativa seleccionada;
- alternativas comparables si el agente las propuso;
- recuerdos recuperados;
- resumen de evaluacion;
- trade-offs observados;
- modos de fallo;
- condiciones de reutilizacion y no reutilizacion;
- riesgo si se aplica fuera de contexto.

Esto cierra la primera automatizacion completa:

```text
decision -> ejecucion -> evaluacion -> post-mortem
-> DecisionEpisode -> MemoryCandidate -> indexador -> embedding -> memoria
```

Estado de verificacion: `202` tests pasan correctamente.

## Primera run con candidato de memoria real

Se ha ejecutado una run Qwen con la generacion automatica de episodios activada:

```text
python -m codigo.scripts.run_nasa_ims_agentic_retry \
  --model qwen3.5:4b \
  --source-run-id nasa-ims-synth-agentic-qwen-fase3 \
  --run-id-prefix nasa-ims-synth-agentic-qwen-fase4-episode-candidate \
  --max-attempts 1 \
  --timeout-seconds 120 \
  --use-memory \
  --memory-dir codigo/reports/reasoning_memory \
  --memory-top-k 3
```

Run generada:

```text
nasa-ims-synth-agentic-qwen-fase4-episode-candidate-attempt-01
```

La decision de Qwen fue coherente con la memoria previa:

- recupero y cito los dos recuerdos existentes;
- no repitio `threshold_quantile=0.50`;
- propuso `threshold_quantile=0.95`;
- la auditoria de memoria fue `memory_aligned`.

Metricas:

- precision: `0.8846`;
- recall: `0.6571`;
- F1: `0.7541`;
- FPR: `0.2143`;
- matriz de confusion: TN=`11`, FP=`3`, FN=`12`, TP=`23`.

El resultado sigue rechazado por el evaluador, pero ahora la run deja un
episodio reutilizable:

```text
decision_episode.json
memory_candidate.json
```

El `memory_candidate` queda como:

- `target_agent`: `modeler`;
- `memory_role`: `boundary_case`;
- `source_type`: `decision_episode`;
- `reusable_as_context`: `true`;
- leccion principal: la memoria evito repetir el salto radical de umbral, pero
  el ajuste moderado solo produjo una mejora parcial y aumento FPR.

Despues se reconstruyo la memoria canonica con:

```text
python -m codigo.scripts.index_reasoning_memory \
  --reports-root codigo/reports \
  --memory-dir codigo/reports/reasoning_memory \
  --clear-existing \
  --include-memory-usage-audits \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b
```

Resultado actual:

- registros en `modeler_memory`: `5`;
- post-mortem humano revisado: `1`;
- auditorias de uso de memoria: `3`;
- candidatos de memoria por episodio: `1`;
- embedding: `qwen3-embedding:0.6b`, dimension `1024`.

Consulta de humo:

```text
partial threshold gain recall fpr compare model family PCA isolation forest
```

Resultados principales:

- `human_review`, `boundary_case`, similitud `0.7009`;
- `decision_episode`, `boundary_case`, similitud `0.6823`;
- auditorias `memory_aligned`, similitud `0.6358`;
- advertencia previa `memory_repeated_boundary_failure`, similitud `0.6103`.

Esto confirma que el RAG ya recupera episodios completos, no solo avisos sobre
umbral. El siguiente paso natural pasa a ser ejecutar un retry donde el
modelador use esta memoria para comparar familias de modelo, especialmente
Isolation Forest frente a PCA reconstruction error.

## Iteracion con comparacion de familia de modelo

Se ha aplicado el siguiente paso natural: reforzar el reintento del modelador
para que la memoria por episodios no empuje solo a mover `threshold_quantile`.
El prompt de retry expone ahora `source_type` de cada recuerdo recuperado y
advierte explicitamente que, si aparece un `decision_episode` o la etiqueta
`compare_model_family_after_partial_threshold_gain`, el agente debe considerar
cambiar de familia de modelo dentro de las opciones soportadas.

Ademas, el formato esperado del reintento incluye ejemplos de
`comparison_candidates`:

- `pca_reconstruction_error_candidate`;
- `iforest_moderate_threshold_candidate`.

Estos candidatos no ejecutan nada por si mismos. Sirven como evidencia de
deliberacion: el agente sigue eligiendo una unica `retry_config`, validada por
Pydantic y ejecutada por el ejecutor determinista.

Run de verificacion:

```text
nasa-ims-synth-agentic-qwen-fase4-model-family-attempt-01
```

Resultado:

- Qwen recupero y cito memoria de episodio, post-mortem humano y auditoria;
- incluyo `pca_reconstruction_error_candidate` como alternativa comparable;
- eligio ejecutar `isolation_forest` con `threshold_quantile=0.95`;
- las metricas fueron precision `0.8846`, recall `0.6571`, F1 `0.7541`, FPR
  `0.2143`;
- el evaluador rechazo la ejecucion, pero la run dejo evidencia clara de que
  el agente comparo familias de modelo.

Durante esta run aparecio un nuevo problema cualitativo: Qwen escribio una
inconsistencia numerica en su razonamiento, por ejemplo tratar `0.95` como mayor
que `0.99` y describir `0.99` como umbral bajo. Esto no invalida la
infraestructura RAG, pero si muestra que los LLM locales pueden citar memoria y
aun asi cometer errores aritmeticos o direccionales en la explicacion.

Se ha implementado una nueva clasificacion de auditoria:

```text
memory_reasoning_inconsistent
reasoning_inconsistent
```

La auditoria detecta comparaciones numericas imposibles en la explicacion del
agente y las convierte en evidencia trazable. La verificacion real se hizo con:

```text
nasa-ims-synth-agentic-qwen-fase4-coherence-audit-attempt-01
```

En esta run se repitio el patron metricamente equivalente, pero
`memory_usage_audit.json` clasifico el resultado como
`memory_reasoning_inconsistent` y dejo como motivo:

```text
El razonamiento afirma que 0.95 es mayor que 0.99.
```

La memoria canonica se reconstruyo de nuevo con embeddings Qwen:

```text
python -m codigo.scripts.index_reasoning_memory \
  --reports-root codigo/reports/nasa_ims_bearing \
  --memory-dir codigo/reports/reasoning_memory \
  --dataset nasa_ims_bearing \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b \
  --include-memory-usage-audits \
  --clear-existing
```

Resultado actual de `modeler_memory`:

- registros: `9`;
- `human_review`: `1`;
- `memory_usage_audit`: `5`;
- `decision_episode`: `3`;
- embedding: `ollama:qwen3-embedding:0.6b`;
- dimension: `1024`.

Interpretacion:

La memoria ya no solo advierte sobre malas metricas. Tambien conserva evidencia
de razonamientos incoherentes. Esto es defendible academicamente porque permite
mostrar tres capas separadas: recuperacion semantica, decision del agente y
auditoria critica de su explicacion.

## Ejecucion real de cambio de familia a PCA

Se ha aplicado el siguiente paso logico: convertir la comparacion de familia de
modelo en una hipotesis ejecutable, no solo documentada. Para ello se anadio al
prompt una guia derivada de memoria:

```text
memory_retry_guidance
```

Cuando la memoria recuperada indica que `isolation_forest` con ajuste de umbral
ya produjo solo una mejora parcial rechazada, la guia marca:

```text
model_family_shift_recommended = true
preferred_retry_config = pca_reconstruction_error
avoid_threshold_only_isolation_forest_retry = true
```

La regla no ejecuta PCA de forma determinista. El agente conserva la decision,
pero debe elegir entre:

- ejecutar `pca_reconstruction_error`;
- parar con `should_retry=false` si considera que no queda margen real.

Primera run tras esta guia:

```text
nasa-ims-synth-agentic-qwen-fase4-pca-guided-attempt-01
```

Qwen eligio por primera vez ejecutar:

```text
model_name = pca_reconstruction_error
threshold_quantile = 0.99
```

Despues de corregir un falso positivo de la auditoria de coherencia, se dejo
como run canonica:

```text
nasa-ims-synth-agentic-qwen-fase4-pca-final-attempt-01
```

Metricas principales:

- precision: `0.9375`;
- recall: `0.4286`;
- F1: `0.5882`;
- FPR: `0.0714`;
- matriz de confusion: TN=`13`, FP=`1`, FN=`20`, TP=`15`;
- evaluacion: rechazada por recall bajo.

Interpretacion:

La memoria logro cambiar la familia de modelo ejecutada. Esto demuestra
protagonismo agentico con RAG: Qwen recupero episodios previos, entendio que
seguir tocando solo el umbral producia mejoras parciales, y eligio PCA como
hipotesis alternativa soportada. El resultado fue tecnicamente informativo pero
no aprobado: PCA redujo FPR por debajo del objetivo, pero perdio demasiadas
anomalias. La leccion almacenada es que `pca_reconstruction_error` con umbral
`0.99` es demasiado conservador para este benchmark sintetico.

La memoria canonica se reconstruyo de nuevo tras esta run:

```text
python -m codigo.scripts.index_reasoning_memory \
  --reports-root codigo/reports/nasa_ims_bearing \
  --memory-dir codigo/reports/reasoning_memory \
  --dataset nasa_ims_bearing \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b \
  --include-memory-usage-audits \
  --clear-existing
```

Resultado actual de `modeler_memory`:

- registros: `16`;
- embedding: `ollama:qwen3-embedding:0.6b`;
- contiene casos de sobrecorreccion, mejoras parciales con Isolation Forest,
  cambio de familia a PCA, auditorias de uso y episodios de decision.

Decision de foco tras esta evidencia:

- no seguir profundizando por ahora en ajustes de umbral ni en PCA;
- conservar esta linea como demostracion de que la memoria puede cambiar una
  accion real y que el evaluador mantiene el control experimental;
- dedicar el siguiente bloque a memoria multiagente transversal, para que el
  aprendizaje incremental no dependa solo del modelador.

## Extension de memoria a estructurador y evaluador

Se ha implementado el siguiente paso logico de Fase 4: preparar el mismo patron
de memoria supervisada para agentes que actuan en otras partes del pipeline.
El objetivo no es forzar nuevos fallos ni optimizar de nuevo un parametro
concreto. El objetivo es que cada ejecucion pueda dejar una experiencia
indexable y que, iteracion tras iteracion, cada agente recupere contexto util
de su propio rol.

Cambios introducidos:

- `StructuringDecision` y `EvaluationDecision` incorporan campos opcionales de
  uso de memoria:
  - `memory_context_id`;
  - `used_memory_context`;
  - `memory_record_ids`;
  - `memory_usage_summary`;
  - `memory_record_uses`.
- El estructurador puede construir y recuperar consultas RAG propias mediante
  `build_structurer_memory_query` y `retrieve_structurer_memory_context`.
- El evaluador puede construir y recuperar consultas RAG propias mediante
  `build_evaluator_memory_query` y `retrieve_evaluator_memory_context`.
- Se ha creado un servicio comun `agent_memory.py` para serializar memoria
  recuperada en prompts, generar plantillas de declaracion de uso y validar que
  un agente no cite recuerdos que no han sido recuperados.
- `decision_memory.py` ya puede generar episodios y candidatos de memoria para:
  - `structurer_memory`;
  - `evaluator_memory`;
  - ademas de `modeler_memory`.

Reglas de seguridad mantenidas:

- la memoria del estructurador no puede saltarse ventanas, solapes, canales ni
  features soportadas;
- la memoria del evaluador no puede aprobar metricas que incumplen el protocolo
  local;
- un recuerdo recuperado debe citarse con `memory_record_id`;
- un recuerdo citado debe tener una declaracion de uso;
- un recuerdo no recuperado no puede aparecer como memoria usada por el agente.

Interpretacion:

Este cambio desplaza la Fase 4 desde un caso concreto de modelado hacia una
memoria de proceso. A partir de ahora el sistema puede almacenar, por ejemplo:

- que una ventana corta dio mas resolucion temporal pero debe validarse aguas
  abajo;
- que un conjunto de features aumento explicabilidad pero tambien dimension;
- que un evaluador rechazo correctamente una mejora parcial por no cumplir el
  protocolo;
- que una aprobacion o rechazo debe reutilizarse solo bajo la misma politica de
  metricas y etiquetado.

Por tanto, la memoria empieza a representar aprendizaje operacional de todo el
pipeline, no solo ajustes de hiperparametros del modelador.

El paso inmediato derivaba en:

- conectar estos episodios transversales a una ejecucion completa sin forzar
  errores;
- mantener Human-in-the-loop apagado en pruebas automatizadas;
- indexar como memoria reutilizable solo candidatos aceptados por politica o
  revision humana;
- observar si, tras varias runs normales, estructurador y evaluador empiezan a
  citar experiencias previas de forma util y trazable.

## Avance de conexion transversal al grafo completo

Se ha implementado la conexion opcional de memoria transversal en el grafo
CWRU completo, sin cambiar el comportamiento por defecto del pipeline.

Cambios introducidos:

- `PipelineMemoryConfig` permite activar memoria RAG en el grafo mediante un
  `VectorMemoryStore`, con `top_k`, similitud minima y directorio de salida;
- el estructurador recupera memoria propia antes de decidir cuando la memoria
  esta activada;
- el evaluador recupera memoria propia antes de emitir juicio cuando la memoria
  esta activada;
- el contexto recuperado se persiste como:

```text
codigo/reports/<dataset>/<run_id>/agent_memory/<agent>/retrieved_memory_context.json
```

- tras ejecutar la estructuracion se generan `decision_episode.json` y
  `memory_candidate.json` para `structurer_memory`;
- tras la decision del evaluador se generan los mismos artefactos para
  `evaluator_memory`;
- Human-in-the-loop sigue apagado por defecto y la memoria continua siendo
  opcional.

La integracion esta en:

```text
codigo/app/graph/pipeline.py
codigo/tests/test_graph_pipeline.py
```

La prueba nueva valida una ejecucion completa con memoria simulada en la que:

- el estructurador recibe y cita un recuerdo recuperado;
- el evaluador recibe y cita un recuerdo recuperado;
- se escriben los contextos RAG recuperados;
- se escriben candidatos indexables para `structurer_memory` y
  `evaluator_memory`;
- el pipeline sigue completando la ejecucion sin Human-in-the-loop.

Estado de verificacion de este hito: `217` tests pasan correctamente.

A partir de esta ejecucion quedaban tres tareas inmediatas:

- ejecutar una run normal con memoria transversal activada usando el indice
  local real;
- reconstruir el indice con los nuevos `memory_candidate.json`;
- comprobar que aparecen colecciones `structurer_memory` y `evaluator_memory`;
- observar si nuevas runs empiezan a recuperar y citar esos recuerdos de forma
  util, sin convertir la memoria en mecanismo de aprobacion.

## Ejecucion canonica con memoria transversal

Se ha creado un script canonico para ejecutar el pipeline CWRU completo con
memoria RAG transversal:

```text
codigo/scripts/run_cwru_pipeline_with_memory.py
```

Este script es deliberadamente especifico de CWRU. No selecciona entre CWRU y
NASA IMS ni debe usarse para runs NASA. Crea el estado con
`create_initial_cwru_state`, usa los ejecutores CWRU por defecto y deja que el
indexador infiera el dataset por rutas al reconstruir la memoria. Para NASA IMS
se conservan los scripts propios de NASA y, si se necesita una entrada comun,
debera crearse un wrapper multi-dataset explicito. Ademas, el script aborta si
la ruta `--raw-path` parece apuntar a NASA/IMS, para evitar etiquetar una run
NASA como CWRU por accidente.

El script permite:

- activar `PipelineMemoryConfig` sobre el grafo completo;
- seleccionar proveedor de embeddings (`ollama` o `local_hash`);
- usar agentes deterministas por defecto o agentes Qwen con `--use-llm`;
- persistir la run mediante el registro local;
- reconstruir el indice de memoria al finalizar con `--rebuild-index`;
- resumir artefactos de memoria, decisiones y colecciones indexadas.

Primera ejecucion canonica, sin LLM generativo, para crear memoria transversal
inicial:

```text
python -m codigo.scripts.run_cwru_pipeline_with_memory \
  --run-id cwru-memory-transversal-fase4-001 \
  --rebuild-index \
  --clear-existing \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b
```

Resultado:

- run completada y aprobada sobre CWRU;
- precision `0.9991`, recall `1.0000`, F1 `0.9996`, FPR `0.0513`;
- se generaron artefactos RAG para `structurer` y `evaluator`;
- el indice reconstruido quedo con:
  - `modeler_memory`: `16`;
  - `structurer_memory`: `1`;
  - `evaluator_memory`: `1`.

Segunda ejecucion, con Qwen activado, para comprobar si los agentes recuperan y
citan memoria transversal real:

```text
python -m codigo.scripts.run_cwru_pipeline_with_memory \
  --run-id cwru-memory-transversal-fase4-002-llm \
  --use-llm \
  --model qwen3.5:4b \
  --rebuild-index \
  --clear-existing \
  --embedding-provider ollama \
  --embedding-model qwen3-embedding:0.6b
```

Resultado:

- run completada y aprobada sobre CWRU;
- el estructurador declaro `used_memory_context=true`;
- el evaluador declaro `used_memory_context=true`;
- ambos citaron recuerdos recuperados de la run
  `cwru-memory-transversal-fase4-001`;
- el indice reconstruido quedo con:
  - `modeler_memory`: `16`;
  - `structurer_memory`: `2`;
  - `evaluator_memory`: `2`;
  - total: `20` registros.

Interpretacion:

Este hito confirma que la memoria de Fase 4 ya no esta limitada al modelador.
Una run completa puede generar memoria para estructurador y evaluador, y una
run posterior con LLM puede recuperar y citar esos recuerdos sin que la memoria
apruebe metricas ni salte validaciones. La memoria actua como contexto
trazable, no como ejecutor ni autoridad de aprobacion.

A partir de esta ejecucion quedaban tres tareas inmediatas:

- auditar cualitativamente las dos nuevas decisiones con memoria transversal;
- decidir si los candidatos de `structurer_memory` y `evaluator_memory`
  requieren revision humana antes de consolidarse como evidencia principal;
- preparar una comparacion breve con y sin memoria transversal en CWRU o NASA
  sintetico, centrada en uso de memoria y no solo en metricas.

## Auditoria cualitativa de memoria transversal

Se ha implementado y ejecutado el siguiente paso natural: una auditoria
especifica para decisiones de `structurer` y `evaluator` que usan memoria
transversal.

Implementacion:

```text
codigo/app/services/transversal_memory_audit.py
codigo/scripts/audit_transversal_memory_run.py
codigo/tests/test_transversal_memory_audit.py
```

La auditoria comprueba:

- que los recuerdos citados por el agente aparecian en el contexto recuperado;
- que cada recuerdo citado tiene una declaracion `memory_record_uses`;
- que los recuerdos recuperados corresponden al agente y dataset esperados;
- que el evaluador no aprueba por memoria, sino por metricas actuales;
- si el candidato resultante puede reutilizarse como contexto;
- si requiere revision humana antes de tratarse como evidencia academica
  principal.

Comando ejecutado sobre la run Qwen:

```text
python -m codigo.scripts.audit_transversal_memory_run \
  --run-id cwru-memory-transversal-fase4-002-llm
```

Artefactos generados:

```text
codigo/reports/cwru_bearing/cwru-memory-transversal-fase4-002-llm/agent_memory/audit/transversal_memory_audit.json
codigo/reports/cwru_bearing/cwru-memory-transversal-fase4-002-llm/agent_memory/audit/transversal_memory_audit.md
```

Resultado:

- resultado global: `memory_aligned`;
- `structurer`: cito el recuerdo recuperado de la run
  `cwru-memory-transversal-fase4-001` y declaro uso `adapted`;
- `evaluator`: cito el recuerdo recuperado de la run
  `cwru-memory-transversal-fase4-001` y declaro uso `adapted`;
- el evaluador quedo respaldado por metricas actuales: recall `1.0000` y FPR
  `0.0513`, con umbrales `0.9000` y `0.1000`;
- los candidatos pueden reutilizarse como contexto, pero requieren revision
  humana antes de presentarse como evidencia principal.

Estado de verificacion:

- `python -m py_compile codigo/scripts/run_cwru_pipeline_with_memory.py codigo/scripts/audit_transversal_memory_run.py codigo/app/services/transversal_memory_audit.py`;
- `python -m unittest codigo.tests.test_transversal_memory_audit`;
- `python -m unittest codigo.tests.test_transversal_memory_audit codigo.tests.test_graph_pipeline`;
- `python -m unittest discover codigo/tests`: `226` tests correctos.

Siguiente paso natural:

- decidir si se crea una revision humana ligera para estos dos candidatos
  CWRU, o si se mantienen como contexto no principal;
- preparar una comparacion breve con y sin memoria transversal, dejando claro
  que en CWRU el valor esperado es trazabilidad de decisiones, no mejora
  metrica.

## Planificacion comun multi-dataset para futuras interfaces

Tras revisar `codigo/docs/27_diseno_soporte_multidataset.md`, se ha corregido
la direccion operativa: el script CWRU con memoria queda como atajo canonico de
experimento, pero la arquitectura para API/interfaz debe ser un runner comun
que planifica y valida datasets de forma explicita.

Implementacion inicial:

```text
codigo/app/schemas/pipeline_run.py
codigo/app/services/pipeline_runner.py
codigo/scripts/run_dataset_pipeline_with_memory.py
codigo/tests/test_pipeline_runner.py
```

La nueva capa introduce:

- `PipelineRunRequest`, contrato que puede construir una CLI, API o UI;
- `DatasetRunPolicy`, politica de capacidades por dataset;
- `DatasetCapabilityRule`, con estados `allowed`, `blocked` o
  `not_supported`;
- `DatasetPipelinePlan`, plan auditable antes de ejecutar;
- rutas canonicas por `dataset_id/run_id`;
- alias neutrales del grafo (`run_pipeline`, `run_and_persist_pipeline`) sin
  eliminar los nombres historicos CWRU.

Comportamiento validado:

- CWRU con `adapter_id=cwru_bearing` permite manifiesto, perfilado, limpieza,
  estructuracion, modelado, evaluacion, reporting y memoria;
- NASA IMS real/preextraido permite modo `diagnostic` hasta estructuracion;
- NASA IMS en modo `full` bloquea `modeling` y `evaluation` si no se declara
  `allow_synthetic_labels=true`;
- un `adapter_id` que no coincide con `dataset_id` falla antes de ejecutar;
- el runner comun puede mostrar el plan con `--plan-only`, que es el mismo
  patron que deberia usar una futura interfaz.

Ejemplos de humo ejecutados:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id cwru_bearing \
  --adapter-id cwru_bearing \
  --raw-path codigo/data/raw/cwru_bearing/mat \
  --run-id plan-cwru-smoke \
  --plan-only
```

Resultado: `can_execute_requested_stages=true`.

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id plan-nasa-full-smoke \
  --plan-only
```

Resultado: `can_execute_requested_stages=false`, con bloqueos en `modeling` y
`evaluation`.

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id plan-nasa-diagnostic-smoke \
  --execution-mode diagnostic \
  --plan-only
```

Resultado: `can_execute_requested_stages=true`, limitado a manifiesto,
perfilado, limpieza y estructuracion.

Verificacion focalizada:

- `python -m py_compile codigo/scripts/run_dataset_pipeline_with_memory.py codigo/app/services/pipeline_runner.py codigo/app/schemas/pipeline_run.py`;
- `python -m unittest codigo.tests.test_pipeline_runner`.
- `python -m unittest discover codigo/tests`: `226` tests correctos.

Siguiente paso natural:

- conectar el endpoint `POST /runs` o un endpoint de preflight a
  `plan_dataset_pipeline_run(...)`;
- mantener los scripts `cwru_*` y `nasa_*` como reproduccion de experimentos,
  pero hacer que la app use el runner comun.

## Validacion del runner comun

Se ha ejecutado la validacion de no regresion antes de avanzar hacia API/UI.

Run CWRU completa:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id cwru_bearing \
  --adapter-id cwru_bearing \
  --raw-path codigo/data/raw/cwru_bearing/mat \
  --run-id cwru-runner-common-validation-fase4-001
```

Resultado:

- `completed`, aprobada, sin errores;
- precision `0.9991497803599263`;
- recall `1.0`;
- F1 `0.9995747093847462`;
- FPR `0.05128205128205128`;
- metricas identicas a `cwru-memory-transversal-fase4-001` y
  `cwru_iforest_threshold_v1_baseline_threshold_099`.

Run NASA IMS diagnostic:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id nasa-runner-common-diagnostic-fase4-001 \
  --execution-mode diagnostic
```

Resultado:

- `completed`, sin errores;
- metricas `null` y evaluacion `null`;
- solo ejecuto `dataset_manifest`, `data_profiler`, `cleaning` y
  `structuring`;
- artefactos: manifiesto, perfil, senales limpias, log, features, tensores y
  splits;
- no genero modelo, predicciones ni metricas.

Plan NASA IMS full:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id nasa-runner-common-full-block-check-fase4-001 \
  --plan-only
```

Resultado:

- `can_execute_requested_stages=false`;
- bloqueos declarados en `modeling` y `evaluation`.

Conclusion:

El runner comun queda validado como base de seleccion multi-dataset: no cambia
CWRU, permite diagnostico NASA y bloquea evaluacion supervisada NASA sin
politica temporal. A partir de esta base se pudo crear una operacion de
preflight consultable por API antes de abrir ejecuciones remotas completas.

## API controlada y Human Review inicial

Se ha implementado el siguiente paso logico sobre el runner comun: una primera
operacion `POST /runs` para planificar y, si se solicita explicitamente, ejecutar
una run desde API con guardarrailes.

Implementacion:

```text
codigo/app/schemas/api_runs.py
codigo/app/services/api_run_jobs.py
codigo/app/services/human_review.py
codigo/app/api/app.py
codigo/app/api/routes.py
codigo/tests/test_api_runs.py
codigo/docs/34_api_ejecucion_controlada_fase4.md
```

La API reutiliza contratos existentes en lugar de duplicar logica:

- `ApiRunRequest` extiende `PipelineRunRequest`;
- el plan se obtiene con `plan_dataset_pipeline_run(...)`;
- la ejecucion real usa `run_dataset_pipeline(...)`;
- los jobs locales usan `ApiRunJobStore` y no sustituyen los snapshots;
- Human Review reutiliza `HumanReviewSettings` y `HumanApproval`;
- la puerta comun vive en `human_review_gate_for_plan(...)`.

Comportamiento actual:

- `dry_run=true` por defecto devuelve el plan y no ejecuta;
- `raw_path` queda limitado a raices permitidas (`codigo/data/raw` por defecto);
- un `run_id` ya existente responde `409`;
- una politica de dataset bloqueante responde `409` si se intenta ejecutar;
- `use_llm=true` y memoria RAG desde API siguen deshabilitados;
- `human_review.mode=off` no interviene;
- `human_review.mode=passive` devuelve razones y un `HumanApproval` no bloqueante;
- `human_review.mode=required` bloquea la ejecucion salvo que llegue
  `human_approval.approved=true`;
- si hay aprobacion, se inserta en el estado inicial y queda persistida en el
  snapshot de la run;
- `background=true` con `dry_run=false` responde `202` y permite consultar
  `GET /run-jobs/{job_id}`;
- si el job completa, la run queda disponible en `GET /runs/{run_id}`;
- si falla, el job queda como `failed` con detalle del error.

Verificacion:

```text
python -m py_compile codigo/app/services/human_review.py codigo/app/schemas/api_runs.py codigo/app/services/pipeline_runner.py codigo/app/api/routes.py codigo/tests/test_api_runs.py
python -m unittest codigo.tests.test_api_runs
python -m unittest discover codigo/tests
```

Resultado actual: `241` tests correctos.

Interpretacion:

El hito de API queda iniciado con una frontera pequeña pero real para futura UI.
La revision humana ya existe como gate trazable, no como cola completa de
aprobaciones. La ejecucion en segundo plano queda cubierta de forma local e
inicial; todavia no es una cola persistida ni soporta cancelacion.
