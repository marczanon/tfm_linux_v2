# Fase 11: vertical P0 de replay manual y visual

Fecha de cierre: 2026-08-11

Estado: vertical previa P0, implementada y validada como piloto retrospectivo
local. El siguiente paso determinista que proponia este documento queda cerrado
por `135_fase11_motor_triggers_p3_determinista.md`.

## 1. Resultado del incremento

Este incremento materializa el primer vertical ejecutable de la hoja de ruta
133: el histórico oficial NASA IMS Set 2 puede recorrerse snapshot a snapshot,
aplicando el modelo y las políticas temporales congeladas, persistiendo cada
avance y mostrando el resultado en una nueva vista 2D de monitorización.

El alcance termina deliberadamente en la política de activación `P0`. La
ejecución es determinista y manual; no invoca Qwen, no consulta ni escribe
memoria RAG, no emite triggers y no crea runs multiagente hijas. Los controles
de reproducción de la interfaz automatizan localmente llamadas manuales
sucesivas mediante un temporizador del navegador; no constituyen un scheduler
ni un servicio de monitorización continuo en backend.

NASA IMS Set 2 se usa aquí como **piloto retrospectivo ya inspeccionado**. No es
un holdout, un experimento prospectivo, una fuente en tiempo real ni una prueba
de despliegue industrial.

## 2. Decisión de reutilización

La capacidad añadida se definió como: reproducir causalmente una trayectoria
run-to-failure congelada, con cursor, ledger e inspección visual, sin duplicar
el pipeline de entrenamiento ni el grafo multiagente.

La búsqueda previa del protocolo 35 identificó propietarios canónicos que se
han reutilizado:

- la carga y el scoring del bundle congelado del ejecutor de modelado;
- la lectura del manifest común y de los canales de señal;
- la agregación de ventanas por snapshot, la detección de gaps y las políticas
  causales de salud ya existentes;
- el router y la inyección de servicios de la API FastAPI;
- el shell, los tipos y el sistema visual de la aplicación React.

No existía un propietario para el reloj lógico de replay, el cursor de
ejecución, la idempotencia y el ledger de ticks. Por ello se creó un servicio
específico de monitorización. Su responsabilidad termina en preparar y
persistir evidencia determinista; no reentrena, no sustituye al pipeline y no
crea un segundo grafo de agentes.

También se añadieron contratos específicos, una capa HTTP estrecha y los
componentes 2D. La trayectoria retrospectiva utilizada como oráculo en QA no
forma parte de las entradas de runtime.

## 3. Escenario congelado y trazabilidad

El registro interno expone un único escenario en este incremento:

- escenario: `NASA-RTF-HYB-01`;
- dataset y trayectoria: `nasa_ims_bearing` / `set_2`;
- run piloto: `nasa-ims-official-set2-v2-pca-003`;
- 984 snapshots sincronizados: 197 de baseline, 98 de calibración y 689 de
  monitorización;
- 19 ventanas por snapshot;
- `bearing_1/channel_1`: canal modelado;
- `bearing_2/channel_2`, `bearing_3/channel_3` y
  `bearing_4/channel_4`: telemetría descriptiva, sin diagnóstico.

Los artefactos y políticas quedan identificados por hashes SHA-256:

- manifest:
  `c3600b40f43fbbcdc9a99555c56e0a93f69ad386935a5622936255d46071cc0f`;
- features:
  `cf7a2b5591d8f5cf5d67194062b553b0665d772b2794f805ffd8cc9ab5288839`;
- modelo y scaler congelados:
  `10e99c38d125a5903bb410b4c119901feeed20b2b7c5cadac7c4e4c02a657e1d`;
- política de scoring `nasa-set2-pca-003-scoring-v1`:
  `efca7342597261121e08ee6d4f81e1c0ab875ed4d4c9a2e028a91c403274477e`;
- política de activación `deterministic-observer-p0-v1`:
  `5b3620df22e53fea2b096c2c8403aaa8ca1a25d9a6795cb890b4cf820aca2f74`;
- fingerprint compuesto de la fuente:
  `68d038248e76ee6db4fe0f524389746db961e9c10d9d73f93066dffac28f74af`.

El bundle de scoring enlaza además, por contenido, las políticas de agregación,
gaps, salud e indicador de salud mediante los hashes `d47f67c5...08522`,
`e90fcced...315c4`, `2372d0f2...264d7` y `a0a40586...02b61`. El fingerprint
incluye también escenario, dataset, trayectoria, tamaños esperados y el mapeo
activo/canal; una sesión no puede reanudarse si el registro reasigna el score a
otro canal.

La política de scoring usa las diez features permitidas `mean`, `std`, `rms`,
`min`, `max`, `peak_to_peak`, `skewness`, `kurtosis`, `crest_factor` y
`energy`. El umbral congelado es `0.21857833212926256` y la comparación por
ventana es estricta: `score > threshold`. La decisión agregada por snapshot y
el cálculo de salud reutilizan sus políticas versionadas independientes.

## 4. Frontera causal efectiva

En este vertical, «causal» describe la dirección de lectura del replay, no una
afirmación de causalidad física ni un diseño experimental prospectivo:

- el bootstrap contiene solo el prefijo de baseline y calibración;
- cada step consume únicamente el snapshot situado en el cursor siguiente;
- el estado conserva por separado los historiales de salud bruto y suavizado
  necesarios para continuar el cálculo;
- la señal cruda del snapshot actual solo se usa para resumir RMS, pico
  absoluto y número de muestras de los cuatro canales;
- `relative_life`, `time_to_failure_seconds`, etiquetas, targets y tipo de
  fallo se excluyen de la vista de scoring;
- las predicciones y la trayectoria retrospectivas no se leen en runtime;
- el hash de cada tick combina la proyección segura de features y el SHA-256
  del fichero raw usado para la telemetría; los frames conservan ambas
  referencias de evidencia;
- el fichero raw se comprueba antes y después de leerlo: si cambia durante la
  lectura, el step se rechaza y no publica un tick incoherente.

Si un raw no puede leerse, el score congelado sigue siendo reproducible desde
features, pero los canales contextuales se marcan `unavailable` y el hash del
tick registra explícitamente la ausencia de esa evidencia.

Se conoce administrativamente la longitud total de Set 2 y sus particiones,
porque el escenario está registrado y congelado. Lo que se evita es que los
**valores del sufijo futuro** entren en el cálculo del tick actual. Las marcas
temporales son las observaciones históricas del dataset y no se reinterpretan
como hora de llegada en tiempo real.

## 5. Contratos implementados

Los contratos Pydantic son estrictos y separan configuración, estado,
evidencia y comandos:

- sesión y políticas: `ReplayAssetSpec`, `ReplaySessionConfig`,
  `ActivePolicyRefs`, `ReplayAssetCheckpoint`, `ReplaySessionState`,
  `ScoringPolicyBundle` y `AgentActivationPolicy`;
- evidencia: `MonitoringTelemetrySummary`, `MonitoringFrame` y `ReplayTick`;
- entrada causal futura: `CausalEvidenceArtifact` y `CausalInputView`;
- ciclo de triggers futuro: `AgentActivationTriggerRule` y
  `MonitoringTriggerEvent`;
- avance idempotente: `ReplayStepCommand` y `ReplayStepReceipt`.

Un frame `modeled` exige el diagnóstico y el segmento temporal. Un frame
`telemetry_only` solo puede contener el resumen descriptivo de señal, y un
frame `unavailable` exige el motivo de indisponibilidad. Así se impide que los
canales 2--4 adquieran por accidente score, índice de salud, riesgo o estado.
Cada tick contiene al menos un frame y se persiste como unidad atómica.

`CausalInputView` y los contratos de trigger ya fijan una interfaz segura para
fases posteriores, pero el servicio P0 todavía no los produce ni ejecuta.

## 6. Servicio manual P0

El servicio admite únicamente `frozen_benchmark`; el modo adaptativo se
rechaza mientras no existan validación de políticas y aplicación estrictamente
hacia delante. Los paths de artefactos proceden de un registro interno: una
petición no puede suministrar rutas arbitrarias.

Al crear una sesión se escriben configuración, políticas de scoring,
activación y salud temporal, un seed de checkpoints ligado por hash, receipts,
y estado inicial. Cada `step`:

1. comprueba el `expected_revision` mediante compare-and-swap;
2. reconoce de forma durable cualquier `command_id` repetido, también si su
   primer resultado fue conflicto o rechazo;
3. puntúa un único snapshot de monitorización;
4. actualiza el checkpoint causal del activo modelado;
5. genera los cuatro frames sincronizados;
6. valida la transición completa desde el checkpoint anterior y guarda un
   commit atómico dentro de una cadena SHA-256 antes de publicar el nuevo
   estado.

Tras un reinicio, un commit ya confirmado puede reparar un `state.json`
rezagado. Al llegar al último tick, la sesión pasa a `completed` y rechaza
nuevos avances. Un `RLock` protege cada instancia y `fcntl.flock` serializa la
creación y el avance entre procesos locales; una prueba multiproceso confirma
que dos comandos con la misma revisión producen un único commit. La
coordinación sigue siendo POSIX/advisory sobre almacenamiento local: no se
afirma consenso ni tolerancia distribuida a fallos.

Los conflictos y rechazos producen receipts durables, pero no ticks. Al
reanudar, el servicio carga las políticas persistidas y valida sus hashes,
dependencias, artefactos, fingerprint, mapeo activo/canal y continuidad entre
comando, receipt, tick, checkpoint y estado. La validación reconstruye de forma
ligera gaps, segmento, salud bruta y suavizada, rachas e historiales desde el
checkpoint anterior; no necesita releer todo el raw. Una divergencia detiene la
sesión en vez de reconstruir silenciosamente resultados con defaults nuevos.
Cuando una cabeza de ledger aparece por primera vez tras un reinicio, cada frame
modelado se vuelve a ligar a las features y al scorer congelado. El resultado se
cachea por el SHA-256 de la cabeza, por lo que las lecturas posteriores no
repiten el cálculo mientras el ledger no cambie.

La política P0 tiene cero reglas y un máximo de cero runs variables. Por ello,
la colección de triggers permanece vacía y no existe coste LLM ni actividad de
memoria en este vertical.

## 7. API

La API implementa cinco operaciones:

- `GET /monitoring/sources`: lista escenarios registrados y disponibilidad;
- `POST /monitoring/sessions`: crea una sesión congelada;
- `GET /monitoring/sessions/{session_id}`: devuelve configuración, estado,
  ticks y transiciones de trigger visibles;
- `POST /monitoring/sessions/{session_id}/step`: aplica un comando idempotente;
- `GET /monitoring/sessions/{session_id}/ticks?after_sequence=N`: permite
  lectura incremental del ledger.

El identificador de sesión del step procede de la URL y el body solo admite
`command`, `command_id` y `expected_revision`. Los conflictos de revisión, la
ausencia de sesión y la indisponibilidad de artefactos se traducen en respuestas
HTTP diferenciadas.

## 8. Vista 2D de monitorización

La aplicación incorpora una pestaña principal `Monitorización` marcada de
forma visible como `REPLAY HISTÓRICO · no tiempo real`. Desde ella se puede
seleccionar la fuente, preparar una sesión y ejecutar el siguiente tick.

La visualización muestra:

- cuatro tarjetas generadas desde los activos declarados por el backend;
- score, umbral, salud, riesgo y estado solo para el canal modelado;
- RMS, pico absoluto y número de muestras para los canales de telemetría, con
  el diagnóstico expresamente no disponible;
- una gráfica SVG 2D de score frente a umbral, una banda de estados y soporte
  visual para futuros marcadores de trigger;
- un panel de eventos que permanece vacío en P0;
- un cursor de ejecución separado del cursor de inspección.

La inspección solo recorre ticks ya ejecutados. El futuro permanece sombreado
y no seleccionable; volver al cursor de ejecución restaura el último estado
confirmado. Los ritmos `x1`, `x2` y `x5` son una comodidad visual del cliente:
repiten el mismo endpoint de step y no cambian el modo manual persistido.

La evidencia visual de esta vertical se conserva en
`memoria/figuras/captura_web_monitorizacion_hibrida_nasa_replay.png`. La
captura procede de una sesión real completada (689/689 ticks), no de la fixture
E2E, y mantiene visible el alcance P0 sin Qwen, RAG ni triggers.

## 9. Validación realizada

El gate focal de contratos, servicio, API y políticas se ejecutó con:

```bash
conda run -n tfm_v2 python -m pytest -q \
  codigo/tests/test_monitoring_replay_schema.py \
  codigo/tests/test_monitoring_replay_service.py \
  codigo/tests/test_api_monitoring.py \
  codigo/tests/test_modeling_executor.py \
  codigo/tests/test_temporal_health_gaps.py \
  codigo/tests/test_nasa_ims_temporal_policy_v2.py \
  codigo/tests/test_online_blind.py
```

El gate focal actual termina con **75 tests correctos, 1 omitido por dependencia
opcional y 5 subtests correctos**. La integración NASA completa se ejecuta como
test opt-in independiente porque depende de artefactos locales ignorados por
Git.

```bash
TFM_RUN_NASA_REPLAY_INTEGRATION=1 conda run -n tfm_v2 python -m pytest -q \
  codigo/tests/test_nasa_monitoring_replay_integration.py
```

La compilación de producción del frontend también se verificó con
`cd codigo/frontend && npm run build`: TypeScript y Vite finalizaron
correctamente. Vite mantiene un aviso no bloqueante por un chunk WebGL superior
a 500 kB; la vista de replay descrita en este hito es SVG 2D. La suite E2E
aislada completa termina con **18/18 casos correctos** en escritorio y móvil.

Las pruebas cubren, entre otros casos:

- validación cruzada de invariantes de los contratos;
- separación entre canal modelado, telemetría e indisponibilidad;
- whitelist de features y rechazo de columnas de futuro;
- idempotencia, compare-and-swap, recuperación tras commit y fin de sesión;
- exclusión mutua multiproceso y un único commit ante dos avances concurrentes;
- rechazo de políticas manipuladas y de cambios posteriores en el mapeo
  activo/canal;
- rechazo de un checkpoint manipulado incluso cuando se recalcula el hash del
  commit, porque la transición causal ya no coincide con su estado previo;
- rechazo de un score o umbral sustituidos y rehasheados, al volver a contrastar
  el frame con el bundle PCA y las features congeladas;
- rechazo de un estado `completed` prematuro o de actividad agentiva inventada
  dentro de la política P0;
- aislamiento del primer tick al alterar el sufijo futuro;
- registro de fuente, creación, lectura, step e incremental de la API;
- paridad funcional full NASA sobre los 984 snapshots.

La prueba full reconstruye el scoring, los segmentos, los gaps y la salud del
prefijo completo de 984 snapshots y los compara con el artefacto retrospectivo
existente. Coinciden los identificadores, la decisión de anomalía, el segmento,
el indicador de gap y el estado; la diferencia máxima absoluta de score y de
salud suavizada es menor que `1e-10`.

El mismo test opt-in ejecuta además los **689 comandos secuenciales** sobre
`MonitoringReplayStore.step` en un directorio temporal. Cada frame modelado se
contrasta con el oráculo desde el offset 295: score y salud suavizada cumplen
tolerancia `< 1e-10`, estado de salud y segmento coinciden exactamente, y la
sesión termina en `completed`. Este recorrido ya es una regresión automatizada,
aunque no prueba 689 viajes a través del transporte HTTP.

Las pasadas integrales recientes necesitaron entre 108 y 114 segundos en la
máquina local. El store vuelve a parsear y validar el ledger acumulado en cada
step, por lo que el coste estructural actual crece de forma cuadrática durante
una sesión completa. Es suficiente para el replay visual P0, pero debe
reemplazarse por validación incremental o indexada antes de exigir latencia
operacional o sesiones mucho más largas.

Esta integración opt-in necesita los artefactos NASA locales ignorados por
Git. Demuestra paridad de implementación con el pipeline congelado; no recorre
689 commits mediante la API HTTP ni convierte el oráculo retrospectivo en
entrada del servicio.

## 10. Claims permitidos y limitaciones

Este hito permite afirmar que:

- el escenario registrado puede reproducir el scoring y la salud del pipeline
  congelado sin leer valores futuros en cada cálculo;
- un comando aplicado y su tick quedan trazados, validados y recuperables de
  forma idempotente en el store local;
- la interfaz distingue ejecución e inspección y representa visualmente solo
  evidencia ya revelada;
- los canales sin modelo se presentan como telemetría y no como diagnósticos.

No permite afirmar:

- monitorización en tiempo real, streaming industrial o disponibilidad
  continua;
- evaluación sobre holdout no visto, generalización entre activos o
  condiciones, o causalidad física;
- detección de inicio de fallo, RUL, F1/AUC o precisión clínica/industrial;
- independencia estadística de los 984 snapshots: la trayectoria es la unidad
  experimental y los snapshots están correlacionados temporalmente;
- valor de Qwen, fiabilidad de los agentes o mejora atribuible al RAG;
- reducción de carga por triggers o superioridad de una política adaptativa;
- seguridad multiusuario, tolerancia distribuida a fallos, backpressure,
  latencia o despliegue cloud.

El checkpoint ya conserva `last_health_state`, las dos colas necesarias para
salud, las rachas de alerta/recuperación, el timestamp y el segmento. El gap
actual queda en el `MonitoringFrame` comprometido y se visualiza como una
ruptura, pero no existe todavía un estado de episodio ni un ledger de triggers;
esa semántica pertenece al siguiente incremento.

## 11. Siguiente paso original, ya cerrado

El siguiente vertical propuesto era implementar el motor **determinista** de
triggers, con politica versionada, estado de episodio, precedencia,
persistencia, deduplicacion y cooldown, todavia sin Qwen ni RAG. Ese alcance se
ha implementado y se documenta en
`135_fase11_motor_triggers_p3_determinista.md`.

Permanece para un incremento posterior construir la proyeccion
`CausalInputView` y conectar una solicitud de revision acotada con el grafo
multiagente existente.

Este orden permite atribuir primero cuándo y por qué se activa una revisión, y
después estudiar qué decide cada agente y cómo usa la memoria sin confundir
errores de orquestación con fallos del modelo lingüístico.
