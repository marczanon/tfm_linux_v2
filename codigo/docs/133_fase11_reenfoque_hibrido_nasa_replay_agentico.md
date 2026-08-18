# Fase 11: reenfoque hibrido NASA con replay y supervision agentica

Fecha: 2026-08-11.

Estado: hoja de ruta activa. Sustituye como guia inmediata el alcance amplio de
`128_fase11_hoja_ruta_industrializacion_agentica_event_driven.md`, que se
conserva como propuesta historica de industrializacion posterior.

## Idea central del TFM

> Una plataforma hibrida que combina monitorizacion determinista continua con
> supervision multiagente periodica y dirigida por eventos, capaz de disenar,
> adaptar y auditar politicas de deteccion antes de su despliegue industrial.

Esta frase expresa el ideal de producto. El resultado demostrable dentro del
TFM sera mas acotado: experimentar y auditar offline propuestas de politica
sobre replay NASA, sin afirmar que el prototipo este listo para desplegarse.

Resumen operativo:

```text
Determinismo para vigilar.
Agentes para interpretar y proponer cambios.
Contratos, validacion y trazabilidad para confiar.
```

## Decision de alcance

La siguiente fase no intentara resolver todavia:

- adaptacion a datasets externos;
- conectores industriales reales;
- cola distribuida, Redis o Celery;
- despliegue cloud o multiusuario;
- streaming de tiempo real duro;
- RUL industrial;
- automatizacion autonoma de mantenimiento.

El alcance queda fijado en NASA IMS oficial y en una simulacion visual de
monitorizacion mediante replay cronologico. La aplicacion recorrera snapshots
historicos como si fueran llegando progresivamente, mantendra el detector y la
politica operativa de forma determinista y activara la run multiagente actual
en revisiones periodicas o ante eventos significativos.

La expresion correcta en memoria y web sera:

```text
monitorizacion continua simulada mediante replay historico acelerado
```

No se presentara como ingesta industrial en tiempo real. Que la interfaz se
actualice en vivo no demuestra latencia, disponibilidad, backpressure ni
integracion con sensores de una instalacion.

## Piloto cientifico congelado

El primer escenario se identificara como `NASA-RTF-HYB-01`: un piloto
retrospectivo y descriptivo que reutilizara la evidencia oficial ya verificada
del Set 2. Esta trayectoria ya fue inspeccionada en fases anteriores, por lo
que no se presentara como holdout ni como confirmacion preregistrada.

- 984 snapshots con cuatro canales sincronizados;
- 197 snapshots de `baseline_train`;
- 98 snapshots de `calibration`;
- 689 snapshots de `monitoring`;
- cadencia historica nominal de 600 segundos;
- trayectoria modelada actualmente: `set_2/channel_1`, asociada al rodamiento
  1 y al evento final documentado del ensayo.

La unidad del piloto es esa trayectoria/ensayo. Los snapshots, episodios,
canales y repeticiones Qwen estan correlacionados y no se trataran como
replicas independientes. No se calcularan p-values ni intervalos poblacionales
usando 689 snapshots como si fueran 689 activos.

En esta hoja, `causal` significa que ningun calculo, trigger o agente accede a
los valores del sufijo posteriores a su cutoff, usando una particion historica
ya congelada. El reparto 20/10/70 se construyo conociendo la longitud total del
registro; por tanto, no equivale a un arranque prospectivo que desconoce la
duracion futura ni a una afirmacion de inferencia causal.

Los otros tres canales pueden mostrarse como contexto sensorial sincronizado,
pero no recibiran score, HI o diagnostico hasta que exista para cada uno un
bundle determinista propio. La interfaz mostrara `telemetria sin modelo` en vez
de copiar el estado del canal principal. Las tarjetas de activos se derivaran
del manifiesto; no se codificaran cuatro rodamientos de forma fija.

## Relacion con la Fase 11 anterior

La hoja `128` ya propuso una industrializacion event-driven mucho mas amplia:
streams, cola persistente, workers, datasets no vistos, automatizacion general
y Docker extendido. La idea arquitectonica sigue siendo valida, pero excede la
pregunta cientifica y el tiempo disponible del TFM.

Decision de reutilizacion:

```text
adaptar el nucleo de 128 + diferir su infraestructura expansiva
```

Se mantienen de `128`:

- separacion entre scoring frecuente y decisiones agenticas;
- replay historico como sustituto honesto de una fuente viva;
- triggers con cooldown, histeresis y deduplicacion;
- decisiones estructuradas y ejecutores deterministas;
- revision humana y evidencia persistida;
- compatibilidad con las runs batch actuales.

Se difieren:

- `QueueJob`, worker persistente y dead-letter;
- XJTU-SY, MIMII y cualquier cold-start externo;
- MQTT, OPC-UA, Kafka y hardware;
- automatizaciones industriales generales;
- servicios Docker adicionales que no sean necesarios para la demo NASA.

## Punto de partida real

Ya existen capacidades que no deben duplicarse:

- `nasa_ims_temporal_policy.py`: manifiesto y particion causal NASA IMS;
- `temporal_health_policy.py`: agregacion por snapshot, gaps, persistencia,
  Health Index, Risk Index y estados;
- ejecutores de limpieza, estructuracion y modelado;
- `pipeline_runner.py` y `graph/pipeline.py`: run multiagente canonica;
- `api_run_jobs.py`: ejecucion local no bloqueante de una run;
- `AgentRuntimeEvent`: traza incremental de agentes y ejecutores;
- `run_persistence.py` y `run_registry.py`: persistencia y consulta;
- `human_review.py`: puerta humana ya existente;
- `RunVisualizationData`, `TemporalRunSeries` y graficas temporales 2D;
- `IndustrialScene3D`: escena industrial opcional;
- `AgentStoryModel` y la sala `Cree-Elige-Recuerda-Ocurre`;
- gate Playwright de la historia agentica.

Carencias actuales:

- no existe un cursor de replay ni una sesion persistida;
- 2D y 3D muestran la trayectoria completa y su estado final;
- el frontend usa solo la primera trayectoria disponible;
- los rodamientos 3D son decorativos y no tienen identidad causal;
- no existe enlace exacto `snapshot -> trigger -> run agentica -> politica`;
- la run actual vuelve a leer el dataset completo y filtraria futuro si se
  lanzara sin una vista causal;
- no existe ciclo de vida versionado de una politica de monitorizacion.

## Principios no negociables

1. La run multiagente actual se extiende; no se crea otro grafo.
2. Los siete agentes conservan hipotesis y decisiones trazables.
3. El monitor no llama al LLM por cada snapshot.
4. El scoring, los estados y los triggers son deterministas.
5. Cada revision agentica recibe un corte inmutable `<= cursor`.
6. Nunca se recalculan particiones 20/10/70 sobre un prefijo creciente.
7. El modelo, scaler y umbral iniciales se ajustan una vez con las particiones
   permitidas y quedan congelados al iniciar monitorizacion.
8. Una politica nueva solo puede aplicarse desde el snapshot siguiente; nunca
   reescribe el pasado.
9. Una propuesta agentica no se convierte automaticamente en politica activa.
10. Recuperar memoria no equivale a usarla ni a mejorar una decision.
11. La vista 2D es canonica; el 3D es una metafora sincronizada opcional.
12. El final registrado no se presenta como onset fisico ni RUL.
13. El frame y los triggers en el cursor `i` deben ser invariantes si se elimina
    o sustituye cualquier sufijo posterior a `i`.
14. Ningun calculo online usa longitud final, vida relativa, tiempo al final,
    normalizacion global ni estadisticas del sufijo futuro.

## Arquitectura objetivo acotada

```text
NASA IMS oficial
  -> bootstrap causal 20/10/70 ya versionado
  -> ScoringPolicyBundle: features + scaler + modelo + umbral + salud
  -> AgentActivationPolicy: periodicidad + triggers + presupuesto
  -> MonitoringReplaySession
       -> execution_cursor historico autoritativo
       -> inferencia determinista por snapshot
       -> ledger append-only por rodamiento
       -> Health Index / Risk Index / estado
       -> TriggerEngine
            -> evento periodico o significativo
            -> CausalInputView <= cursor
            -> run multiagente hija existente
                 -> hipotesis y memoria
                 -> propuesta de politica
                 -> frozen_benchmark: registrar sin aplicar
                 -> adaptive_replay_exploratory:
                      validacion + Human Review cuando proceda
                      -> activacion en application_cursor + 1
  -> sala de monitorizacion 2D/3D
  -> historia agentica e informe bajo demanda
```

El replay tendra variables temporales diferenciadas:

- `source_time`: timestamp historico de NASA;
- `replay_elapsed`: tiempo virtual transcurrido dentro de la simulacion;
- `speed_multiplier`: relacion entre tiempo fuente y avance visual;
- `runtime_time`: tiempo real consumido por backend, Qwen y frontend.

La periodicidad cientifica se expresara en snapshots o tiempo historico, no en
segundos de pared. La web mostrara estas variables sin mezclarlas.
El tiempo fuente sera la referencia visual principal; la velocidad de replay
aparecera junto a los controles y la duracion runtime solo dentro de la
revision agentica.
Si la fuente no declara zona horaria, la UI rotulara `tiempo del dataset, sin
zona declarada` en vez de inventar UTC o tiempo local.

La sesion tendra dos cursores distintos:

- `execution_cursor`: backend, monotono, persistido y fuente de verdad;
- `inspection_cursor`: seleccion visual que puede retroceder, pero nunca
  superar al cursor de ejecucion.

El frontend solo envia comandos y recibe confirmacion del backend. El primer
mecanismo de actualizacion sera polling incremental por secuencia; React no
sera el reloj de la sesion. Recargar la pagina reconstruira el cursor de
ejecucion y permitira restaurar la inspeccion sin repetir frames ni triggers.

`inspection_cursor` sera estado de vista restaurable desde la URL o estado
local, siempre acotado al cursor autoritativo. `follow_execution` seguira el
ultimo tick; si el usuario inspecciona el pasado se desactiva y aparece la
accion `Volver al actual`, aunque el backend continue avanzando.

## Dos modos experimentales separados

### Modo A: `frozen_benchmark`

Es el experimento principal y defendible:

- la politica inicial permanece congelada durante monitoring;
- los agentes interpretan, diagnostican y proponen;
- las propuestas se registran, pero no alteran el scoring de la trayectoria;
- se comparan politicas de activacion con el mismo presupuesto maximo `B`
  predeclarado;
- al cerrar se abre el post-mortem retrospectivo.

Este modo permite medir eficiencia de triggers, fiabilidad agentica y calidad
de hipotesis sin confundirlas con una adaptacion online del detector.

### Modo B: `adaptive_replay_exploratory`

Es la demostracion de la vision del producto:

- una propuesta pasa por contrato, validacion y, si se configura, aprobacion;
- se crea una version inmutable con referencia a la decision que la origino;
- se activa solo desde el snapshot posterior al cursor real de aplicacion;
- la grafica marca el punto exacto de cambio;
- las metricas se segmentan por version de politica.

Este modo puede mostrar cambios reales en umbral, persistencia o agenda de
revision, pero no se usara para afirmar mejora causal general del detector sin
un experimento posterior preregistrado y retenido.

Comparar segmentos vistos por versiones diferentes sera solo descriptivo:
cada version observa una fase temporal distinta de la degradacion y no existe
intercambiabilidad causal entre esos segmentos.

## Ciclo hibrido completo

### 1. Bootstrap

- verificar procedencia y hashes del conjunto NASA elegido;
- congelar fronteras baseline, calibration y monitoring;
- preparar features y ajustar scaler/modelo solo con baseline;
- calibrar umbral solo con calibration;
- producir `ScoringPolicyBundle v1` y `AgentActivationPolicy` por separado;
- registrar modelos, configs y artefactos por hash.

### 2. Monitorizacion determinista

Por cada tick/snapshot visible:

- leer solo la observacion correspondiente al cursor;
- ejecutar inferencia con el bundle activo;
- calcular score, ratio contra umbral, HI, riesgo y estado;
- aplicar persistencia, histeresis y resets por gaps;
- guardar una fila append-only con `asset_id`, snapshot y version de scoring;
- actualizar la sala de monitorizacion.

Un paso produce un lote atomico de frames con un unico `source_time`. Si hay
varios canales/activos visibles, todos se proyectan sobre el mismo snapshot;
cambiar el activo seleccionado nunca cambia el instante inspeccionado.
El TriggerEngine se ejecuta una sola vez despues de cerrar ese lote, nunca en
mitad del recorrido de sus canales.

### 3. Disparo agentico

Triggers iniciales permitidos:

- revision periodica con calendario congelado;
- entrada en alerta persistente;
- transicion a `warning` o `critical`;
- gap que invalida continuidad;
- cierre de sesion;
- solicitud manual trazada para la demo.

Preflight, cierre y trigger manual se contabilizaran aparte. El trigger manual
queda excluido de las comparaciones cientificas entre politicas.

No se implementaran todavia drift ni desacuerdo de modelos hasta que exista un
detector determinista que les de semantica verificable.

Controles contra tormentas:

- una sola run hija activa por sesion;
- clave de deduplicacion por evento;
- cooldown por tipo de trigger;
- coalescing de eventos compatibles;
- prioridad para criticidad;
- reanudacion sin repetir triggers ya confirmados.

La maquina de estados de cada trigger registrara `emitted`, `suppressed`,
`coalesced`, `dispatched`, `running`, `resolved` o `failed`. La politica P3
versionara antes de abrir monitoring la racha de entrada, la racha de
recuperacion/salida, cooldown en tiempo fuente, precedencia, coalescing y regla
de rearme.

La demo inicial usara `guided_replay`: al despachar una run hija se pausa de
forma explicita el cursor de ejecucion para poder inspeccionarla. Un modo
`continuous_simulation` posterior podra seguir avanzando y coalescer nuevos
eventos, sin presentarlo como garantia de operacion industrial.

### 4. Revision multiagente

La run hija reutilizara el grafo actual, pero su entrada sera una vista causal
inmutable y no el directorio raw completo.

Cada rol mantiene una aportacion reconocible:

- `supervisor`: encuadra el evento, enruta y cierra la revision;
- `cleaner`: formula hipotesis sobre calidad sensorial, faltantes o ruido;
- `structurer`: revisa orden temporal, ventanas, gaps y continuidad;
- `modeler`: juzga modelo, umbral y estrategia permitida;
- `evaluator`: interpreta degradacion, persistencia y consecuencias;
- `report_writer`: sintetiza el incidente o revision;
- `report_verifier`: contrasta claims, evidencia y limites.

El primer gate `monitoring_review` convocara los siete roles para verificar su
hipotesis y trazabilidad con el mismo contrato. Despues podra optimizarse el
routing por `review_kind`, pero `requested_roles` y `required_roles` quedaran
congelados y auditados. A lo largo de la sesion, la traza mostrara con
precision quien intervino en preflight, evento y cierre.

### 5. Propuesta y aplicacion

Primer catalogo cerrado de acciones:

- mantener politica;
- intensificar observacion o adelantar la siguiente revision;
- ajustar persistencia dentro de un rango preregistrado;
- proponer ajuste acotado de umbral;
- solicitar revision humana;
- pausar la simulacion guiada;
- rechazar el cambio por evidencia insuficiente.

Quedan fuera del primer incremento:

- cambiar arbitrariamente de modelo;
- reentrenar con monitoring sin un protocolo independiente;
- modificar el manifiesto, las particiones o la procedencia;
- ejecutar codigo generado por el LLM.

Toda aplicacion conserva:

```text
trigger_id
  -> child_run_id
  -> decision_id
  -> proposal_id
  -> validation_id
  -> human_approval opcional
  -> target_policy_kind + old/new version
  -> application_cursor
  -> effective_from_cursor = application_cursor + 1
```

En `frozen_benchmark` la cadena termina en propuesta validada/no aplicada. La
aprobacion y activacion pertenecen exclusivamente a
`adaptive_replay_exploratory`.

La aplicacion usara una precondicion sobre la version padre y una clave de
idempotencia. Si Qwen o la revision humana terminan despues de que el replay
haya avanzado, se captura atomicamente el cursor de aplicacion; nunca se usa el
cursor antiguo del trigger. En `guided_replay`, ambos coincidiran porque la
sesion estara pausada.

## Contratos minimos

Antes de servicios o endpoints se definiran contratos Pydantic cerrados.

### `ReplaySessionConfig` y `ReplaySessionState`

- config inmutable: sesion, dataset, manifiesto, hashes, trayectoria y activos;
- `execution_cursor`, secuencia/revision y estado
  `ready/running/paused/completed/failed`;
- modo `manual/accelerated`;
- velocidad de replay;
- `ActivePolicyRefs {scoring_version, activation_version}`;
- ultimo trigger y runs hijas;
- checkpoint y version de esquema.

El estado/checkpoint mutable incluira ademas, por activo, persistencia,
smoothing, segmento, ultimo timestamp y version aplicada. Guardar solo el
cursor no basta para reanudar de forma bit a bit.

### `CausalInputView`

- registros visibles hasta el cursor;
- cutoff temporal y particiones congeladas;
- whitelist positiva de campos y evidencias permitidas;
- referencias de artefactos y SHA-256;
- prohibicion de longitud final, EOL, vida relativa, fallo y metricas futuras.

El manifiesto administrativo completo permanece fuera del payload visible por
agentes. La seguridad causal no dependera de una blacklist de nombres.

### `ReplayTick` y `MonitoringFrame`

- `tick_id`, cursor, snapshot, tiempo fuente e `input_record_hash`;
- lote completo de frames antes de evaluar triggers;
- `frame_id`, `tick_id`, `asset_id`, canal y segmento;
- `analysis_status = modeled/telemetry_only/unavailable`;
- score, umbral, HI, riesgo y estado opcionales cuando no hay modelo;
- `scoring_version`;
- refs de evidencia.

`ReplayTick` sera tambien el contrato de transporte: un snapshot historico,
una secuencia y cero o mas frames de activos/canales declarados por el
manifiesto. Esto evita que las tarjetas representen tiempos diferentes.

### `MonitoringTriggerEvent`

- tipo, prioridad y razon determinista;
- activo, rango de snapshots y cutoff;
- estado anterior y nuevo;
- politica de cooldown/deduplicacion;
- `origin_tick_id`, `frame_ids`, dedupe key y hash de la politica de trigger;
- `activation_version`, estado lifecycle, secuencia y timestamps;
- referencia a evento suprimido/coalescido y `child_run_id` cuando existan;
- expediente causal asociado.

### `ScoringPolicyBundle`

- especificacion inmutable, version, hash y artefactos;
- feature schema, scaler, modelo y artefactos;
- umbral, persistencia, smoothing y reglas de gap;
- reglas de reset declaradas.

### `AgentActivationPolicy`

- version y hash separados del scoring;
- calendario periodico o maquina de triggers;
- presupuesto maximo y unidad de coste;
- mapping congelado de trigger a roles;
- cooldown, prioridad, coalescing y rearme;
- llamadas fijas de preflight/cierre separadas de llamadas variables.

Esta separacion permite comparar P0--P3 sin afirmar que cambio el detector.

### `MonitoringReviewRequest`

- `causal_view_ref` y hash;
- sesion, trigger, cursor y `ActivePolicyRefs`;
- `review_kind`, `requested_roles` y `required_roles`;
- capabilities cerradas `no_fit/no_retrain/no_raw_scan/propose_only`;
- snapshot de memoria elegible o memoria desactivada;
- hashes de prompt, esquema y opciones permitidas.

Este modo extiende el runner y el grafo actuales. No vuelve a limpiar el raw,
recalcular particiones ni entrenar con monitoring.

### `PolicyProposal`, `ValidationRecord` y `ApplicationRecord`

Separan recomendacion agentica, comprobacion determinista y mutacion efectiva.
El exito de una ejecucion no confirma por si solo la hipotesis que la motivo.
El estado `candidate/validated/approved/active/retired`, el intervalo efectivo
y los resets aplicados viven aqui y en el timeline de sesion, no dentro del
bundle inmutable. `ValidationRecord` diferencia validacion estructural,
causalidad y seguridad de eficacia: aprobar una politica no demuestra mejora.

Cada propuesta/aplicacion declara `target_policy_kind = scoring/activation`,
version anterior y nueva. `ValidationRecord` incluye `validation_cursor`, refs
y hashes de evidencia, version de validador/esquema y cumple:

```text
max(evidence_cutoff) <= validation_cursor <= application_cursor
```

Una evaluacion que use el sufijo se marca `postmortem_only` y no puede producir
un `ApplicationRecord`.

### `HypothesisOutcomeAssessment`

- `hypothesis_id` y `decision_id` originales;
- cutoff que vio el agente;
- observacion esperada y criterio de refutacion congelados;
- evidencia posterior permitida y sus refs;
- resultado `supported/partially_supported/contradicted/inconclusive/not_evaluable`;
- metodo y evaluador `deterministic` o `human_blinded`;
- fecha y hash del assessment.

El mismo LLM autor no sera el juez de su hipotesis. Un resultado de ejecutor
correcto acredita ejecucion, no apoyo a la hipotesis.

### `MemoryEligibilityPolicy`

El primer experimento ejecutara memoria OFF. Un incremento RAG posterior
debera versionar `corpus_snapshot_hash` y excluir:

- recuerdos de la misma trayectoria con cutoff posterior al cursor;
- post-mortems, EOL y metricas retrospectivas del monitoring activo;
- registros sin linaje dataset/trayectoria/cutoff demostrable.

Se anadira un future-bait especifico para memoria antes de cualquier ablacion
OFF/ON. Hasta entonces, la UI mostrara honestamente `sin retrieval` y no se
afirmara utilidad de RAG.

## Persistencia

La nueva responsabilidad justificada sera un servicio pequeno de replay, no un
segundo pipeline. Directorio candidato:

```text
codigo/reports/monitoring_sessions/<session_id>/
  session.json
  ticks.jsonl
  triggers.jsonl
  policy_versions/
  causal_views/
  child_runs.json
  session_report.json
```

El ledger sera append-only, con una linea o commit durable por `ReplayTick`
completo. El tick se cierra y valida primero en memoria; el TriggerEngine se
evalua una vez sobre ese tick cerrado y tick, triggers, checkpoint y estado se
co-persisten despues en un unico commit atomico. Un reinicio debe reconstruir
cursor, triggers y versiones activas sin reescribir observaciones pasadas ni
aceptar medio tick.

`api_run_jobs.py` podra lanzar las runs hijas, pero no sera el reloj ni la
fuente de verdad de la sesion: sus jobs siguen viviendo en memoria.
Si el proceso reinicia con una run hija huerfana, el intento se marca
`interrupted`; un retry reutiliza request/trigger y queda trazado sin emitir de
nuevo el trigger ni fingir que el hilo anterior se reanudo.

## Sala de monitorizacion

### Vista 2D canonica

Primera lectura propuesta:

```text
[ REPLAY NASA · estado · tiempo fuente · velocidad · policy vN ]

[ activo modelado ] [ telemetria ] [ telemetria ] [ telemetria ]
    HI / riesgo      sin modelo     sin modelo     sin modelo

[ grafica grande: score + umbral + cursor + cambios de politica ]
[ grafica grande: Health Index + estados + gaps ]

[ anterior ] [ play/pausa ] [ velocidad ] [ siguiente trigger ]
[ rail: telemetria | trigger | run agentica | validacion | activacion ]
```

Las tarjetas se generan desde el manifiesto. Al seleccionar un rodamiento se
mantiene el mismo `source_time` y se actualizan las graficas/ficha solo si
existe un bundle propio; en caso contrario se muestra la telemetria disponible
y `sin modelo`. No se llamara sano a un rodamiento censurado; se mostrara
`sin evento final
documentado` cuando corresponda.

Los controles distinguen ejecucion e inspeccion. Retroceder el slider solo
mueve `inspection_cursor`; no rebobina ni muta la sesion. `Siguiente trigger`
significa avanzar causalmente hasta que se emita uno nuevo, no consultar ni
revelar un indice precalculado del futuro.

Cuando se active una revision:

- aparece un indicador de run agentica en curso;
- la monitorizacion y la revision conservan cronologias separadas;
- se puede abrir la historia actual de agentes sin perder la sesion;
- al terminar aparece un diff legible `politica vigente -> candidata`;
- el texto largo queda en `Informes` y `Auditoria`.

El rail diferencia visualmente triggers emitidos, suprimidos, coalescidos,
despachados, en curso, resueltos y fallidos. La navegacion hacia `Agentes`
conserva un contexto verificable:

```text
session_id + execution_cursor + inspection_cursor + trigger_id
  + child_run_id + agent_id + decision_id + event_id
```

Al volver se restaura el foco del trigger. Si no existe enlace a una decision
exacta, la interfaz declara que el enlace solo es a nivel de run.

### Vista 3D opcional

- representar el banco y los rodamientos con identidad real;
- actualizar color, halo y pulso desde el mismo `MonitoringFrame`;
- iluminar el activo que origino un trigger;
- enlazar la revision con la oficina de agentes como cinemática narrativa;
- no usar profundidad como metrica cuantitativa;
- mantener paridad completa en 2D, teclado y `prefers-reduced-motion`;
- actualizar materiales y cursor sin reconstruir Three.js en cada tick.

El 3D no inventara causalidad: una linea solo aparece si existe `trigger_id`,
`decision_id`, `scoring_version` o `activation_version` enlazado.

Paridad significa igualdad semantica de activo, frame, estado, trigger y
politica seleccionados, no interacciones identicas. Toda accion critica existe
como control HTML fuera del canvas. La cinematica sera opcional y saltable; con
movimiento reducido se eliminan vuelos, pulsos y bucles RAF continuos.

## Hoja de ruta de implementacion

Para no duplicar los hitos 11.1--11.11 de la propuesta historica, este
reenfoque se organiza en bloques A--I.

### Bloque A - Congelacion cientifica e inventario

Objetivo: fijar el escenario antes de escribir el replay.

Trabajo:

- seleccionar y fingerprintar el subconjunto NASA IMS oficial;
- congelar run de referencia, policy v2, modelo y Qwen;
- declarar memoria OFF en el primer experimento y diferir el corpus causal;
- congelar por separado `ScoringPolicyBundle` y presupuesto maximo `B`, cuya
  unidad primaria son runs hijas variables por trigger;
- excluir de `B` preflight y cierre, y medir aparte decisiones, llamadas
  logicas, llamadas fisicas, repairs y tokens disponibles;
- fijar que evidencias ve cada etapa antes de ejecutar la nueva comparacion
  agentica sobre el piloto ya conocido;
- declarar modos `frozen_benchmark` y `adaptive_replay_exploratory`;
- registrar decisiones `reuse/extend/new` por componente.

Cierre:

- manifiesto experimental versionado;
- cero discrepancias de procedencia;
- claims permitidos y prohibidos escritos.

### Bloque B - Replay determinista puro

Objetivo: recorrer monitoring snapshot a snapshot sin LLM ni frontend.

Trabajo:

- contratos de sesion, frame y bundle;
- separar bootstrap de inferencia incremental en ejecutores existentes;
- implementar `step()`, cursor, checkpoint y resume;
- cerrar cada `ReplayTick` multicanal de forma atomica;
- persistir ledger por activo y version;
- comparar resultado incremental con la referencia batch causal.

Cierre:

- mismos scores, HI, riesgo, estados, episodios y primer aviso;
- ningun snapshot perdido o duplicado;
- resume determinista;
- ninguna evidencia futura visible;
- score, frame y trigger invariantes al truncar cualquier sufijo futuro.

### Bloque C - Motor de triggers

Objetivo: generar eventos reproducibles sin llamar aun a Qwen.

Trabajo:

- maquina de estados de periodicidad, persistencia, severidad, gap y cierre;
- cooldown, coalescing, prioridad y deduplicacion;
- simulacion de cuatro politicas:
  - `P0`: observador determinista sin llamadas;
  - `P1`: demanda potencial por cada snapshot alertado, sin ejecutar Qwen;
  - `P2`: hasta `B` revisiones periodicas con calendario fijado a priori;
  - `P3`: persistencia + histeresis + eventos, con el mismo maximo `B`;
- congelar expedientes de trigger para QA agentico economico.

`B`, el calendario P2 y el mapping trigger--roles se fijan con
baseline/calibration o un escenario de desarrollo, antes de ejecutar la nueva
comparacion agentica sobre monitoring.
Si se iguala P2 al numero realizado por P3 despues de ver la trayectoria, se
rotulara como sensibilidad post-hoc y no como politica online preregistrada.

Cierre:

- cada evento se emite exactamente una vez;
- pausa/resume no duplica llamadas;
- P2 y P3 tienen presupuesto comparable;
- no se atribuye verdad fisica a episodios algoritmicos.

### Bloque D - API y control minimo de sesion

Objetivo: conectar el servicio de replay sin convertir React en scheduler.

Trabajo:

- crear/leer sesion y consultar revision autoritativa;
- comandos `step`, `play`, `pause`, velocidad y cierre con `command_id` y
  `expected_revision`;
- respuesta con `accepted_revision`, lock/CAS de sesion e idempotencia de
  servidor ante retry o doble clic;
- polling incremental de ticks, triggers y cambios por secuencia;
- control de concurrencia para descartar respuestas obsoletas;
- reload/resume y errores trazables;
- mantener `api_run_jobs.py` solo para runs hijas.

Cierre:

- el backend posee el reloj y el cursor de ejecucion;
- `step` y `play` simultaneos no pueden confirmar dos veces el mismo tick;
- ninguna peticion o render por frame de animacion;
- recarga sin duplicados ni perdida de estado;
- transporte incremental sin recargar el ledger completo.

### Bloque E - Replay visual 2D

Objetivo: obtener pronto una sala de monitorizacion usable.

Trabajo:

- nueva vista `Monitorizacion` dentro del frontend existente;
- selector de rodamiento/trayectoria;
- cursor causal, play/pausa, paso y velocidades;
- tarjetas dinamicas: estado para bundles modelados y `sin modelo` para el
  resto;
- graficas grandes de score/umbral, HI y estados;
- rail de triggers y politica;
- responsive y accesibilidad.

Cierre:

- en el frame `i` no aparece informacion de `i+1` en DOM, texto accesible,
  contadores, marcadores, recomendacion ni longitud final;
- todos los activos/canales declarados son seleccionables y muestran si
  disponen o no de modelo;
- cambiar activo conserva el mismo tiempo fuente;
- `Siguiente trigger` avanza causalmente y no consulta un indice futuro;
- funciona sin WebGL;
- no hay overflow en movil.

### Bloque F - Puente trigger a run multiagente

Objetivo: activar el sistema agentico actual con evidencia causal.

Trabajo:

- construir `CausalInputView` por whitelist;
- separar manifiesto administrativo de payload agent-visible;
- crear `MonitoringReviewRequest` propose-only;
- extender la entrada del runner sin volver a escanear el raw completo ni
  permitir fit/retrain;
- enlazar sesion, cursor, trigger, run, eventos y decisiones;
- usar single-flight inicialmente;
- ejecutar primero sin memoria;
- convocar los siete roles en el primer gate y congelar el routing;
- mostrar progreso mediante los eventos runtime existentes;
- gate especifico de Qwen con expedientes variados.

Cierre:

- cero accesos al futuro;
- cero fallback en el conjunto nominal del gate;
- hipotesis y generation trace para los roles convocados;
- vinculo exacto trigger -> decision -> resultado.

### Bloque G - Ciclo de politicas

Objetivo: hacer visible y seguro el cambio propuesto por los agentes.

Trabajo:

- contratos propuesta/validacion/aplicacion;
- catalogo cerrado y rangos permitidos;
- diff humano de politica;
- validacion determinista;
- Human Review para umbral o cambios sensibles;
- aplicacion con compare-and-set sobre la version padre;
- activacion idempotente en `application_cursor + 1`;
- reset de persistencia/HI declarado cuando corresponda;
- comparacion visual de versiones.

Cierre:

- ninguna politica retroactiva;
- cada frame cita su version;
- toda version cita decision y validacion;
- la demo distingue recomendacion, aprobacion y aplicacion.

### Bloque H - 3D sincronizado y transicion agentica

Objetivo: reforzar la explicacion visual sin crear otra fuente de verdad.

Trabajo:

- reutilizar `IndustrialScene3D` y `AgentOffice3D`;
- identificar rodamientos/activos reales en la escena;
- mantener una escena estable y actualizarla por refs;
- foco del activo, trigger y cambio de politica;
- enlace contextual a la historia agentica;
- reduced-motion, fallback y E2E.

Cierre:

- paridad 2D/3D;
- ningun renderer nuevo por tick;
- navegacion causal exacta;
- escena legible en escritorio y alternativa completa en movil.

### Bloque I - Experimento, evidencia y memoria academica

Objetivo: demostrar el sistema sin exagerar sus resultados.

Trabajo:

- calcular P0/P1 como baselines deterministas de carga;
- ejecutar Qwen solo para P2/P3 bajo presupuesto maximo `B`;
- comparar P2 y P3 principalmente a nivel de sesion: carga, cobertura,
  retraso, revisiones utiles y claims inseguros por cien snapshots;
- repetir la inferencia Qwen para observar estabilidad, no para inflar `n`;
- evaluar hipotesis de forma independiente del exito del ejecutor;
- generar figuras reproducibles, no capturas de logs;
- extender Playwright al replay y al puente con Agentes;
- trasladar arquitectura, metodologia, experimento, resultados y limites a la
  memoria LaTeX;
- preparar demo final guiada.

P2 y P3 ven expedientes distintos. Una nota humana superior por decision no
aisla mejor razonamiento del LLM: mezcla seleccion y dificultad. Una comparacion
contrafactual de calidad solo sera valida en un banco separado donde ambos
modos reciban exactamente los mismos expedientes.

Cierre:

- artefactos y hashes reproducibles;
- figuras con conclusiones claras;
- suite backend, build y E2E correctos;
- claims de memoria coherentes con la evidencia.

## Metricas

### Replay y causalidad

- snapshots procesados, perdidos y duplicados;
- igualdad batch--incremental;
- orden, gaps y hashes;
- reinicio y reanudacion deterministas;
- violaciones de cutoff futuro;
- aplicaciones retroactivas de politica, cuyo objetivo es cero.

### Triggers

- llamadas potenciales y efectivas;
- llamadas por cien snapshots;
- child runs, decisiones, llamadas LLM logicas y llamadas fisicas por separado;
- tokens/contexto solo cuando el proveedor los exponga de forma fiable;
- episodios algoritmicos cubiertos u omitidos;
- retraso entre cruce y trigger;
- eventos redundantes por episodio;
- supresion frente a P1;
- violaciones de cooldown y deduplicacion.

### Agentes

- JSON valido al primer intento;
- reintentos, repair, overlay, fallback y error;
- cobertura de hipotesis;
- evidencia valida, inventada o futura;
- memoria recuperada, citada, usada o rechazada;
- accion permitida;
- enlace trigger--decision--resultado;
- estabilidad entre repeticiones.

La calidad de hipotesis se informara con el contrato de assessment y un
evaluador identificado. Se separaran grounding, cautela causal, accion
admisible y calibracion de incertidumbre. P2/P3 no se compararan por una media
de decisiones no emparejadas como si tuvieran igual dificultad.

### Politicas

- propuestas, rechazadas, aprobadas y activadas;
- campos modificados y magnitud del cambio;
- tiempo desde trigger hasta decision y aplicacion;
- frames observados por cada version;
- resets declarados;
- comparacion futura por segmentos, solo descriptiva en el modo exploratorio.

### PHM permitidas para NASA IMS

- `persistent_alert_run_rate`;
- `first_persistent_alert_time_to_trajectory_end`, siempre retrospectiva;
- `pre_monitoring_alert_rate`, documentando numerador, denominador y que la
  calibracion no constituye un test independiente;
- episodios, picos aislados y racha maxima;
- tendencia Spearman;
- caida, monotonicidad, robustez y volatilidad del HI.

No se publicaran F1, AUC, onset fisico, RUL ni `lead time to failure` como si
existieran etiquetas oficiales por snapshot.

## QA obligatorio

- unitarios de contratos, cursor, orden y maquina de triggers;
- pruebas de paridad batch--replay;
- bait/sufijo futuro que no altere detector, frame, trigger ni decision;
- future-bait especifico de memoria antes de habilitar RAG;
- duplicados que no creen eventos dobles;
- gap que reinicie estado segun politica;
- pausa/reanudacion sin repetir revision;
- crash entre frames que no confirme medio `ReplayTick`;
- POST repetido y `step/play` concurrentes que avancen exactamente una vez;
- modelo, scaler y umbral que no se reajusten con monitoring;
- validation cutoff y evidencia de politica dentro del cursor permitido;
- integracion con LLM simulado para errores y fallbacks;
- gate Qwen real solo tras cerrar replay y triggers;
- regresion completa de `POST /runs` y de la historia agentica;
- E2E desktop/movil, reduced-motion y fallback WebGL;
- reload/resume, trigger asincrono y navegacion contextual ida/vuelta;
- teclado completo, zoom 200 % y controles tactiles sin depender de hover;
- slider con `aria-valuetext` y resumen textual de cada grafica;
- `aria-live="polite"` solo para trigger, cambio de estado y fin de run, nunca
  para cada tick;
- estado, severidad y version diferenciados por texto/icono ademas de color;
- rebuild Docker solo al estabilizar la superficie final.

Los E2E validan presentacion, no evidencia cientifica. No habra autoplay al
entrar; toda accion critica del 3D tendra equivalente HTML. La reduccion de
puntos preservara triggers, cambios de politica y extremos aunque use
downsampling para la curva.

## Demo final candidata

1. Abrir `Monitorizacion` y seleccionar la sesion NASA.
2. Ver el canal modelado y los canales de contexto sin diagnostico inventado.
3. Iniciar replay acelerado.
4. Observar score, umbral, HI y estados actualizandose.
5. Alcanzar una revision periodica sin cambio de politica.
6. Alcanzar una alerta persistente o transicion de severidad.
7. Ver el trigger y la run multiagente en curso.
8. Abrir la historia visual y reconocer hipotesis, estado RAG OFF y decisiones.
9. Volver al monitor y revisar el diff de politica.
10. Validar/aprobar la propuesta en modo exploratorio.
11. Ver el marcador de activacion desde el siguiente snapshot.
12. Cerrar la sesion y abrir informe, auditoria y post-mortem.

## Claims permitidos

- se implemento un replay offline causal y reproducible de NASA IMS;
- se separo scoring determinista frecuente de revision agentica periodica y
  dirigida por eventos;
- una politica de triggers redujo solicitudes agenticas conservando los
  episodios algoritmicos declarados en la trayectoria evaluada;
- los agentes produjeron hipotesis, decisiones y propuestas enlazadas a
  evidencia disponible hasta su cutoff;
- las propuestas de politica fueron validadas, versionadas y, en la demo
  exploratoria, aplicadas solo hacia el futuro;
- el sistema permite auditar visualmente telemetria, trigger, razonamiento,
  estado de memoria, validacion y cambio de politica.

## Claims prohibidos

- streaming o tiempo real industrial real;
- deteccion demostrada del fallo fisico o de su onset;
- RUL validado;
- mejora general del detector por aplicar una propuesta agentica;
- fiabilidad universal del 99 %;
- generalizacion a otros activos o datasets desde una trayectoria;
- utilidad de RAG sin comparacion controlada;
- autonomia industrial o cumplimiento/certificacion normativa.

## Primer incremento vertical

El primer desarrollo debe ser pequeno y sin Qwen:

```text
NASA oficial congelada
  -> ReplaySessionConfig/State
  -> step() manual sobre monitoring
  -> ReplayTick atomico + ledger por snapshot
  -> paridad batch--incremental
  -> API step/read con backend autoritativo
  -> cursor 2D causal con play/pausa
  -> un trigger persistente determinista
```

Solo cuando ese corte pase paridad, causalidad y QA se conectara la primera run
multiagente hija. Este orden evita validar fallbacks, graficas o adaptaciones
sobre una base temporal incorrecta.

## Estado de ejecucion de esta hoja

La secuencia inicial y sus refuerzos ya estan materializados en cierres
incrementales:

- `134_fase11_vertical_replay_manual_visual.md` cierra el replay P0 y su
  paridad causal;
- `135_fase11_motor_triggers_p3_determinista.md` cierra el motor P3 y su ledger
  de triggers;
- `136_fase11_conexion_trigger_run_multiagente.md` cierra el Bloque F mediante
  dispatch manual, vista causal por whitelist, ledger hijo y una run
  propose-only de siete roles con memoria OFF;
- `137_fase11_gate_repetido_qwen_triggers_nasa.md` publica las baterias V2 y V3
  como resultados bloqueados por fragilidades distintas;
- `138_fase11_refuerzo_binding_evidencia_monitoring_review.md` y
  `139_fase11_catalogo_evidencia_causal_por_registro.md` refuerzan sin otro gate
  la seleccion exacta de evidencia hasta el nivel de registro;
- `140_fase11_policy_proposal_consultiva.md` implementa una primera rebanada
  del Bloque G: sintetiza las siete recomendaciones bajo autoridad del servidor
  y las muestra como consultivas y no aplicadas, sin inventar parametros.

Los apartados de validacion de eficacia, aprobacion humana, politica adaptativa,
aplicacion hacia delante, nuevo gate de Qwen y ablacion RAG continuan como
trabajo pendiente. Las afirmaciones de la seccion de demo y los claims sobre
propuestas aplicadas describen el objetivo de la hoja, no capacidades
demostradas por estos cierres. La `MonitoringPolicyProposal` de la hoja 140 es
una sintesis determinista del servidor: no constituye una nueva decision de
Qwen, una politica candidata ni un cambio ejecutable.
