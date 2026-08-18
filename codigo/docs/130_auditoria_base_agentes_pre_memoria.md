# Auditoria base de agentes antes de evaluar la memoria

Fecha de apertura: 2026-08-03. Ultima actualizacion: 2026-08-10.

## Decision

La evaluacion del efecto de la memoria RAG queda temporalmente subordinada a una
auditoria previa de la capa agentica. Antes de comparar una ejecucion con y sin
memoria hay que demostrar que cada rol puede emitir una decision valida, que su
procedencia queda registrada y que una finalizacion tecnica no oculta una caida
al respaldo determinista.

El codigo actual incorpora un contrato comun de hipotesis para los siete roles.
La hipotesis deja de ser un texto exclusivo del modelador: cada decision nueva
debe declarar que sostiene el agente, sobre que alcance, que espera observar y
que la refutaria. El campo solo permanece opcional en el esquema base para
poder leer snapshots historicos; los validadores de los agentes lo exigen en
las emisiones nuevas.

La conclusion de validacion actual distingue capacidad contractual, ejecucion
real y contraste cientifico:

> El gate vigente con Qwen 3.5 produjo 45 decisiones efectivas validas en el
> primer intento logico sobre 15 escenarios repetidos tres veces. Cubrio los
> nueve puntos de entrada y el contrato comun de los siete roles, sin segunda
> llamada LLM, fallback, overlay, decision no agentica, fallo semantico ni error.
> La normalizacion conservadora del servidor completo taxonomia y envoltura en
> seis salidas del verificador, sin cambiar su veredicto. La run CWRU posterior
> registro sus 18 decisiones como `llm`, `validated` e intento 1 y mostro las
> siete fichas con hipotesis efectivas completas. Es una puerta de ingenieria y
> una prueba de instrumentacion: no estima una tasa universal del 99 %, no
> contrasta la verdad de las hipotesis y no demuestra utilidad de la memoria RAG.

## Reutilizacion aplicada

Capacidad buscada:

```text
Auditar por rol hipotesis, evidencias, validacion, reparaciones, fallbacks y
relacion entre propuesta agentica y configuracion ejecutada.
```

Inventario previo:

- `run_persistence.py` ya era el propietario del evidence pack y de
  `execution_audit.md`;
- `AgentObservabilityView.tsx` ya era el propietario de la visualizacion del
  runtime agentico;
- `reasoning_audit.py`, `memory_usage_audit.py` y
  `transversal_memory_audit.py` cubren auditorias especializadas, pero no el
  estado base de todos los roles;
- `decisions.json` conserva las decisiones completas, aunque los snapshots
  historicos no incluyen el origen de generacion ni los intentos rechazados.

Decision: `extend` para persistencia y frontend. Este documento es `new` porque
resume evidencia transversal de multiples runs y fija el criterio de aceptacion
previo a memoria; no sustituye la auditoria individual generada para cada run.

## Dos resultados que no deben confundirse

### Exito operativo

Indica que el grafo termino, los ejecutores produjeron artefactos y los
guardarrailes mantuvieron el contrato. Un fallback puede contribuir a este
resultado. Por tanto, `completed` no significa que todas las decisiones hayan
salido del LLM ni que hayan sido correctas al primer intento.

### Exito agentico

Exige conocer para cada decision efectiva:

- el rol y el objetivo de la decision;
- la hipotesis operativa, obligatoria en toda decision nueva, y su tipo;
- que observacion la apoyaria y que criterio permitiria refutarla;
- su alcance, corte causal, supuestos, riesgos y referencias de evidencia;
- las alternativas consideradas;
- las evidencias citadas y, por separado, las herramientas realmente observadas;
- si la salida fue LLM valida, LLM reparada, determinista solicitada, fallback o
  sustitucion por protocolo;
- el intento que produjo la decision y la causa exacta del fallback;
- que configuracion llego al ejecutor y que resultado produjo.

No se pretende almacenar razonamiento interno libre ni cadenas de pensamiento.
La auditoria se limita a hipotesis falsables, decisiones estructuradas,
alternativas, evidencias, errores de validacion y configuraciones efectivas.

## Contrato comun de hipotesis

`AgentHypothesis` constituye la unidad comun que comparten supervisor,
limpiador, estructurador, modelador, evaluador, redactor y verificador. No
contiene una cadena de pensamiento. Conserva un resultado auditable mediante:

- `kind`: clase de hipotesis asociada a la responsabilidad del rol;
- `statement`: afirmacion concreta que el agente propone contrastar;
- `scope`: conjunto de datos, fase o artefacto al que se limita;
- `evidence_cutoff`: limite causal de la informacion disponible al decidir;
- `expected_observation`: resultado observable compatible con la hipotesis;
- `falsification_criterion`: resultado que la contradice;
- `evidence_refs`: referencias concretas usadas para formularla;
- `risk_notes`: amenazas que pueden invalidar la interpretacion;
- `assumptions`: supuestos declarados, cuando sean necesarios.

La decision conserva aparte su accion, justificacion, confianza, alternativas,
procedencia y `decision_kind`. Esta ultima distincion permite separar, por
ejemplo, modelado inicial de reintento y borrador de informe de revision sin
inventar agentes nuevos.

### Hipotesis que aporta cada rol

- El supervisor formula una hipotesis `routing_readiness`: el estado actual
  contiene los prerrequisitos para avanzar hacia un nodo concreto, o bien para
  detenerse.
- El limpiador formula una hipotesis `data_quality`: la politica propuesta
  reducira defectos observados sin destruir continuidad ni senal util.
- El estructurador formula una hipotesis `temporal_representation`: ventanas,
  particiones y escalado conservaran estructura relevante sin fuga temporal.
- El modelador formula una hipotesis `model_performance`, tambien en el
  reintento: la familia y configuracion elegidas produciran un comportamiento
  medible en datos retenidos bajo el corte causal declarado.
- El evaluador formula una hipotesis `operational_acceptance`: la evidencia
  disponible basta, o no basta, para sostener su veredicto operativo.
- El redactor formula `report_grounding` al crear el borrador: el informe puede
  cubrir resultados y limitaciones sin afirmaciones no respaldadas. Cuando
  revisa, formula `revision_effectiveness`: los cambios resolveran las
  incidencias sin introducir afirmaciones nuevas sin evidencia.
- El verificador formula una hipotesis `report_fidelity`: el estado final que
  asigna al informe esta respaldado por el catalogo cerrado de evidencias.

En datasets NASA con vista `online_blind`, estas hipotesis deben respetar la
separacion entre entrenamiento base, calibracion y monitorizacion retenida. No
pueden usar el fallo futuro, el onset fisico real ni un RUL retrospectivo como
evidencia disponible en el momento de decidir.

## Exito tecnico y contraste cientifico

Una accion ejecutada correctamente solo demuestra que el ejecutor pudo aplicar
la configuracion. No confirma la hipotesis que motivo la decision. Tampoco una
run `completed`, una metrica calculada o un informe generado bastan por si solos
para rotularla como apoyada.

El contrato conserva la hipotesis *ex ante*. Su contraste debe enlazar despues
observaciones independientes de la ejecucion y podra clasificarla como apoyada,
parcialmente apoyada, refutada, inconclusa o no evaluable. Mientras no exista
esa evaluacion persistida, la web la presenta expresamente como `pendiente de
contraste`. El frontend ya reconoce esos estados, pero no los deduce del campo
`success` de un ejecutor ni de texto libre.

## Inventario historico disponible

La inspeccion local encontro:

- 77 runs con 1.140 decisiones persistidas;
- 61 runs terminadas y 16 fallidas;
- 40 runs que recorren los siete roles y disponen de evidence pack;
- 32 de esas 40 con verificacion final `approved`;
- 7 con verificacion final `needs_revision` y 1 con `blocked`, pese a figurar
  como `completed`.

Esta evidencia sirve para detectar problemas, pero no para estimar una tasa
actual de fallback. El corte historico de 75 runs anterior a la nueva
instrumentacion no conserva un fichero de eventos runtime, un
`runtime_events_path` valido o `generation_trace` en sus decisiones. Las dos
runs incorporadas despues (`agent-trace-cwru-qwen35-20260806` y
`agent-hypothesis-cwru-live-20260810`) si conservan 30 eventos y traza de
generacion en sus 18 decisiones. En el bloque antiguo, los intentos invalidos
solo pueden inferirse por el texto de la justificacion.

Tampoco se persiste de forma suficiente el identificador exacto del modelo de
chat usado en cada run antigua; en muchos casos solo consta `use_llm=true`.

## Pilotos NASA causal v2 mas recientes

Los cuatro pilotos Qwen 3.5 de NASA IMS Set 2 contienen 76 decisiones. La
lectura textual identifica al menos 14 intentos LLM invalidos:

- supervisor: 1;
- estructurador: 2;
- modelador: 4;
- evaluador: 2;
- redactor: 3;
- verificador: 2;
- limpiador: ninguno identificable por texto.

La cifra es un minimo y debe rotularse como inferencia historica, no como medida
estructurada. Hay otras justificaciones que mencionan correcciones, pero la
evidencia guardada no permite atribuirlas con la misma seguridad.

Los patrones mas importantes son:

- el modelador cae al guardarrail en los cuatro pilotos por usar informacion
  retrospectiva incompatible con la vista `online_blind`;
- estructurador y evaluador caen en los dos pilotos con memoria por declaraciones
  incoherentes sobre el uso del contexto recuperado;
- las cuatro configuraciones de estructuracion y las cuatro de modelado fueron
  fijadas por la suite experimental: la propuesta del agente queda visible, pero
  no controla la ejecucion;
- dos informes terminan en `needs_revision` aunque la run quede completada.

Algunas causas de contrato ya se han corregido en el codigo actual. Esto no
demuestra que su frecuencia haya bajado: hace falta una nueva ejecucion
instrumentada y sin memoria para comprobarlo.

## Lectura por rol

### Supervisor

Invoca el LLM, repara transiciones invalidas y dispone de fallback. Su libertad
esta deliberadamente acotada por el grafo, por lo que se evalua por coherencia de
enrutamiento y procedencia, no por originalidad. La traza de generacion ya se ha
incorporado al codigo actual, pero no existe en los artefactos historicos. Cada
ruta nueva debe incluir una hipotesis `routing_readiness` que explicite que
prerrequisito permite la transicion y que observacion invalidaria esa lectura.

### Limpiador

Propone una configuracion que el ejecutor puede aplicar directamente. Conserva
justificacion y configuracion. En el contrato actual debe aportar ademas una
hipotesis `data_quality` con evidencia de entrada, cambio esperado y condicion
de refutacion; ya no se considera suficiente una justificacion narrativa de la
politica de calidad. Un primer intento semanticamente invalido recibe una ronda
de reparacion LLM dirigida por el error. Solo una segunda respuesta invalida
activa el fallback, que se registra como tercer intento.

### Estructurador

Puede declarar alternativas, usar memoria y separar propuesta de configuracion
efectiva mediante `protocol_trace`. En la suite canonica su propuesta queda
restringida por el protocolo. Tambien dispone ya de una reparacion LLM antes del
fallback, manteniendo los limites de ventanas, solapes, particion causal y
declaraciones de memoria. Su hipotesis `temporal_representation` debe anticipar
que propiedad conservara la representacion y que resultado revelaria fuga o
perdida de estructura.

### Modelador

Es el rol con mayor riqueza agentica: conserva hipotesis, evidencias, riesgos,
objetivos y alternativas. En una ejecucion libre puede seleccionar la familia de
modelo; en la suite comparativa la familia queda fijada para mantener el control
experimental. Los cuatro pilotos recientes revelaron una contradiccion del
contrato `online_blind`: se exigia citar
`policy:nasa_ims_run_to_failure_v2` y, a la vez, se rechazaba cualquier
referencia que contuviese `failure`. El codigo actual excluye unicamente las
referencias canonicas obligatorias de ese escaneo y sigue bloqueando evidencias
retrospectivas adicionales. Tanto la decision inicial como el reintento de
modelado disponen ya de reparacion LLM dirigida. Ambos deben emitir el bloque
comun `model_performance`; el antiguo texto interno de
`decision_strategy.hypothesis` solo se conserva como compatibilidad historica.

### Evaluador

Interpreta la evidencia y redacta un juicio, pero la aprobacion queda sometida a
reglas deterministas. Esto es una medida de seguridad, no autonomia completa.
Dispone de reparacion y traza estructurada en el codigo actual. Su hipotesis
`operational_acceptance` hace contrastable si las metricas y limitaciones
disponibles bastan para sostener el veredicto, sin convertir el propio veredicto
en prueba de que la hipotesis sea cierta.

### Redactor

Redacta el informe y puede repararlo tras una verificacion. La traza de
generacion se ha completado tanto para redaccion como para revision. El borrador
usa `report_grounding`; la revision usa `revision_effectiveness`, de modo que
una misma tarjeta de agente puede distinguir las dos responsabilidades mediante
`decision_kind`. Las referencias de evidencia siguen siendo escasas en parte
del corpus historico.

### Verificador

Combina juicio LLM con comprobaciones deterministas. Ya registra intentos,
reparaciones y fallback en el codigo actual. Queda un problema funcional de
prioridad alta: una verificacion final no aprobada puede coexistir con el estado
global `completed`. Su hipotesis `report_fidelity` debe estar limitada al
catalogo cerrado de evidencias y declarar que hallazgo cambiaria su
clasificacion.

## Cambios de auditabilidad aplicados

- `AgentHypothesis` unifica la afirmacion, alcance, corte causal, observacion
  esperada, criterio de refutacion, evidencias, riesgos y supuestos de todos los
  roles;
- los validadores de cada agente exigen el tipo de hipotesis que corresponde a
  su responsabilidad; la opcionalidad del esquema base existe unicamente para
  cargar snapshots anteriores;
- `decision_kind` distingue nueve clases de decision dentro de los siete roles,
  incluidos el reintento de modelado y la revision del informe;
- `DecisionGenerationTrace` cubre ahora supervisor, limpiador, estructurador,
  modelador, evaluador, redactor, revision del redactor y verificador;
- una traza declarada por el propio LLM se descarta y se sustituye por la que
  genera el sistema;
- se distinguen LLM valido, LLM reparado, determinista solicitado, fallback y
  restriccion de protocolo;
- el evidence pack conserva origen, intento, estado de validacion, causa de
  fallback, hipotesis, alternativas, evidencias y restriccion experimental;
- `execution_audit.md` separa estado operativo y estado agentico;
- el panel visual separa rutas del supervisor de decisiones tecnicas, muestra
  procedencia por rol y deja de presentar `protocol_trace` como prueba de
  ejecucion;
- el embudo RAG deja de ocupar el bloque principal de la auditoria base;
- todos los roles intentan reparar mediante el propio LLM una salida formal o
  semanticamente invalida antes de activar el respaldo determinista;
- el cliente Ollama envia ahora el esquema JSON completo en `format`, de modo
  que el contrato condiciona la generacion y no solo la validacion posterior;
- IDs, rutas, titulos canonicos y otros invariantes mecanicos son propiedad del
  servidor; el LLM conserva hipotesis, configuraciones, alternativas,
  evidencias y juicios semanticos;
- el verificador usa un expediente compacto con presupuesto explicito y
  conserva siempre conclusiones, limitaciones y evidencia prioritaria;
- cuando un guardarrail determinista completa una verificacion LLM se registra
  `policy_overlay_applied` y deja de presentarse como exito agentico autonomo;
- structurer y modeler reciben en modo `online_blind` una proyeccion causal de
  memoria sin texto libre, resultados, metricas ni outcome retrospectivo; las
  cautelas con grupos experimentales desconocidos no se inyectan.

## Que muestra la web de cada agente

Las vistas 2D y 3D consumen el mismo modelo tipado de decision e hipotesis. No
reconstruyen hipotesis buscando frases en `rationale`: el bloque comun es la
fuente autoritativa de las runs nuevas. Solo para snapshots antiguos del
modelador se admite la hipotesis legacy, rotulada como incompleta y no
evaluable.

La auditoria 2D es la vista de detalle. Para cada rol presenta:

- numero de decisiones e hipotesis y tipo de decision elegida;
- procedencia de la salida: intento logico 1 del LLM, reparacion, fallback, overlay o
  restriccion de protocolo;
- afirmacion de la hipotesis, observacion esperada y criterio de refutacion;
- alcance, corte causal y riesgos;
- referencias de evidencia, alternativas y herramientas declaradas en sus
  bloques separados;
- comparacion entre propuesta LLM y decision efectiva cuando el protocolo fija
  la configuracion;
- estado de contraste, que permanece como `pendiente de contraste` si no hay
  una evaluacion posterior enlazada.

La oficina 3D es una vista resumida y navegable, no una segunda semantica. Cada
mesa muestra actividad, numero de decisiones e hipotesis y, al enfocarla, la
hipotesis principal del agente, lo esperado, lo que la refutaria y su estado de
contraste. El detalle completo sigue perteneciendo al inspector 2D.

La escena no convierte decoracion en evidencia. Solo cuenta memoria cuando hay
identificadores de recuerdos realmente recuperados; solo cuenta herramientas
cuando existe una observacion de herramienta, no por estar declarada; y no
dibuja conversaciones causales entre agentes por mera proximidad temporal. Las
conexiones visibles se limitan a rutas exactas del supervisor. Un futuro mapa
3D de hipotesis--evidencia--resultado requerira identificadores y evaluaciones
causales persistidas, y no debe simularse antes de disponer de ellos.

## Limitaciones que siguen abiertas

- El contrato *ex ante* ya es comun, pero aun no existe una evaluacion
  independiente persistida para cada hipotesis. La web debe mantener el estado
  pendiente y no inferir apoyo a partir del exito tecnico del ejecutor.
- Las runs historicas anteriores a esta ampliacion no adquieren hipotesis por
  reconstruccion textual. En general solo el modelador conserva un texto legacy
  y faltan observacion esperada, criterio de refutacion y corte causal.
- Los eventos de operaciones causadas por una decision enlazan el
  `decision_id`; las operaciones sin causa decisional demostrable permanecen
  sin enlace en lugar de recibir una atribucion inventada.
- La captura de runtime exacta esta asociada al flujo background. En runs
  sincronas o historicas la API reconstruye una vista parcial desde decisiones
  y artefactos persistidos, y debe mantener visible ese origen reconstruido.
- Los nombres de herramientas incluidos por los agentes son declaraciones o
  propuestas. Mientras no exista una `AgentToolObservation` persistida no se
  contabilizan como herramienta ejecutada ni como evidencia consultada.
- La bateria `decision-only` no recorre el cierre global del grafo. Ese cierre ya
  se comprobo en una run CWRU completa, pero sigue pendiente repetirlo sobre la
  trayectoria NASA causal y ante perturbaciones no incluidas en el banco.
- El gate vigente cubre el contrato comun, pero contiene 15 escenarios cerrados
  repetidos tres veces. No es un banco holdout amplio ni permite extrapolar su
  ausencia de fallos a otros datasets, formatos, prompts o modelos.
- Los tests especificos de roles usan clientes LLM simulados: validan
  contratos, reparaciones y guardarrailes, no la robustez real de Qwen.

## Puerta agentica previa a una ejecucion completa

Una validacion end-to-end consume tiempo de LLM y de ejecutores, y puede ocultar
la causa de una caida. Por ello, las nuevas validaciones comienzan con un banco
`decision-only`: estados pequenos y congelados llaman a los agentes reales,
pero no transforman datos, entrenan modelos ni consultan memoria.

La clasificacion sera estricta:

- `first_pass`: decision LLM valida sin reparacion;
- `llm_repaired`: el LLM corrige JSON o contrato y produce la decision efectiva;
- `fallback`: el guardarrail sustituye al LLM; siempre es fallo de la puerta;
- `non_agentic`: decision determinista, desconocida o fijada por protocolo;
  tambien es fallo en esta auditoria;
- `semantic_failure`: el JSON valida, pero no satisface el oraculo cerrado del
  escenario; es fallo aunque el origen figure como LLM.

El primer gate requiere tres repeticiones del pack, trazas completas, cero
fallbacks, cero decisiones no agenticas, cero fallos semanticos, al menos 90 %
de first-pass y como maximo 10 % de reparaciones. Es una puerta de ingenieria
para autorizar una sola run real; no demuestra aun una tasa estadistica del
99 %.

La tasa debe informarse por decision y por flujo. Un flujo reciente contiene
unas 20 decisiones: incluso un 99 % de exito independiente por decision solo
implicaria aproximadamente un 81,8 % de ejecuciones sin ningun fallback. Para
alcanzar un 99 % por flujo de ese tamano haria falta aproximadamente un 99,95 %
por decision. Como referencia, 300 decisiones holdout sin fallos permiten
acotar aproximadamente por debajo del 1 % la tasa agregada de fallo con un
limite unilateral del 95 %.

El pack v1 contiene 15 escenarios sobre CWRU y NASA IMS y cubre nueve
callables: supervisor, cleaner, structurer, modeler, modeler retry, evaluator,
report writer, report reviser y report verifier. Se inspecciona sin llamar a
Ollama mediante:

```bash
python -m codigo.scripts.run_agent_decision_reliability --plan-only
```

La ejecucion real exige `--execute`; no hay una activacion implicita desde el
plan ni desde los tests.

## Cronologia de la validacion Qwen 3.5

Las primeras baterias de esta seccion corresponden al contrato anterior a
`AgentHypothesis`. Se conservan porque explican la evolucion de reparaciones,
fallbacks y guardarrailes. La ultima repeticion documentada ya usa el bloque
comun actual y constituye la referencia vigente.

### Ensayo de transporte excluido

Un primer lanzamiento registro 45 fallbacks, pero las llamadas terminaron en
milisegundos con `Operation not permitted`: el proceso aislado no podia abrir la
conexion local hacia Ollama. No hubo respuestas generadas por Qwen. Ese
artefacto se conserva para auditar el incidente de infraestructura, pero se
excluye del numerador y del denominador de fiabilidad del modelo.

### Primera bateria que alcanzo realmente Ollama

El 6 de agosto de 2026 se ejecuto el pack completo con `qwen3.5:4b`, tres
repeticiones de los 15 escenarios y memoria desactivada. De las 45 decisiones:

- 38 fueron validas al primer intento (84,44 %);
- 7 terminaron en fallback;
- no hubo decisiones no agenticas, fallos semanticos del oraculo ni errores de
  ejecucion;
- la cobertura de `generation_trace` fue del 100 %.

Los siete fallbacks no estuvieron repartidos por todo el sistema. Supervisor,
limpiador, estructurador, modelador, reintento del modelador, evaluador y
revision del informe alcanzaron el 100 % al primer intento en sus escenarios.
El verificador produjo seis fallbacks en seis casos y el redactor uno en tres.
Por tanto, el gate quedo bloqueado aunque 38 decisiones fuesen agenticas.

### Diagnostico y correcciones focales

La inspeccion de las respuestas revelo dos defectos de integracion distintos:

- el verificador devolvia contenido semantico util en un dialecto compacto con
  campos como `classification`, `issues` y `reasoning`; el normalizador no
  conservaba ese contenido y el contrato recibia listas de incidencias vacias;
- en el caso NASA, el control de afirmaciones del redactor podia interpretar
  una limitacion negada como si fuese una afirmacion fisica positiva.

Se corrigieron la normalizacion conservadora del verificador y el tratamiento
de negacion y alcance de las afirmaciones NASA. En una bateria focal posterior
de nueve decisiones desaparecieron los fallbacks: el redactor produjo dos
respuestas al primer intento y una reparada por el propio LLM. Los tres casos
seguros del verificador fueron aprobados al primer intento. En los tres casos
adversariales, sin embargo, un overlay determinista completo incidencias que la
salida no habia expresado con los identificadores canonicos; esos casos se
contabilizaron como fallos semanticos, no como exitos agenticos.

Una inspeccion posterior de las respuestas brutas confirmo que Qwen si habia
identificado tanto la afirmacion industrial no respaldada como la limitacion
ausente, pero habia elegido identificadores libres. Puesto que esos
identificadores son metadatos de trazabilidad y no parte del juicio semantico,
su canonizacion pasa a ser responsabilidad del servidor. Este cambio no altera
el veredicto ni inventa una incidencia.

Desde estas repeticiones focales, cada intento logico conserva la respuesta
estructurada recibida, su huella, la huella del esquema y la huella del prompt.
Asi puede auditarse que vio el validador en un intento rechazado sin almacenar
el prompt completo ni una cadena de pensamiento privada. Los artefactos
anteriores a esta ampliacion no adquieren retrospectivamente esa informacion.

### Repeticion completa final del contrato anterior: gate historico superado

La repeticion completa posterior a las correcciones se ejecuto sobre los mismos
15 escenarios, tres veces cada uno, con `qwen3.5:4b` y memoria desactivada. El
artefacto final registra:

- 45 observaciones;
- 42 decisiones validas al primer intento (93,33 %);
- 3 decisiones reparadas por el propio LLM: una en `modeler_retry` y dos en
  `report_verifier`;
- 0 fallbacks, 0 decisiones no agenticas, 0 fallos semanticos y 0 errores;
- 100 % de cobertura de traza y 100 % de exito agentico;
- 48 llamadas logicas y 48 llamadas fisicas. Las tres llamadas adicionales
  corresponden a las reparaciones generativas.

Las tres repeticiones completas superaron el flujo, y el gate emitio
`passed` sin bloqueos. El resultado demuestra que, dentro de aquel contrato y
pack cerrado, ninguna decision efectiva fue sustituida por una politica
determinista y que las reparaciones conservaron autoria LLM. No demuestra que
las respuestas satisfagan los campos de hipotesis incorporados despues.

Este es un gate de ingenieria, no una estimacion poblacional. Son 45
observaciones construidas a partir de 15 escenarios y tres repeticiones, no 45
activos independientes ni un banco holdout amplio. En su momento autorizo la
validacion end-to-end sin memoria del contrato anterior, pero por si mismo no
autorizaba una run bajo el esquema ampliado ni permitia afirmar una tasa general
del 99 % frente a datasets, perturbaciones o prompts no representados.

### Iteraciones de ajuste bajo el contrato comun

El gate vigente no fue la primera ejecucion del banco tras ampliar el contrato.
Dos baterias completas anteriores, sobre los mismos escenarios, se utilizaron
para diagnosticar la integracion:

- la primera termino con 35 decisiones en el intento logico 1, 3 reparadas por el
  LLM y 7 fallbacks;
- una repeticion posterior alcanzo 39 decisiones en el intento logico 1, 5 reparadas
  y un fallback concentrado en el reintento del modelador.

Ambas quedaron bloqueadas. Sus fallos guiaron ajustes de prompt, aliases
semanticos y validacion conservadora. Por tanto, la repeticion final no es un
holdout: mide el sistema corregido sobre el mismo banco conocido.

### Gate vigente con el contrato comun: repeticion final superada

Tras exigir `AgentHypothesis` en todos los roles y corregir los fallos focales
sin inventar evidencia, incidencias ni alterar el veredicto, se repitio el
mismo pack con `qwen3.5:4b`, memoria desactivada y tres vueltas completas. El artefacto canonico
`agent-reliability-hypotheses-qwen35-gate2-20260810` registra:

- 45 observaciones, correspondientes a 15 escenarios por 3 repeticiones;
- 45 decisiones efectivas validas en el primer intento logico y 45 llamadas
  logicas y fisicas;
- 0 reparaciones, 0 fallbacks, 0 decisiones no agenticas, 0 overlays, 0 fallos
  semanticos y 0 errores;
- 100 % de cobertura de traza y 3 de 3 flujos completos;
- 100 % al primer intento en `cleaner`, `evaluator`, `modeler`,
  `modeler_retry`, `report_reviser`, `report_verifier`, `report_writer`,
  `structurer` y `supervisor`;
- hipotesis efectiva completa y del tipo exigido por el rol en todas las
  decisiones tras normalizacion conservadora.

En las seis salidas del verificador, Qwen uso tipos de hipotesis no canonicos y
omitio campos de envoltura que son propiedad del servidor. El normalizador los
convirtio a `report_fidelity` y completo confianza y justificacion por defecto;
no cambio ningun veredicto ni anadio incidencias. En consecuencia,
`first_pass` significa una unica llamada LLM que produjo una decision efectiva
valida tras normalizacion sin cambio de juicio, no coincidencia literal del JSON
bruto con todas las claves del contrato persistente.

La figura `fiabilidad_agentes_contrato_hipotesis` representa el resultado por
punto de entrada con barras de ejes, no mediante una tabla. Su manifiesto enlaza
la imagen con el resumen y las 45 observaciones mediante huellas SHA-256.

El 100 % observado solo describe este banco cerrado. No permite afirmar una
tasa poblacional ni que las hipotesis sean correctas: el oraculo comprueba
contrato y coherencia del escenario, no su confirmacion cientifica posterior.

## Como se interpretan reparacion, fallback y overlay

- `first_pass`: la primera respuesta logica del LLM produce la decision
  efectiva y supera contrato y oraculo;
- `llm_repaired`: el propio LLM corrige una respuesta rechazada y sigue siendo
  el autor de la decision efectiva, aunque no cuenta como primer intento;
- `fallback`: el guardarrail determinista sustituye al LLM y bloquea el gate;
- `policy_overlay_applied`: la decision LLM existe, pero una politica
  determinista añade o endurece incidencias. Protege el resultado operativo,
  pero no demuestra autonomia del agente y se penaliza en esta puerta;
- `non_agentic`: la decision efectiva fue determinista o impuesta por
  protocolo y tampoco cuenta como exito agentico.

Estas categorias se calculan con campos estructurados. No se deducen buscando
palabras como "correccion" o "fallback" dentro de la justificacion.

## Primera run completa con el contrato comun

Tras superar el gate vigente se ejecuto la run
`agent-hypothesis-cwru-live-20260810` sobre CWRU, sin memoria y en modo
background, para validar la instrumentacion dentro del grafo real. El runtime
persistido contiene 30 eventos:

- 18 decisiones: 12 rutas del supervisor y 6 decisiones de roles tecnicos;
- 18 decisiones con origen `llm`, estado `validated` e intento logico 1;
- 0 segundas llamadas LLM registradas, 0 fallbacks, 0 overlays y 0 errores;
- 7 eventos de ejecutor;
- 4 enlaces causales exactos desde limpieza, estructuracion, modelado y
  redaccion hacia su resultado de ejecutor;
- hipotesis comun completa en las 18 decisiones y participacion observable de
  supervisor, limpiador, estructurador, modelador, evaluador, redactor y
verificador.

La run conserva el origen logico, pero no un manifiesto de inferencia con el
nombre exacto del modelo ni el numero de llamadas fisicas. Por ello acredita que
el runtime no registro reparacion generativa ni fallback; no se usa para
atribuir de forma reproducible esas 18 respuestas a una version concreta de
Qwen ni para descartar una reparacion JSON interna no expuesta en la traza.

Los tres ejecutores restantes no recibieron un enlace inventado: corresponden a
operaciones deterministas que no dependen de una decision previa equivalente.
El modelador eligio Isolation Forest y conservo tres alternativas con efecto
esperado. El verificador aprobo el informe y el supervisor respeto el veredicto
antes de cerrar la run como completada.

Las fichas 2D y la oficina 3D consumen el mismo objeto persistido. Para cada rol
muestran enunciado, observacion esperada, criterio de refutacion, alcance, corte
de evidencia, riesgos, supuestos y referencias propias. Todas permanecen
rotuladas como `pendiente de contraste`: ningun resultado de ejecutor se
convierte automaticamente en confirmacion de una hipotesis.

Aunque el runtime incluye eventos que registran el intento de recuperar
contexto para estructurador, modelador y evaluador, la solicitud tenia memoria
desactivada: no se recuperaron recuerdos, ninguna decision declaro usarlos y el
resultado no se utiliza como evidencia a favor del RAG. Del mismo modo, los
nombres de herramientas siguen siendo declaraciones; la vista mantiene como
limite visible que no existe una observacion de ejecucion equivalente.

Las capturas web exactas se conservan junto a los artefactos. El panel de
auditoria distingue procedencia, primer intento, reparacion, fallback, overlay,
hipotesis, alternativas y enlace al ejecutor sin recurrir a inferencias
textuales. La oficina 3D muestra la misma hipotesis y su refutador al seleccionar
un rol; sus lineas representan rutas explicitas del supervisor y no relaciones
causales inventadas. Este smoke valida la base CWRU y la captura runtime; no
sustituye una nueva run NASA causal bajo el contrato vigente ni autoriza por si
solo una ablacion de memoria.

## Criterio de aceptacion previo a memoria

Una nueva run de referencia sin memoria sera apta para iniciar la comparacion RAG
cuando cumpla, como minimo:

1. participacion esperada de los siete roles;
2. `generation_trace` presente en todas las decisiones;
3. hipotesis comun presente en todas las decisiones nuevas, con tipo correcto,
   afirmacion, alcance, corte causal, observacion esperada, refutacion,
   evidencias y riesgos;
4. las siete fichas 2D y sus resumenes 3D muestran esas hipotesis sin inferirlas
   desde la justificacion;
5. cualquier hipotesis sin evaluacion independiente aparece como pendiente, no
   como confirmada por el mero exito del ejecutor;
6. fallback y reparacion contabilizados por campos estructurados, nunca por
   busqueda textual;
7. propuesta restringida claramente separada de configuracion ejecutada;
8. resultado del ejecutor enlazado a la decision o rotulado como no demostrable;
9. verificacion final aprobada, o run no presentada como cierre correcto;
10. memoria desactivada para no confundir robustez base con efecto RAG.

No se aceptara una run con fallback como evidencia del comportamiento agentico,
aunque termine y sus artefactos sean correctos. La ejecucion CWRU descrita
cumplio los diez criterios y valida la instrumentacion con memoria desactivada.
El siguiente gasto de ejecucion se dedica a NASA causal, escenarios holdout y
perturbaciones pequenas antes de iniciar pares con/sin memoria o la comparacion
posterior con Qwen 3.

## Siguiente orden de trabajo

1. ampliar el banco con escenarios holdout, perturbaciones pequenas y un tercer
   formato para medir robustez fuera de los 15 escenarios conocidos;
2. ejecutar una run NASA causal v2 sin memoria y verificar especialmente el
   corte `online_blind`, la unidad snapshot y las hipotesis de los siete roles;
3. incorporar una valoracion independiente que contraste observacion esperada,
   refutador, accion efectiva y resultado sin usar el exito del ejecutor como
   atajo;
4. congelar un corpus pertinente y juicios de relevancia antes de reanudar la
   comparacion RAG con Qwen 3.5;
5. repetir mas adelante el mismo protocolo con Qwen 3, sin cambiar contratos,
   prompts, memoria ni datos entre modelos.
