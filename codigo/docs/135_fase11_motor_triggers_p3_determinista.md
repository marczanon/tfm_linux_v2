# Fase 11: motor determinista de triggers P3

Fecha: 2026-08-11

Estado: incremento backend implementado y cerrado tras auditoria funcional,
gate focal y recorrido golden completo de NASA Set 2.

## 1. Resultado del incremento

Este incremento cierra el paso que quedo abierto en el vertical P0 de la hoja
134. El replay NASA puede crearse ahora con una politica de activacion `P3`
registrada. En cada avance, un motor Python puro evalua el tick causal ya
cerrado, produce eventos estructurados y actualiza su checkpoint antes de que
tick, triggers y estado se persistan juntos.

El alcance sigue siendo deliberadamente backend y determinista:

- no se invoca Qwen;
- no se consulta ni se escribe memoria RAG;
- no se despachan runs multiagente hijas;
- no se aplica ninguna propuesta de cambio de scoring;
- no se implementa el modo `adaptive_replay_exploratory`;
- no se ha modificado el frontend en este incremento.

Por tanto, un evento `emitted` representa una **solicitud determinista y una
reserva de presupuesto**, no una run hija realmente ejecutada. Los estados
`dispatched`, `running`, `resolved` y `failed` quedan fuera de este corte.

## 2. Posicionamiento experimental correcto

`P0` y `P3` son dos politicas de **activacion** disponibles dentro del mismo
modo `frozen_benchmark`. No son las dos ramas `frozen_benchmark` y
`adaptive_replay_exploratory`:

- `P0` observa el replay sin generar eventos ni reservar runs variables;
- `P3` conserva exactamente el mismo scoring congelado y decide, mediante
  reglas deterministas, cuando estaria justificada una revision agentica;
- el servicio sigue rechazando `adaptive_replay_exploratory`, porque todavia
  no existe aplicacion validada y exclusivamente hacia delante de nuevas
  versiones de politica.

Esta separacion impide atribuir a P3 cambios del detector que no han ocurrido.
`ScoringPolicyBundle` y `AgentActivationPolicy` continúan versionados por
separado.

El escenario sigue siendo NASA IMS Set 2, un historico retrospectivo conocido,
inspeccionado y utilizado durante el desarrollo. No es tiempo real, holdout no
visto, prueba prospectiva ni evidencia de generalizacion a otro activo o
condicion. Los episodios son episodios **algoritmicos** de la politica de salud;
no se interpretan como onset fisico, fallo etiquetado ni RUL.

## 3. Decision de reutilizacion

La capacidad se definio como: evaluar triggers reproducibles sobre cada tick
del replay y co-persistir su decision causal sin introducir Qwen ni duplicar el
pipeline.

La revision previa segun el protocolo 35 encontro propietarios ya existentes:

- `MonitoringReplayStore` continua siendo el reloj, la fuente de verdad de la
  sesion y el propietario del commit;
- `ReplayTick`, `MonitoringFrame`, `ReplaySessionState` y
  `AgentActivationPolicy` se extendieron en su modulo de contratos canonico;
- la politica de salud existente sigue produciendo estado, rachas y gaps;
- la API de monitorizacion existente selecciona una politica registrada, sin
  aceptar bundles ni rutas arbitrarias desde HTTP;
- el scoring, los checkpoints, receipts, locks y validaciones de reanudacion
  del vertical P0 se reutilizan sin crear un segundo replay.

No existia un propietario para decidir eventos a partir de un tick cerrado.
Por ello se creo `monitoring_trigger_engine.py` como motor puro. No persiste,
no ejecuta agentes, no conoce FastAPI y no vuelve a calcular el score. Recibe
tick, checkpoints anterior y actual, ledger previo, politica y checkpoint de
activacion; devuelve eventos y el siguiente checkpoint.

## 4. Contratos y estado causal

La superficie Pydantic mantiene modelos estrictos e inmutables para la parte
append-only:

- `AgentActivationTriggerRule` fija tipo, prioridad, cooldown en tiempo
  fuente, grupo de coalescing, rearme, estados objetivo, roles solicitados y
  clasificacion presupuestaria;
- `AgentActivationPolicy` fija version, hash, clase P0--P3, presupuesto,
  persistencias K/R, reglas y precedencia completa;
- `MonitoringTriggerEvent` registra identidad, secuencia, tipo, lifecycle,
  razon, episodio, inicio de condicion, cutoff, evidencia, deduplicacion,
  version de politica, supresion/coalescing y reserva de presupuesto;
- `ReplayActivationRuleCheckpoint` conserva la ultima activacion efectiva por
  tipo para aplicar cooldown causal;
- `ReplayActivationCheckpoint` conserva secuencia siguiente, slots reservados,
  armado, candidato de persistencia, episodio activo, trigger que ya lo
  cubrio, ultimo cursor evaluado y checkpoints de reglas;
- `ReplaySessionState` enlaza ese checkpoint con la version de activacion
  realmente activa.

El contrato distingue el primer snapshot de una racha de su confirmacion. Un
trigger persistente con `K=3` conserva `condition_start_cursor` y
`snapshot_start_id` del primer alertado, pero su `cutoff_cursor` y
`snapshot_end_id` corresponden al tercer tick, cuando la condicion ya puede
confirmarse causalmente.

Los eventos usan una secuencia contigua y claves de deduplicacion estables. Un
evento suprimido o coalescido tambien queda en el ledger: no se elimina una
decision solo porque no reserve una nueva revision.

## 5. Politica P3 registrada

La politica `nasa-rtf-hyb-p3-01-activation-v1` esta congelada con:

- presupuesto maximo `B = 7` reservas de runs hijas variables;
- entrada persistente `K = 3` ticks consecutivos en `warning` o `critical`;
- recuperacion `R = 1` tick fuera de alerta para rearmar;
- cooldown de `51.600 s` de tiempo fuente para reglas variables;
- ningun calendario periodico;
- los siete roles existentes como mapping solicitado, aunque en este corte no
  se despacha ninguno.

Las reglas, en orden de precedencia, son:

1. `continuity_gap`, prioridad 100: invalida continuidad y reinicia el estado
   temporal del episodio;
2. `state_transition`, prioridad 90: solo escala hacia `critical`;
3. `persistent_alert`, prioridad 80: confirma la racha K=3 y se rearma tras
   recuperacion;
4. `session_close`, prioridad 20: registra el cierre una vez y queda fuera de
   `B`.

Gap, critical y persistencia comparten el grupo `monitoring_review`. Si varias
condiciones compatibles coinciden, la precedencia elige una primaria y las
restantes se registran como coalescidas. El cooldown se calcula con
`source_time`, no con el reloj de ejecucion local.

Una activacion efectiva asociada a un episodio lo marca como cubierto y
desarma la persistencia. De este modo, una entrada inmediata en `critical` y
su posterior confirmacion K=3 consumen como maximo un slot para ese episodio.
El episodio solo se rearma al completar R; una recuperacion parcial en una
politica con R mayor que uno no debe duplicarlo ni dejar el motor en un estado
sin referencia causal.

P0 conserva su contrato anterior: cero reglas, cero presupuesto y cero
eventos. P1 y P2 siguen presentes en el tipo general de politica, pero no estan
registradas como opciones ejecutables de este escenario.

## 6. Integracion atomica con el replay

El orden efectivo de un `step` P3 es:

1. validar receipt, idempotencia, revision y politicas persistidas;
2. puntuar el siguiente snapshot y construir todos sus frames;
3. cerrar y validar el `ReplayTick` en memoria;
4. evaluar una vez el motor de triggers sobre ese tick cerrado;
5. construir el nuevo checkpoint y el nuevo estado;
6. escribir un unico commit encadenado que contiene comando, receipt, tick,
   estado y triggers;
7. publicar el estado derivado del commit.

No existe primero un commit visible del tick y despues otro de triggers. El
tick cerrado en memoria y sus triggers forman un **co-commit atomico**. Un
crash no debe dejar medio lote multicanal ni un tick confirmado sin su decision
de activacion correspondiente.

Un retry con el mismo `command_id` devuelve los mismos triggers que el commit
original. Al reanudar, el store reconstruye y valida el ledger causal, incluida
la transicion exacta del motor. Alterar un trigger y recalcular solamente el
hash externo del commit no basta: la reejecucion determinista detecta que los
eventos ya no siguen del checkpoint anterior y rechaza la sesion.

## 7. API disponible

La API existente incorpora P3 sin abrir un endpoint paralelo:

- `GET /monitoring/sources` declara `P0` y `P3` como politicas registradas;
- `POST /monitoring/sessions` acepta `activation_policy_kind` y resuelve
  exclusivamente el bundle interno correspondiente;
- la creacion con P2 u otra politica no registrada se rechaza;
- las respuestas de creacion, lectura y step exponen los triggers ya
  confirmados por el commit;
- el cliente no puede aportar reglas, presupuesto, cooldown, hashes ni
  versiones libres.

P3 v1 exige ademas una frontera bootstrap sin episodio de alerta activo. El
servicio rechaza una sesion que intentaria transportar una racha no resuelta
desde calibracion a monitoring, porque esa semantica aun no esta implementada.

## 8. Resultado real actual sobre NASA Set 2

La integracion opt-in recorre los 689 ticks de monitoring de Set 2 con P3 y
mantiene la paridad de score, Health Index, estado y segmento descrita para el
vertical P0.

El ledger observado contiene:

- 689 ticks comprometidos;
- 14 eventos de trigger en total;
- por tipo: 11 `state_transition`, 2 `persistent_alert` y 1
  `session_close`; no aparece un gap en esta trayectoria de monitoring;
- 4 eventos `emitted`: 3 variables y el cierre fijo;
- 10 eventos `suppressed`: 9 por cooldown y 1 porque el episodio ya estaba
  cubierto;
- 2 de 2 confirmaciones persistentes cubiertas;
- 3 de 7 slots variables reservados;
- cero runs hijas, llamadas Qwen o interacciones RAG, porque el despacho sigue
  desactivado.

Estos son recuentos de **eventos y reservas**, no de decisiones LLM ni de runs
multiagente ejecutadas. Tampoco prueban superioridad de P3: describen como se
comporta una politica fijada sobre una trayectoria retrospectiva conocida.

La proyeccion semantica del ledger queda ratificada con la huella SHA-256
**golden final para este contrato**:

```text
84fe3c6b1a8054e23abc795d31c8aeca8f0b3e13979ce292c48ae6e5f8d2b0c1
```

Esta huella cubre secuencia, tipo, lifecycle, codigo de razon, inicio y cutoff,
supresion, reserva y coalescing de cada evento. Excluye `episode_id`, cuya
identidad se deriva de `session_id` y hacia que el golden anterior cambiase
entre sesiones semanticamente equivalentes. Cualquier cambio posterior de la
semantica conservada exige versionar el contrato y ratificar una nueva huella;
no debe actualizarse el golden para ocultar una regresion.

## 9. Pruebas implementadas

La validacion se distribuye sin duplicar responsabilidades:

- `test_monitoring_replay_schema.py`: invariantes estrictos de politica,
  reglas, lifecycle, rango causal, presupuesto y checkpoints;
- `test_monitoring_trigger_engine.py`: K=3, inicio frente a confirmacion,
  recuperacion y rearme, critical mas persistencia, regresion de recuperacion
  parcial, gap, cooldown, coalescing, precedencia, presupuesto, cierre y P0;
- `test_monitoring_replay_service.py`: co-commit tick+triggers, idempotencia,
  resume, integridad frente a manipulacion, bootstrap permitido y causalidad
  frente a cambios en el sufijo futuro;
- `test_api_monitoring.py`: seleccion registrada P3, exposicion de eventos y
  rechazo de P2 no registrada;
- `test_nasa_monitoring_replay_integration.py`: paridad completa y ledger P3
  de 689 steps sobre los artefactos NASA locales.

El test NASA completo sigue siendo opt-in porque depende de artefactos locales
ignorados por Git. Los casos sinteticos cubren ramas que no aparecen en Set 2,
como gap, coalescing y agotamiento de presupuesto.

El gate focal backend termina con **67/67 tests correctos**. Esta cifra
corresponde exclusivamente al corte focal de replay, contratos, motor, store y
API; no es el recuento total de tests del repositorio.

La regresion Python completa del repositorio termina, en el mismo estado de
codigo, con **625 tests correctos, 2 omitidos y 13 subtests correctos**. Los dos
omitidos conservan sus condiciones explicitas y no pertenecen al gate focal P3.

El golden opt-in completa **689/689 steps** P3 y, tras recargar la sesion desde
disco, conserva estado `completed`, 14 eventos y 3/7 slots reservados. P0
permanece sin triggers. No queda un bloqueante funcional reproducible en el
alcance de este incremento.

Como verificacion separada de la superficie visual relacionada, la suite E2E
confirmada termina con **18/18 casos correctos** en escritorio y movil. No
forma parte de los 67 tests backend ni implica que este incremento haya
activado Qwen, RAG o runs hijas.

Permanece una deuda conocida de rendimiento: el store vuelve a leer y validar
el ledger acumulado durante cada step, por lo que el recorrido completo tiene
coste estructural O(n²). No afecta a la paridad ni a la integridad observadas
en 689 ticks, pero debe resolverse mediante validacion incremental o indexada
antes de reclamar latencia operacional o escalar a trayectorias mayores.

## 10. Claims permitidos y limites

Este incremento permite afirmar que:

- P3 genera un ledger de triggers determinista y reproducible sobre ticks
  causalmente cerrados;
- inicio de racha y confirmacion K=3 quedan diferenciados;
- cooldown, coalescing, rearme, deduplicacion y presupuesto tienen estado
  persistente y versionado;
- tick, triggers y siguiente checkpoint se co-persisten en un commit;
- P0 y P3 pueden compararse como politicas de carga potencial sin cambiar el
  scoring congelado.

No permite afirmar:

- monitorizacion en tiempo real, streaming o disponibilidad industrial;
- evaluacion prospectiva, holdout o generalizacion fuera de NASA Set 2;
- verdad fisica de los episodios, onset, RUL, F1 o AUC;
- que los tres slots reservados equivalgan a tres runs ejecutadas;
- calidad, fiabilidad o utilidad de Qwen, los agentes o la memoria RAG;
- superioridad causal de P3 frente a P0, P2 o una politica adaptativa;
- efecto de aplicar propuestas, porque `adaptive_replay_exploratory` sigue
  deshabilitado.

## 11. Gate posterior cerrado

El incremento propuesto al cerrar esta hoja se implemento despues sin modificar
la semantica ni el golden del trigger. Su cierre se documenta en
`136_fase11_conexion_trigger_run_multiagente.md` y demuestra el enlace:

```text
tick -> trigger -> vista causal -> run hija -> decisiones -> resultado
```

La conexion usa una vista por whitelist, dispatch manual, ledger hijo separado,
siete roles propose-only y memoria OFF. Los recuentos NASA de esta hoja siguen
siendo exclusivamente ticks, eventos y reservas del corte P3: no deben
reinterpretarse retroactivamente como runs hijas. Qwen real, RAG y aplicacion
de politicas continuan fuera de ambos cierres.
