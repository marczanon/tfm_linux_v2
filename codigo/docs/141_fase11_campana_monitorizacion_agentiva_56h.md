# Fase 11: campaña de monitorización agentiva de 55 h 50 min

Fecha: 2026-08-18

Estado: campaña y superficie de evidencia implementadas con pruebas focales de
software. No se ha ejecutado todavía la campaña oficial. Se ha realizado un
único smoke diagnóstico separado sobre el primer trigger con Qwen; no forma
parte del resultado de campaña ni sustituye sus cuatro contextos. Las baterías
V2 y V3 y su puntero publicado permanecen inalterados.

## 1. Objetivo de cierre

El objetivo inmediato no es ampliar de nuevo la autonomía de los agentes, sino
poner en condiciones de ejecución prolongada el 90 % del sistema ya construido
y obtener una evidencia única, legible y auditable del ciclo completo:

```text
replay NASA P3 histórico acelerado
  -> pre-roll causal
  -> cuatro triggers primarios
  -> cuatro runs hijas single-flight
  -> siete decisiones por run
  -> cuatro propuestas consultivas
  -> veredicto operativo + veredicto agentivo
```

La campaña se identifica por defecto como
`nasa-p3-agentic-window-56h-v1`. Sigue siendo un replay histórico offline, no
streaming ni tiempo real industrial. La duración de 55 h 50 min pertenece al
reloj de la fuente NASA; no es una promesa de duración de pared.

## 2. Decisión de reutilización y frontera

La capacidad se definió como: ejecutar y observar una sesión P3 completa con
ritmo configurable, prerregistro, estado incremental y un cierre dual, sin
crear otro replay ni otro grafo.

Se reutilizan sin duplicación:

- `MonitoringReplayStore`, sus 689 ticks y su ledger causal;
- el motor P3 y sus cuatro contextos primarios ya congelados;
- `run_full_session_review_cycle`, que avanza, despacha y espera cada hija;
- el bridge `trigger -> CausalInputView -> MonitoringReviewRequest`;
- los siete roles y el contrato generativo actual con catálogo `E01..EN`;
- el observador de fiabilidad y la traza física de Ollama;
- `MonitoringPolicyProposal`, siempre consultiva y no aplicada;
- la persistencia, el endpoint de lectura y la sala de Monitorización.

El servicio de campaña es nuevo porque ninguna pieza existente era propietaria
del prerregistro, el progreso y el veredicto conjunto de una ejecución larga.
Su frontera termina en resumir artefactos ya producidos. No decide por los
agentes, no cambia el detector, no aplica una política y no introduce workers,
colas ni un scheduler distribuido.

## 3. Por qué no se cambia ahora el contrato agentivo

El contrato actual cierra las acciones ejecutables, pero conserva libertad
observable para que cada rol:

- formule una hipótesis, su observación esperada y su criterio de refutación;
- seleccione filas concretas del catálogo causal;
- declare confianza, riesgos y supuestos;
- elija una acción principal y alternativas;
- contraste los aportes previos desde su misión especializada.

Añadir ahora valores paramétricos obligaría a versionar prompt y esquema,
propagar el cambio por persistencia, API, web y tests, y abrir las fronteras de
`ValidationRecord`, Human Review y `ApplicationRecord`. Eso reemplazaría el
objetivo de evidencia por otro rediseño y haría menos comparable la nueva
ejecución con el instrumento ya auditado.

Por tanto, la campaña congela el contrato actual. Las propuestas paramétricas
acotadas permanecen como trabajo posterior. Esta decisión no afirma que el
catálogo actual sea el diseño final de autonomía; afirma que es suficiente para
cerrar la demostración consultiva y medir su comportamiento real.

## 4. Ventana temporal exacta

La sesión conserva los 689 snapshots de monitoring. No se inicia directamente
en el primer trigger, porque eso eliminaría el estado causal que lo origina.

| Tramo | Cursores inclusivos | Snapshots | Función |
| --- | ---: | ---: | --- |
| Pre-roll causal | `0..352` | 353 | reconstruir scoring, salud, persistencia y estado antes de la primera revisión |
| Ventana agentiva | `353..688` | 336 | observar los cuatro triggers y sus revisiones |

La ventana agentiva empieza en `2004-02-16T22:32:39` y termina en
`2004-02-19T06:22:39`. La diferencia entre ambos instantes es 201.000 segundos,
es decir, 55 horas y 50 minutos. La fuente no declara zona horaria y la
interfaz debe mantener el rótulo correspondiente; no se añade `UTC` ni una zona
local inventada.

Los cuatro contextos esperados son:

1. transición de estado en el cursor 353;
2. alerta persistente iniciada en 496 y confirmada en 498;
3. transición de estado en el cursor 499;
4. cierre de sesión en el cursor 688.

El plan espera cuatro triggers, cuatro hijas, 28 decisiones de rol y cuatro
`MonitoringPolicyProposal`. Son observaciones internas de una misma
trayectoria, no 28 réplicas independientes.

## 5. Pacing y heartbeat

El runner común acepta dos parámetros opcionales:

- `step_interval_seconds`, con valor histórico compatible `0` fuera de esta
  campaña;
- `heartbeat_interval_seconds`, también desactivado con `0` en los usos
  anteriores.

La primera orden `step` de una invocación es inmediata. Antes de los siguientes
ticks, el runner espera solo cuando no existe un trigger pendiente ni una hija
activa. De esta forma el pacing no retrasa un dispatch ya emitido y no modifica
la regla single-flight. Cada espera positiva emite `pacing_wait_started`; si
hay heartbeat, la divide en tramos no superiores a ese intervalo y emite
`campaign_heartbeat` después de cada tramo.

La campaña usa por defecto:

```text
source_cadence_seconds = 600
speed_multiplier = 60
step_interval_seconds = 600 / 60 = 10
heartbeat_interval_seconds = 5
```

El multiplicador es configurable desde CLI y el intervalo de step siempre se
deriva de la cadencia fuente. El heartbeat no puede superar dicho intervalo.
La duración runtime incluye pacing, llamadas a Qwen y pausas guiadas; por ello
no se deduce únicamente dividiendo 201.000 entre el multiplicador.

## 6. Plan, estado y publicación

`MonitoringEvidenceCampaignPlan` congela antes de ejecutar:

- identidad de campaña y sesión;
- dataset, escenario, P3 y `frozen_benchmark`;
- límites del pre-roll y la ventana agentiva;
- cadencia, multiplicador, pacing y heartbeat;
- cuatro contextos y siete roles;
- recuentos esperados;
- digest y configuración de Qwen;
- fingerprints del contrato generativo;
- hashes de las fuentes críticas.

El plan y el prerregistro son inmutables. `--execute` rechaza la ejecución si
una fuente congelada ha cambiado o si la etiqueta de Ollama ya no resuelve al
digest previsto. El sello incluye el replay, el motor P3, la captura física de
intentos, el grafo de revisión, la propuesta consultiva, la persistencia y el
propio CLI, además de sus contratos directos.

`MonitoringEvidenceCampaignState` publica una proyección incremental y
hasheada con:

- fase `planned`, `pre_roll`, `agentic_window` o `completed`;
- revisión y cursor confirmados;
- progreso sobre 689 ticks;
- lifecycle de las cuatro revisiones;
- decisiones, orígenes LLM, reparaciones y fallbacks;
- propuestas consultivas observadas;
- bloqueos y duración runtime.

Cada identidad conserva además su propio `publication.json`; `current.json`
solo señala la campaña visible en la web. Un `flock` exclusivo impide dos
ejecuciones simultáneas y la publicación rechaza retrocesos de cursor,
contadores, expedientes o lifecycle. Una campaña iniciada, fallida o terminada
no se reanuda: requiere una identidad y una sesión nuevas. El resultado sella
la matriz exacta de cuatro contextos por siete roles y el ledger global de
llamadas físicas, sin guardar payloads del modelo.

La publicación referencia el prerregistro, el plan, el estado y, tras el
cierre, el resultado. También comprueba que el prerregistro preceda al inicio
de la ejecución. La lectura vuelve a verificar todos los hashes. El endpoint
`GET /monitoring/evidence-campaigns/current` expone únicamente esta proyección
estrecha, incluidos los sellos y fechas mínimos de prerregistro y publicación,
y devuelve ausencia o conflicto de integridad de forma explícita.

La sala web actúa como observador. Permite abrir la sesión publicada y ver
progreso, fase, cuatro revisiones, decisiones, fallbacks y propuestas. El
navegador no avanza una campaña gestionada ni permite despachar manualmente sus
triggers.

## 7. Dos veredictos y uno conjunto

El cierre separa propiedades que no deben mezclarse.

### Veredicto operativo

Pasa si:

- la sesión observada conserva la identidad prerregistrada;
- memoria sigue `off` y ninguna política pasa de `not_applied`;
- la sesión termina;
- se confirman exactamente 689 ticks;
- los cuatro contextos conservan orden, tipo, motivo, inicio de condición y
  cutoff del pack P3 congelado;
- existen exactamente cuatro expedientes hijos terminales, con identidades de
  trigger y run hija presentes y sin colisiones;
- el ledger primario contiene exactamente 14 eventos, diez de ellos suprimidos;
- el presupuesto variable termina con tres slots reservados de siete.

Este veredicto mide el motor y su orquestación. No demuestra por sí solo que
las respuestas generativas sean válidas.

### Veredicto agentivo

Pasa si:

- existen exactamente 28 observaciones de rol;
- las cuatro hijas terminan resueltas;
- no hay fallback, decisión no agentiva ni error;
- las 28 decisiones cumplen traza, binding, grounding, estructura de
  hipótesis, alcance, catálogo, memoria OFF y política no aplicada;
- se generan cuatro propuestas `advisory_not_applied` / `not_applied`;
- al menos el 90 % valida al primer intento.

Una reparación permanece visible y reduce la primera pasada. Un fallback
bloquea el veredicto agentivo aunque el mecanismo seguro permita cerrar el
replay.

### Veredicto de evidencia

Solo pasa cuando los veredictos operativo y agentivo pasan. Un resultado
bloqueado se publica igualmente; no se repite selectivamente una hija ni se
oculta el caso adverso.

## 8. Modos del CLI

Preparación sin Qwen ni sesión:

```bash
python -m codigo.scripts.run_monitoring_evidence_campaign --plan-only
```

Este modo crea plan, prerregistro, estado `planned` y publicación verificable.
No crea FastAPI, no abre una sesión, no construye el cliente de Ollama y no
consulta el modelo. Si se omite tanto `--plan-only` como `--execute`, el
comportamiento sigue siendo plan-only.

Ejecución explícita:

```bash
python -m codigo.scripts.run_monitoring_evidence_campaign --execute
```

La velocidad y el heartbeat pueden configurarse, por ejemplo:

```bash
python -m codigo.scripts.run_monitoring_evidence_campaign \
  --plan-only \
  --speed-multiplier 120 \
  --heartbeat-interval-seconds 2
```

Una identidad ya prerregistrada no admite otro contenido. Para usar una
configuración distinta debe elegirse un `--campaign-id` nuevo antes de observar
resultados. `--execute` exige además que su directorio de sesión todavía no
exista: no incorpora ticks, runs hijas ni llamadas físicas anteriores al
prerregistro. Los fallos de preflight se publican como `failed`, en vez de dejar
una campaña aparentemente preparada.

Tras una ejecución cerrada se esperan:

```text
codigo/reports/validation/monitoring_evidence_campaign/
  current.json
  <campaign_id>/
    plan.json
    preregistration.json
    publication.json
    final_state.json
    result.json
    observations.jsonl
    report.md
    states/
      <state_sha256>.json
```

## 9. Verificación focal realizada

Las pruebas de software cubren, sin esperar tiempos reales ni llamar a Qwen:

- cálculo de pre-roll, ventana, duración fuente e intervalo derivado;
- rechazo de heartbeat incompatible;
- pacing desactivado compatible con el runner anterior;
- espera fragmentada mediante reloj y `sleep` inyectables;
- emisión de `pacing_wait_started` y `campaign_heartbeat`;
- ausencia de retraso del primer dispatch por pacing;
- transición de estado entre pre-roll, ventana y revisión terminal;
- separación entre veredicto operativo y agentivo;
- prerregistro, publicación, lectura y rechazo de manipulación;
- monotonía ante estados obsoletos, historial independiente por campaña y
  exclusión de ejecución concurrente;
- matriz exacta `4 x 7`, binding de sesión/hija y ledger físico sin reutilizar
  un mismo intento entre roles;
- rechazo de una sesión previa y publicación explícita de fallos de preflight;
- modo plan-only sin FastAPI, sesión ni Ollama;
- verificación de fuentes y digest antes de crear la aplicación en modo
  execute;
- proyección API y presentación compacta en modo observador.

Estas pruebas validan contratos, orquestación y visualización. No son la
campaña, no son 28 decisiones reales y no permiten afirmar que Qwen haya
superado el catálogo actual.

### 9.1 Smoke diagnóstico previo

Tras cerrar la auditoría se ejecutó una sesión nueva y excluida de la campaña,
`nasa-p3-catalog-smoke-20260818-02`, sin pacing y solo hasta el primer trigger
del cursor 353. La hija `mon-review-82b4409675767ab65684780d` terminó
`resolved`: los siete roles tuvieron origen `llm`, validación contractual en el
intento 1 y cero fallback. El catálogo contenía 12 registros; las selecciones
materializadas fueron E09, E10, E11 y E12 en subconjuntos diferentes según el
rol. La síntesis produjo siete contribuciones, desacuerdo explícito,
`advisory_not_applied`, `not_applied` y elegibilidad de validación falsa.

Un intento técnico anterior, ejecutado dentro de un sandbox que impedía la
consulta local de estado de Ollama, fue rechazado con 503 antes de reservar una
hija o llamar a Qwen. Ambos intentos son diagnósticos y quedan fuera del
prerregistro oficial.

Este smoke comprueba que el camino mecánico actual funciona en un contexto. No
demuestra estabilidad en los otros tres triggers, calidad semántica, fiabilidad
general ni superación del futuro veredicto agentivo.

## 10. Estado real al cierre

En este cierre:

- el plan oficial `nasa-p3-agentic-window-56h-v1` está prerregistrado y
  publicado en estado `planned`, revisión 0, sin crear todavía su sesión;
- el plan tiene SHA-256
  `2c6b1ad76904bac23970e35965fade6eac883d31b6c1c6ef8e4200b4ea65b95e`,
  el prerregistro
  `f6330ec721f2f1063cb9b34b5a8e8b26d0088ffc5d87ccc0ac014b83fe1d9ae7`
  y la publicación preparada
  `d84c1971e96768e69079752da281c2ae6485c9fd6427f459acd777f369565813`;
- la configuración por defecto es 60x, 10 s por step y heartbeat de 5 s;
- memoria permanece OFF;
- ninguna propuesta puede aplicarse;
- el smoke diagnóstico del primer trigger produjo 7/7 decisiones LLM sin
  fallback y una propuesta no aplicada con desacuerdo visible;
- no se ha ejecutado el comando oficial `--execute`;
- no se ha llamado a Qwen dentro de la campaña oficial;
- no existen cuatro nuevas hijas, 28 decisiones reales ni cuatro propuestas
  empíricas atribuibles a este hito;
- no se ha publicado V4 ni se ha modificado el resultado V3 o su `current.json`.

El siguiente paso es ejecutar una vez la campaña completa ya prerregistrada.
El resultado se conservará tanto si pasa como si queda bloqueado.

## 11. Claims permitidos

Se puede afirmar que:

- existe un protocolo ejecutable y prerregistrable para recorrer la sesión P3
  y observar una ventana agentiva de 55 h 50 min de tiempo fuente;
- el pacing es configurable, emite heartbeat y mantiene dispatch y
  single-flight fuera de la espera;
- la campaña separa éxito operativo y éxito agentivo;
- su estado y su resultado tienen publicación verificable;
- el frontend puede observar una campaña sin gobernarla;
- el diseño reutiliza el replay, los agentes y la propuesta existentes sin
  cambiar el contrato generativo.
- un smoke diagnóstico separado recorrió correctamente el primer trigger bajo
  el catálogo por registro y produjo siete decisiones LLM contractualmente
  válidas sin aplicar política alguna.

## 12. Claims todavía prohibidos

No se puede afirmar que:

- la campaña oficial se haya ejecutado o superado;
- Qwen haya producido 28 decisiones de campaña o decisiones físicamente
  correctas bajo el catálogo actual;
- existan cuatro propuestas empíricas nuevas;
- una propuesta sea correcta, útil, validada o aplicada;
- el replay equivalga a 55 h 50 min de operación industrial real;
- el pacing demuestre disponibilidad, latencia o tolerancia a fallos de planta;
- se haya implementado adaptación automática, RAG o generalización a otros
  datasets;
- el nuevo protocolo cambie o repare retrospectivamente V2 o V3.
