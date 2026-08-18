# Decision de backend y ciclo de memoria RAG para el estudio run-to-failure

Fecha de revision: 2026-08-03.

## Alcance

Este documento fija el siguiente bloque de trabajo sin reabrir las fases 10 y
11. El objetivo cientifico no es la base vectorial ni la interfaz: es observar
como los agentes formulan hipotesis, usan o rechazan experiencias anteriores y
revisan sus decisiones en un escenario industrial run-to-failure.

La capacidad implementada en este bloque se resume asi:

> Automatizar un ciclo de memoria auditable sin promocion autorreforzada:
> captura, gobierno persistente, indexacion reconstruible, recuperacion con
> procedencia y control determinista de calidad, inyeccion acotada y auditoria
> de la influencia declarada y de la ejecucion efectiva.

## Decision revisada: no migrar a pgvector ni fijar Qdrant todavia

No se adopta pgvector como respuesta a la indisponibilidad actual de Qdrant, ni
se fija Qdrant como backend obligatorio del benchmark. La comprobacion del
entorno encontro que el servicio Qdrant no esta disponible porque Docker no
esta integrado en esta sesion WSL; tampoco hay un servicio PostgreSQL/pgvector
instalado. Cambiar el codigo de backend no resolveria por tanto el bloqueo
operativo y, sobre todo, no crearia los recuerdos pertinentes que faltan en el
corpus.

La decision inmediata es mantener el contrato independiente del motor, usar la
busqueda JSON exacta como baseline operativo y exigir un preflight explicito al
backend elegido. Qdrant y una futura implementacion pgvector solo se compararan
con un corpus congelado, las mismas consultas, el mismo embedding y juicios de
relevancia independientes. No se afirma que ninguno sea universalmente
superior ni "el estado del arte".

La arquitectura queda separada en dos capas:

- los contratos Pydantic, episodios y candidatos JSON son la evidencia
  canonica, auditable y exportable;
- JSON, Qdrant o pgvector son indices derivados y reconstruibles para
  recuperacion;
- JSON local permanece como baseline exacto y reproducible;
- `VectorMemoryStore` conserva la posibilidad de incorporar pgvector sin
  cambiar los agentes.

Qdrant sigue siendo un candidato razonable porque el proyecto ya lo integra y
la recuperacion necesita
filtros por agente, dataset, rol, veredicto y estado de reutilizacion. Sus
indices de payload y HNSW filtrable estan documentados en
<https://qdrant.tech/documentation/manage-data/indexing/>. Qdrant tambien
permite consultas hibridas y multietapa, aunque no se incorporaran hasta medir
primero el baseline dense: <https://qdrant.tech/documentation/search/hybrid-queries/>.

pgvector sigue siendo una alternativa razonable si la industrializacion futura
introduce PostgreSQL como propietario transaccional de runs, decisiones,
revisiones, usuarios y estados de aprobacion. pgvector ofrece busqueda exacta,
HNSW e IVFFlat y se combina con filtros SQL; sus diferencias operativas estan
descritas en su documentacion oficial: <https://github.com/pgvector/pgvector>.
Introducir PostgreSQL ahora aumentaria infraestructura y migracion sin demostrar
una mejora de relevancia. Sera coherente reconsiderarlo si la industrializacion
posterior convierte PostgreSQL en propietario transaccional del resto del
sistema.

## Hallazgos que cambian la prioridad

### Memoria RAG

Antes de este bloque existian casi todas las piezas, pero no formaban un ciclo
operativo unico:

- la interfaz enviaba `use_memory=true`, pero la API rechazaba la ejecucion;
- el runner y el grafo ya aceptaban `PipelineMemoryConfig`;
- Qdrant recuperaba candidatos amplios y filtraba despues en Python, sin usar
  filtros de payload en el servidor;
- el quality gate se calculaba solo en benchmarks offline;
- API, curacion e indexacion abrian explicitamente un store JSON aunque la run
  usara Qdrant;
- los candidatos nuevos podian quedar marcados como reutilizables por defecto,
  aun sin veredicto humano ni validacion independiente.

La inspeccion inicial del indice mostro 20 de 20 registros reutilizables, 19 sin
veredicto humano y 9 procedentes de auditorias de uso de memoria. Tras aplicar
la nueva politica y reconstruir el baseline local quedaron 23 registros
indexados, pero solo uno reutilizable: el postmortem revisado por una persona.
Los 13 candidatos historicos se conservan indexados como no reutilizables y
cuarentenados, y las 9 auditorias de uso quedan como observaciones no
recuperables. El cambio conserva la evidencia sin convertirla en contexto.

La primera pasada pareada sobre Set 2 confirmo una limitacion del corpus, no un
beneficio de memoria. En PCA e Isolation Forest, la condicion con retrieval
recupero para el modelador el mismo unico recuerdo reutilizable, con similitud
0,5576. El registro era un caso frontera de un piloto etiquetado, con metricas
de precision, recall, F1 y FPR y procedencia/perfil desconocidos. Ningun agente
lo cito ni declaro uso y los dos benchmarks quedaron en `retrieval_only`, con
configuraciones y metricas identicas a sus pares sin memoria.

El artefacto original lo habia clasificado como `caution`. La auditoria motivo
una regla general adicional: si las metricas de un recuerdo revelan un perfil
binario y no existen señales run-to-failure compatibles, se excluye de una
consulta oficial sin etiquetas por snapshot. El benchmark recalculado lo marca
como `exclude_candidate`. No se ha promocionado ningun recuerdo nuevo para
forzar un resultado positivo.

### NASA IMS y run-to-failure

Los pilotos disponibles siguen siendo evidencia de integracion y no una
validacion cientifica sobre NASA IMS real. La base causal oficial, en cambio,
ya se ha ejecutado como estudio descriptivo de una trayectoria. Se han cerrado
las siguientes carencias estructurales:

- NASA IMS Set 2 esta extraido: 984 snapshots, cuatro canales y 544.618.480
  bytes;
- un sidecar canonico vincula la URL NASA admitida, el archivo de
  1.075.597.174 bytes y SHA-256
  `21001ac266c465f5d345ec42d7b508c6a6328487fd9d4d7774422dd5ea10ad83`
  con el inventario extraido y su tree SHA-256
  `aaa5210f0052a5b3ad33c47daff8395c2ea7a879b436aa3032e3eb82c0d14ebe`;
- el adaptador solo declara procedencia `official` si verifica de nuevo toda
  esa cadena; ausencia implica `unknown` e incoherencia implica error;
- las ventanas de una adquisicion se agregan antes de persistencia y metricas
  longitudinales mediante `snapshot_aggregation_v1`;
- tres ventanas positivas de una unica captura producen una racha de un
  snapshot y no una persistencia ficticia de tres instantes.
- `nasa_ims_run_to_failure_v2` fija 197 snapshots de baseline, 98 de
  calibracion y 689 de monitorizacion sin imponer una etiqueta de degradacion;
- el umbral se obtiene exclusivamente de 1.862 ventanas de calibracion y el
  tramo de monitorizacion queda fuera de su ajuste;
- los 983 intervalos de Set 2 son exactamente de 600 segundos, no hay gaps y la
  politica reinicia persistencia y suavizado causal cuando aparezcan;
- la vista `online_blind` elimina de limpiador, estructurador, modelador y sus
  herramientas las etiquetas y campos retrospectivos; el evaluador solo los
  recibe despues de cerrar las decisiones.

La run determinista de referencia proceso 18.696 ventanas y 984 snapshots. El
score presenta Spearman 0,794 con el avance temporal y el Health Indicator pasa
de 93,02 a 1,90. La primera alerta algoritmica persistente aparece al 65,8 % de
la trayectoria, unas 56 horas antes del final registrado. Estos valores no son
validacion de un onset fisico: calibration y monitoring carecen de ground truth,
por lo que precision, recall, F1, ROC-AUC y PR-AUC no se publican.

## Ciclo canonico de memoria

El ciclo objetivo queda fijado asi:

```text
decision del agente
  -> episodio y candidato trazables
  -> candidato pendiente (no reutilizable)
  -> validacion de resultado y procedencia
  -> promocion, cautela o exclusion
  -> indexacion en el backend configurado
  -> recuperacion filtrada
  -> quality gate de relevancia/perfil
  -> contexto efectivo para el agente
  -> cita, adaptacion, rechazo o ignorado explicitos
  -> auditoria del efecto y nueva evidencia
```

Reglas iniciales:

1. Capturar episodios es automatico.
2. Capturar no equivale a promocionar.
3. Un candidato nuevo queda con `reusable_as_context=false` por defecto.
4. Un recuerdo `unsafe`, contradicho, incompatible o excluido nunca llega al
   prompt.
5. El contexto bruto, el resultado del gate y el contexto efectivo se guardan
   por separado.
6. El agente solo puede citar identificadores realmente presentes en el
   contexto efectivo.
7. El filtrado local se conserva como defensa aunque Qdrant filtre en servidor.
8. La promocion automatica se habilitara solo tras definir evidencia suficiente;
   una unica ejecucion correcta no debe crear una verdad autorreforzada.
9. Una auditoria de uso de memoria nunca se recupera como leccion: describe el
   uso de otros recuerdos y realimentarla generaria bucles autorreferenciales.
10. Una promocion queda ligada al hash exacto del candidato revisado. Si cambia
    el artefacto fuente, la promocion anterior deja de ser valida.
11. Un contexto puede quedar trazado aunque el agente declare que no influyo;
    en ese caso no se permiten IDs citados, resúmenes de influencia ni usos por
    registro.
12. Un recuerdo con evidencias binarias incompatibles con el perfil causal
    v2 se excluye aunque coincidan dataset y agente.

La promocion futura debera distinguir como minimo:

- validacion humana correcta;
- leccion repetida en runs independientes;
- evidencia soportada pero todavia provisional;
- warning o caso frontera reutilizable solo como cautela;
- contradiccion, contaminacion de benchmark o procedencia no comparable.

## Cambios funcionales de este bloque

Se han extendido propietarios existentes; no se ha creado un runner, contrato o
backend paralelo:

- `api/routes.py`: ensambla la configuracion RAG en ejecuciones sincronas y de
  background;
- `api/app.py` y `memory_registry.py`: comparten el `VectorMemoryStore`
  configurado para listar, curar, borrar y ejecutar;
- `graph/pipeline.py`: aplica el quality gate en vivo y persiste evidencia bruta
  y efectiva;
- `vector_memory.py`: envia filtros de payload a Qdrant, crea indices de payload
  idempotentes y conserva la validacion defensiva local;
- `reasoning_memory_index.py`: se adapta para indexar mediante el store
  configurado, manteniendo compatibilidad con el baseline JSON;
- `experiment_protocol.py`: el modelador del protocolo restringido conserva la
  hipotesis, citas y uso de memoria del agente aunque la familia de modelo quede
  fijada para comparabilidad.
- `memory_registry.py`: mantiene un ledger append-only de promocion, exclusion,
  restauracion y borrado, con motivo, revisor, tombstones y hash de fuente;
- `dataset_adapters.py`: verifica de forma fail-closed la procedencia de NASA
  IMS oficial y propaga evidencia al descriptor, manifiesto y estado;
- `nasa_ims_temporal_policy.py` y `pipeline_runner.py`: materializan la politica
  causal v2 con particiones exactas y labels desconocidas fuera del baseline;
- `online_blind.py`, agentes y `agent_tools.py`: filtran de forma recursiva
  cualquier clave futura antes de una decision causal;
- `evaluation.py` y `temporal_health_policy.py`: reducen ventanas a snapshots,
  segmentan gaps y publican aliases neutrales para v2; una alerta algoritmica no
  se presenta como fallo fisico confirmado;
- los contratos de estructuracion y modelado separan propuesta del agente,
  restricciones aplicadas y configuracion realmente ejecutada.
- `agent_decisions.py` y `agent_memory.py`: distinguen contexto observado de
  memoria influyente; un agente puede ignorar correctamente un contexto sin
  activar un fallback, pero no puede citar recuerdos que declare no usados;
- `agent_decisions.py` y los cuatro agentes de decision: incorporan origen,
  intento, estado de validacion y enlace de fallback estructurados por la
  aplicacion; cualquier metadato de procedencia forjado por el LLM se descarta;
- `reasoning.py`, `state.py`, `decision_memory.py` y `memory_quality_gate.py`:
  propagan aplicabilidad tipada (perfil, etiquetas, frecuencia, trayectoria,
  grupo de evaluacion y alcance de transferencia), excluyen fugas de benchmark
  y recurren a tags solo para artefactos legacy;
- `memory_registry.py` y la API: publican un diagnostico `/memory/status` que
  separa disponibilidad del motor, inventario gobernado y preparacion
  cientifica, con huella semantica y bloqueos explicitos;
- `report_verifier.py`: impone coherencia entre estado, incidencias y
  correcciones, evitando `needs_revision` o `blocked` vacios;
- `run_registry.py`, `experiment_protocol.py` y
  `memory_effect_benchmark.py`: publican para v2 aliases neutrales de alerta
  persistente, intervalo al final registrado y tasa premonitorizacion, sin
  presentar `before_failure`, `lead_time` o metricas binarias como evidencia;
- `experiment_protocol.py`: ofrece una suite v2 clasica con PCA, Isolation
  Forest y One-Class SVM; el autoencoder queda bloqueado hasta disponer de
  readiness causal suficiente.
- `experiment_protocol.py`: materializa tambien una puerta pre-Qwen de quince
  requisitos que diferencia capacidad disponible, prueba no ejecutada y
  evidencia superada; el dictamen actual permanece `BLOCKED`.
- la suite v2 persiste en planes futuros un manifiesto con modelo LLM, modo de
  razonamiento, timeouts, backend, embedding y top-k, sin hosts ni secretos.
- `validation_figures.py`: genera figuras academicas desde artefactos
  persistidos y acompana cada PDF con hashes de entrada y salida. Se crea como
  frontera nueva porque las visualizaciones de la aplicacion son interactivas y
  no existia un propietario para graficos estaticos reproducibles de la memoria.

Los candidatos generados por API y por runners quedan pendientes de revision por
defecto. La API expone cola y decisiones de curacion con motivo y revisor
obligatorios. La recuperacion persiste por separado el pool bruto, el resultado
del gate y el contexto efectivo, incluyendo recuentos y causas de descarte.
Esto cierra el bucle de recuperacion y observacion sin activar todavia una
realimentacion automatica insegura.

La compatibilidad del embedding tambien se valida como contrato. Modelo,
version, dimension y distancia deben coincidir con la coleccion; una diferencia
falla de forma explicita en lugar de comparar vectores incompatibles. El
baseline local se reconstruyo con `qwen3-embedding`, version `0.6b` y 1.024
dimensiones, y se verifico una consulta real contra Ollama.

## Metricas obligatorias del RAG

La evaluacion no se limitara a comparar F1. Debe separar cuatro niveles:

1. Recuperacion: `hit@k`, `recall@k`, `precision@k` por rol, MRR y tasa de
   incompatibilidades filtradas.
2. Fidelidad: citas existentes, citas inventadas, recuerdos ignorados y
   consistencia entre cita y explicacion de influencia.
3. Comportamiento: cambio de hipotesis, configuracion, confianza, alternativas,
   revisiones y rechazo explicito del contexto.
4. Resultado: deltas de metricas operacionales run-to-failure, tasa de ayuda,
   tasa de perjuicio, latencia y coste de contexto.

La busqueda exacta debe ser el baseline cientifico. HNSW se evaluara aparte como
estudio de latencia/escalabilidad para no confundir aproximacion del indice con
calidad del razonamiento.

## Estado del protocolo run-to-failure v2

La base causal necesaria para el benchmark agentico queda cerrada:

1. Procedencia `official|synthetic|unknown` separada de la fuente de etiquetas.
2. Set 2 verificado, Bearing 1 y channel 1 como caso monocanal inicial.
3. `snapshot_aggregation_v1` antes de cualquier metrica longitudinal.
4. `temporal_gap_v1`, con reinicio de persistencia y suavizado ante intervalos
   superiores a 900 segundos.
5. Particiones `baseline_train`, `calibration` y `monitoring` materializadas
   mediante reparto determinista 20/10/70.
6. Sin target binario en calibracion o monitorizacion y sin metricas binarias
   fabricadas.
7. Vista `online_blind` sin EOL, `relative_life`, `time_to_failure` ni modo de
   fallo; vista retrospectiva solo despues de cerrar decisiones.
8. Umbral calibrado unicamente en `calibration`, sin fallback a monitoring.

El diagnostico pareado inicial con dos familias ya esta ejecutado. Mostro
retrieval sin uso y detecto un recuerdo incompatible, por lo que no constituye
la ablacion principal. El siguiente bloque ya no modifica la base causal: debe
construir y congelar un corpus pertinente, ejecutar replicas agenticas con Qwen
3.5 y auditar hipotesis y uso efectivo antes de comparar con Qwen 3. Los
resultados sinteticos continúan separados de la evidencia NASA oficial.

## Estado de verificacion de este bloque

- Regresion Python: 483 tests correctos y uno omitido.
- Build de produccion del frontend correcto; solo permanece el aviso no
  bloqueante de un chunk WebGL superior a 500 kB.
- Baseline local de memoria reconstruido: 23 registros, uno reutilizable, 13
  candidatos historicos en cuarentena y 9 auditorias no recuperables.
- Procedencia NASA IMS Set 2 verificada sobre los datos extraidos reales.
- Agregacion temporal por snapshot validada con casos deterministas, incluido
  el control de pseudorreplicacion.
- Consulta local con el embedding real validada mediante Ollama.
- Sonda no generativa posterior: el backend JSON recupero un registro con
  `ollama:qwen3-embedding:0.6b`; el control causal recupero `1`, excluyo `1` por
  conflicto de perfil/procedencia incierta y entrego `0` al contexto efectivo.
  El artefacto queda en
  `codigo/reports/validation/rag_memory_probe/rag_memory_probe.json`.
- Dos pares PCA/Isolation Forest ejecutados con memoria off/retrieval on: una
  recuperacion por par, cero citas, cero usos y cero deltas de configuracion o
  metricas.
- El piloto uso `local_json_vector_memory_store` con
  `ollama:qwen3-embedding:0.6b`; no aporta evidencia de ejecucion Qdrant.
- La version Qwen configurada no quedo persistida en los artefactos historicos
  del piloto; el nuevo manifiesto de ejecucion corrige el gap para futuras
  runs.
- La forma de los filtros y payloads Qdrant esta cubierta por tests, pero no se
  ha ejecutado un smoke contra servidor en este cierre porque el servicio no
  estaba disponible. Al iniciar Qdrant debe reconstruirse el indice derivado y
  comprobarse la consulta real antes del benchmark.

## Diseno experimental posterior

Con el protocolo v2 congelado, la comparacion minima sera factorial y con
replicas:

- modelo de agente: Qwen 3.5 frente a Qwen 3;
- memoria: off, retrieval sin inyeccion, memoria filtrada y, si procede,
  memoria completa;
- mismas entradas, semillas, contratos, presupuesto de contexto y ejecutores;
- decisiones evaluadas a ciegas ademas de metricas del sistema.

El protocolo de familia de modelo fija configuraciones para comparabilidad, pero
debe conservar la hipotesis, evidencia, citas y confianza emitidas por el
agente. Una suite con configuraciones hardcodeadas no demuestra por si sola que
la memoria mejore la seleccion del agente.

## Consecuencias para la memoria academica

La memoria del TFM debe sostener solo afirmaciones acordes con la evidencia:

- el motor vectorial es una decision de ingenieria reemplazable; JSON es el
  baseline actual y Qdrant/pgvector deben superar un preflight y una comparacion
  congelada antes de fijarse;
- la aportacion original es el ciclo de decision-memoria auditable y su efecto
  en agentes bajo run-to-failure;
- las runs sinteticas actuales validan contratos, trazabilidad y ejecucion;
- los resultados NASA se reservaran para el protocolo real por snapshot;
- cada tabla experimental debe indicar dataset, procedencia, unidad temporal,
  modelo Qwen, modo de memoria, corpus/hash, embedding y politica de retrieval.
