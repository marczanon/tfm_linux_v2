# Fase 11: conexion causal de trigger a run multiagente

Fecha: 2026-08-12

Estado: incremento implementado y gate final ratificado.

## 1. Resultado del incremento

Este incremento cierra el Bloque F de la hoja 133 sobre la base determinista
de las hojas 134 y 135. Un trigger primario `emitted` puede convertirse, por
accion manual, en una revision hija consultable por la superficie comun de
runs:

```text
tick comprometido
  -> trigger emitido
  -> vista causal por whitelist
  -> dispatch manual
  -> run hija de siete roles
  -> decisiones + runtime
  -> resultado propose-only persistido
```

La frontera de este corte es deliberadamente estrecha:

- los siete roles se ejecutan en orden fijo y producen una decision comun
  estructurada;
- la memoria esta forzada a `off`;
- las capacidades son `propose_only`, `no_fit`, `no_retrain` y `no_raw_scan`;
- no se invoca ningun ejecutor de datos, entrenamiento o scoring;
- ninguna recomendacion modifica una politica;
- el dispatch solo ocurre cuando una persona pulsa el control correspondiente
  o llama explicitamente al endpoint;
- se ha completado una primera ejecucion real con Qwen 3.5 sobre un trigger
  NASA, sin convertir ese unico caso en una evaluacion general de la calidad
  cientifica de sus hipotesis.

Por tanto, este incremento demuestra la integridad y auditabilidad del puente,
incluida una primera travesia real sin reparaciones ni fallback. No demuestra
utilidad general de Qwen, beneficio de RAG ni mejora del detector.

## 2. Decision de reutilizacion y propietarios canonicos

La capacidad se definio como: enlazar un trigger causal con una run hija sin
reescribir el ledger cientifico del replay ni crear otra superficie de runs.

La revision previa del protocolo de reutilizacion encontro propietarios
existentes para casi todo el recorrido:

- `MonitoringReplayStore` sigue siendo la autoridad de ticks, triggers y
  estado causal del replay;
- el modulo canonico de contratos de monitorizacion conserva vistas,
  comandos, receipts, intentos y resultados estrictos;
- el grafo existente aporta LangGraph, los siete nombres de rol y los eventos
  runtime;
- `pipeline_runner` y `run_persistence` conservan el propietario comun de la
  ejecucion y de las runs consultables;
- FastAPI, el registro de jobs y los endpoints de runs se reutilizan;
- la vista `Monitorizacion` y la sala `Agentes` comparten el mismo snapshot y
  la misma traza persistida.

El elemento nuevo con responsabilidad propia es el store de revisiones de
monitorizacion. Mantiene la proyeccion causal y un ledger hijo append-only;
no puntua señales, no decide triggers, no ejecuta el grafo y no modifica los
commits del replay.

## 3. Vista causal por lista positiva

La vista se construye exclusivamente para un trigger primario emitido que
tenga tick de origen y cutoff confirmados. Incluye los frames ya comprometidos
con cursor menor o igual al cutoff. No consulta el sufijo posterior.

La evidencia visible usa una lista positiva cerrada. Puede contener identidad
de registro, dataset, trayectoria, activo, canal, snapshot, tiempo fuente,
segmento, estado de analisis, telemetria compacta y diagnosticos ya calculados,
ademas de las versiones de scoring y activacion. Se omiten valores ausentes.
No se entregan rutas raw, muestras completas, longitud final, vida relativa,
tiempo hasta fallo, onset ni resultados retrospectivos.

El store materializa dos proyecciones separadas:

- un manifiesto administrativo reducido, con particion visible, activos,
  politicas y cutoff;
- un artefacto de evidencia con los registros permitidos.

Ambos se ligan mediante SHA-256. La vista conserva ademas sesion, trigger,
evento de trigger, tick de origen, snapshot y tiempo de cutoff. Al cargarla se
vuelven a verificar la huella de los bytes, el esquema, los campos permitidos,
los tiempos y la identidad causal. Las referencias que puede citar una
decision son exactamente los `evidence_id` declarados por la vista, nunca
paths elegidos por el modelo.

## 4. Contratos del puente

Los contratos estrictos implementados separan cinco responsabilidades:

1. `CausalInputView` describe el prefijo permitido y se autoverifica mediante
   su hash canonico.
2. `MonitoringReviewRequest` fija run hija, sesion, trigger, tick, cutoff,
   politicas, vista, siete roles, capacidades, memoria desactivada y huellas de
   prompt, esquema y catalogo de opciones.
3. `MonitoringReviewDecision` conserva para cada rol la hipotesis, traza de
   generacion, observacion, justificacion, confianza, evidencia, alternativas
   y accion recomendada.
4. `MonitoringReviewRoleResult` y `MonitoringReviewResult` cierran los siete
   desenlaces y mantienen el enlace con request, vista y eventos runtime.
5. `MonitoringReviewDispatchCommand`, `MonitoringReviewDispatchReceipt` y
   `MonitoringChildRunAttempt` modelan compare-and-swap, idempotencia y
   lifecycle de la hija.

Los siete roles canonicos son supervisor, limpiador, estructurador, modelador,
evaluador, redactor y verificador. No se acepta un subconjunto ni otro orden en
esta primera puerta. La accion pertenece al catalogo cerrado
`maintain_policy`, `intensify_observation`, `request_human_review`,
`pause_replay` o `insufficient_evidence`.

El servidor es propietario de las identidades, los hashes, el cutoff, la
clase de hipotesis de cada rol, la traza del intento, `memory_mode=off` y
`policy_application_status=not_applied`. Una salida del modelo no puede
sustituir esos campos. Las huellas de vista, request, decision, resultado,
comando y receipt se recalculan al validar; la persistencia rechaza decisiones
o eventos diferentes de los que quedaron sellados en el resultado.

## 5. Run propose-only de siete roles

El subgrafo contiene solo siete nodos, conectados en el orden canonico. Cada
nodo recibe la misma vista causal, las referencias permitidas y el resumen de
las decisiones anteriores. El contenido semantico que debe aportar cada rol
es observable: hipotesis falsable, observacion, accion, alternativas,
justificacion, confianza y evidencia.

Esta ruta no entra en el pipeline ordinario. No crea manifiestos, no perfila ni
limpia señales, no estructura ventanas, no ajusta modelos, no evalua datasets y
no redacta mediante el ejecutor de informes. Tampoco recupera, escribe o cura
memoria RAG. Las recomendaciones quedan como propuestas textuales dentro del
catalogo y el resultado declara siempre que la politica no fue aplicada.

La capa de generacion admite una respuesta valida, un segundo intento de
reparacion y un fallback trazado. Los tests con un cliente falso comprueban las
tres ramas y que el servidor sustituye cualquier identidad o cutoff aportado
por la respuesta. Estas pruebas verifican el contrato; no son resultados de
Qwen ni una medida de calidad de razonamiento.

## 6. Ledger hijo y lifecycle

El despacho no modifica el commit que contiene el tick y el trigger. Crea un
segundo ledger append-only anclado al hash de configuracion, al evento
`emitted`, a la vista causal y al request. Una prueba conserva los bytes del
commit de replay antes y despues de completar la hija.

El lifecycle hijo distingue:

```text
dispatched -> running -> resolved
                      -> failed
dispatched/running -> interrupted
```

Las transiciones `dispatched`, `running`, `resolved` y `failed` se proyectan
tambien en la historia visible del trigger, pero su fuente es el ledger hijo.
`interrupted` representa un corte de infraestructura sin fingir una resolucion
del trigger. Un `failed` logico exige un resultado de fallo persistido; un
`interrupted` puede no disponer de ese expediente.

Cada comando declara `expected_child_revision`. Repetir el mismo
`command_id` y payload devuelve un receipt idempotente; reutilizarlo con otro
payload o revision produce conflicto. Solo puede existir una hija activa por
sesion y un trigger no se despacha dos veces. Mientras una hija esta
`dispatched` o `running`, el replay guiado no permite avanzar otro tick. El
launcher del job sigue siendo local y en memoria; la evidencia causal y el
ledger de lifecycle son los elementos durables.

En el alcance local monoproceso, el `lifespan` de la API reconcilia el ledger
al reiniciar. Una hija `dispatched` o `running` que ya no tenga job activo ni
resultado completo se marca `interrupted`; Qwen no se reejecuta de forma
automatica. Si existe una reserva durable sin receipt, el comando se
reconstruye desde el propio ledger para cerrar su trazabilidad idempotente.

La run resuelta se persiste en el registro comun con siete decisiones, sus
hipotesis, eventos runtime, request, resultado, evidence pack, informe y
auditoria. La carga vuelve a verificar hashes y enlaces antes de aceptar el
snapshot. Reutilizar el mismo identificador con un request o resultado distinto
se trata como conflicto de idempotencia, no como una ejecucion correcta.

## 7. API y puente web

La superficie HTTP nueva es estrecha:

- `POST /monitoring/sessions/{session_id}/triggers/{trigger_id}/dispatch`
  recibe solo `command_id` y `expected_child_revision`; el servidor resuelve
  vista, roles, hashes, request, run y job;
- `GET /monitoring/sessions/{session_id}/child-runs` lee los intentos desde el
  ledger durable;
- las lecturas de sesion incluyen revision hija, intentos y lifecycle
  proyectado;
- la run terminada se consulta por los endpoints comunes de runs, eventos,
  artefactos, informe y auditoria.

La web muestra `Lanzar revision` solo en un trigger realmente despachable. El
boton tiene estado ocupado, bloquea dobles envios y no introduce autoplay. Tras
la reserva, la historia del trigger muestra el nuevo lifecycle y permite abrir
la run hija en `Agentes`. La aplicacion conserva el contexto de sesion, cursor
y trigger, y ofrece volver al mismo punto de monitorizacion sin avanzar el
replay. Tanto el mapa 2D como la inspeccion detallada consumen los eventos y
decisiones persistidos; no inventan una relacion si falta el enlace.

## 8. Validacion disponible

El gate backend cubre contratos y hashes, whitelist y cutoff, evidencia
manipulada, CAS e idempotencia, ledger separado, single-flight, lifecycle,
subgrafo de siete roles, repair/fallback, persistencia consultable y API de
dispatch. Los tests bloquean explicitamente las funciones de raw, ejecutores y
RAG para fallar si esta ruta las invoca.

La suite de navegador cubre escritorio y movil, dispatch manual por teclado,
estado pendiente, ausencia de doble envio, actualizacion del lifecycle,
navegacion a `Agentes`, restauracion del trigger y ausencia de llamadas API no
declaradas.

El gate final relevante queda cerrado con:

- **140 tests backend correctos** y **3 subtests correctos**; se conserva una
  unica advertencia procedente de una dependencia externa;
- **22 de 22 casos E2E correctos**, ratificados localmente en escritorio y
  movil junto con el typecheck y el build de produccion.

Estas cifras no son el recuento total del repositorio ni muestras cientificas
independientes. La advertencia externa no corresponde a un fallo del contrato.

## 9. Primera ejecucion real sobre un trigger NASA

El gate nominal se ejecuto sobre NASA IMS Set 2 con la politica P3 ya
congelada. La traza canonica es:

- sesion `nasa-p3-qwen35-trigger-20260812-02`;
- trigger `state_transition` confirmado en el cursor 353;
- run hija `mon-review-1ce152db1b9d0b23c16572f2`;
- siete de siete decisiones con `origin=llm` y validadas al primer intento;
- cero reparaciones y cero fallbacks;
- `memory_mode=off` y `policy_application_status=not_applied`.

La run demuestra que los siete roles pueden atravesar el puente real, citar la
vista causal permitida y dejar decisiones consultables bajo el contrato
cerrado. Es una sola ejecucion retrospectiva sobre una trayectoria conocida:
no estima una tasa de exito, no confirma las hipotesis propuestas y no permite
atribuir mejora alguna al razonamiento del modelo.

Una ejecucion tecnica anterior registro dos timeouts y, como consecuencia, dos
fallbacks. Se rechazo como resultado del gate y se conservo solo como
diagnostico de integracion; motivo la introduccion de un timeout especifico
para la revision de monitorizacion. Sus fallbacks no se mezclan con la
contabilidad de la ejecucion final.

## 10. Claims permitidos y limites

Este incremento permite afirmar que:

- un trigger emitido puede enlazarse de forma manual y auditable con una run
  hija de siete roles;
- todos los roles reciben un prefijo hasheado y limitado al cutoff;
- las decisiones, hipotesis, trazas y evidencias quedan persistidas y son
  consultables desde la aplicacion;
- replay y lifecycle hijo permanecen en ledgers separados;
- la ruta implementada mantiene memoria OFF, no llama ejecutores y no aplica
  politicas;
- la ejecucion NASA identificada completo siete decisiones LLM validas al
  primer intento, sin repair ni fallback en esa run concreta.

No permite afirmar:

- monitorizacion en tiempo real, scheduler continuo o despliegue industrial;
- evaluacion prospectiva, holdout o generalizacion fuera de NASA Set 2;
- calidad, fiabilidad o superioridad general de Qwen;
- ausencia universal de timeouts, reparaciones o fallbacks en ejecuciones
  futuras;
- utilidad de RAG, porque la memoria esta desactivada;
- deteccion de onset fisico, RUL o fallo etiquetado;
- mejora del scoring o de la politica P3;
- que exista todavia validacion o aplicacion hacia delante de una propuesta.

NASA IMS Set 2 continua siendo una trayectoria retrospectiva conocida y el
bridge no convierte sus snapshots correlacionados en replicas independientes.
Los escenarios sinteticos y clientes falsos verifican integracion y seguridad,
no rendimiento fisico ni razonamiento experto.

## 11. Gate posterior ejecutado

La bateria propuesta en el cierre original se implemento y ejecuto despues
sobre los cuatro triggers primarios P3, tres replays y los siete roles. Su
protocolo, artefactos y resultados completos se documentan en
`137_fase11_gate_repetido_qwen_triggers_nasa.md`.

El gate cumplio una funcion bloqueante real. La primera pasada completa (`v2`)
resolvio 12/12 hijas y mantuvo 84/84 decisiones al primer intento, pero tres
textos formularon claims fuera del alcance causal permitido. Tras incorporar
el control al runtime, una repeticion integral con plan e identidades nuevos
(`v3`) alcanzo 84/84 claims acotados, pero dos roles agotaron la correccion por
citar evidencia fuera de la vista; quedaron dos fallbacks y 11/12 hijas
resueltas.

Ambas publicaciones son evidencia negativa util y ninguna autoriza la ablacion
RAG. Tampoco se aplico una politica ni se evaluo la verdad fisica de las
hipotesis. El siguiente paso debe resolver y prerregistrar la fragilidad de
referencias sin repetir selectivamente el unico caso fallido.
