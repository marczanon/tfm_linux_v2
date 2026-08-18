# Fase 11: PolicyProposal consultiva multirol

Fecha: 2026-08-12

Estado: incremento implementado y comprobado mediante validacion focal de
software. No se ha ejecutado Qwen, no se ha repetido el replay NASA completo,
no se ha publicado un gate nuevo y no se ha aplicado ninguna politica.

## 1. Resultado y frontera

Este incremento convierte las siete recomendaciones ya estructuradas de una
revision de monitorizacion en un expediente consultivo unico y auditable:

```text
trigger causal
  -> run hija propose-only
  -> siete decisiones de rol
  -> sintesis determinista del servidor
  -> MonitoringPolicyProposal
       -> siete contribuciones atribuibles
       -> advisory_not_applied
       -> application_status = not_applied
```

La sintesis no es una octava opinion agentica. El propio contrato declara
`proposal_origin=deterministic_server`, ademas del `trace_origin` equivalente
del evento runtime. Conserva y clasifica lo que recomendaron los roles, pero no
genera una nueva recomendacion, no interpreta texto libre para extraer
parametros y no decide que alternativa es mejor.

Este vertical cierra solo la primera parte consultiva del Bloque G de la hoja
133. No implementa `ValidationRecord`, aprobacion humana, `ApplicationRecord`,
una version candidata de scoring o activacion ni el modo
`adaptive_replay_exploratory`.

## 2. Decision de reutilizacion

La capacidad se definio como: proyectar las siete decisiones selladas de una
run hija en una sintesis consultiva sin duplicar la revision, la persistencia o
la superficie web.

Se extienden los propietarios canonicos existentes:

- `monitoring_replay.py` conserva los contratos estrictos y hasheados;
- `pipeline_runner.py` conoce el resultado completo de los siete roles y
  orquesta la sintesis;
- `run_persistence.py` guarda y vuelve a validar la propuesta junto a la run;
- los eventos runtime existentes transportan su proyeccion consultable;
- `AgentObservabilityView` la muestra dentro de la sala **Agentes**.

No existia un propietario para la sintesis entre roles. Por ello se incorpora
un servicio puro de propuesta consultiva. No conoce FastAPI, no llama al LLM,
no lee datos NASA, no modifica el replay y no posee aplicacion de politicas. No
se crea un endpoint ni una pantalla independientes.

## 3. Contrato agregado y contribuciones

Cada `MonitoringPolicyProposal` pertenece a una unica run hija y contiene
exactamente siete `PolicyProposalContribution`, una por cada decision y en el
orden canonico:

1. supervisor;
2. limpiador;
3. estructurador;
4. modelador;
5. evaluador;
6. redactor;
7. verificador.

Cada contribucion conserva la identidad de su decision, el rol, la accion
original, su categoria consultiva, el fundamento, los riesgos, la necesidad
declarada de revision humana y las evidencias que realmente selecciono ese rol.
El fundamento sigue siendo una declaracion de la decision, no un impacto
verificado. Las referencias canonicas por registro se resuelven bajo autoridad
del servidor hacia los handles `E01..EN` del catalogo sellado. Una referencia
ausente, duplicada o ajena al catalogo no se completa ni se acepta
silenciosamente.

La propuesta agregada conserva `proposal_origin=deterministic_server`, el
request, la run hija, el trigger, el cutoff, las politicas activas, la vista
causal, el catalogo de evidencia y sus hashes. El evidence pack la enlaza
despues con el resultado persistido. Su identidad y su SHA-256 se derivan del
contenido canonico, de forma que una alteracion de las contribuciones, el orden,
la evidencia, el origen o el estado deja de validar.

## 4. Mapeo semantico cerrado

Las decisiones actuales no contienen un parametro de politica ni un valor
numerico propuesto. La sintesis no los inventa. Aplica exclusivamente este
mapeo cerrado:

| Accion | Categoria | Sujeto | Estado consultivo actual -> propuesto |
|---|---|---|---|
| `maintain_policy` | `no_change` | `policy_configuration` | `unchanged -> unchanged` |
| `intensify_observation` | `observation` | `observation_cadence` | `current_schedule -> intensification_requested` |
| `request_human_review` | `workflow` | `human_review` | `not_requested -> requested` |
| `pause_replay` | `workflow` | `replay_execution` | `current_execution -> pause_requested` |
| `insufficient_evidence` | `abstain` | `policy_change` | `unchanged -> withheld` |

Por tanto, el objeto no contiene un diff numerico, un `target_policy_kind`, una
version nueva, un cursor efectivo ni una configuracion ejecutable. La categoria
es una proyeccion protocolaria de la accion original, no una estimacion de su
impacto. Los estados de la ultima columna describen la intencion consultiva; por
ejemplo, `requested` no significa que el sistema haya cursado una revision
humana.

## 5. Unanimidad, desacuerdo e invalidez

La agregacion no usa votacion, mayoria, pesos por confianza ni un nuevo modelo.
Solo expone una accion agregada cuando las siete contribuciones validas son
unanimes. Si los roles recomiendan acciones distintas, el resultado es
`disagreement` y se conservan todas las aportaciones sin fabricar consenso.

La propuesta solo se construye cuando existen las siete decisiones canonicas.
Si alguna contribucion tiene `generation_origin` distinto de `llm` ---incluido
un fallback, una decision protocolaria o determinista---, el agregado queda
`invalid_review`. Una revision con un rol `failed` o `not_run` y sin decision
no puede producir la propuesta. Esta frontera impide presentar continuidad
protocolaria como una recomendacion colectiva agentiva.

La recomendacion agregada de revision humana se calcula como el OR de
`decision.requires_human_review`. Significa un requisito consultivo para un
paso posterior; no constituye una solicitud tramitada, una revision realizada
ni una aprobacion.

En todos los casos, el estado permanece `advisory_not_applied` y
`application_status=not_applied`. Ademas,
`policy_validation_eligible=false`: este objeto no puede cruzar por accidente
la futura frontera de validacion.

## 6. Persistencia, traza e interfaz

La propuesta se persiste como artefacto de la run y se enlaza al estado, al
resultado de monitorizacion y al evidence pack. La lectura vuelve a verificar
su hash, las siete decisiones fuente, el orden de roles, el catalogo y la
resolucion exacta de evidencias antes de proyectarla en runtime.

La sala **Agentes** muestra esta sintesis con dos rotulos permanentes:
`Consultiva` y `No aplicada`. La lectura compacta distingue unanimidad,
desacuerdo o revision invalida; permite inspeccionar las siete contribuciones,
sus handles de evidencia y si algun rol recomienda revision humana. Las
referencias canonicas largas permanecen en el payload tecnico.

No se anaden controles de aprobar, rechazar, activar o aplicar. La ausencia de
esos controles forma parte de la frontera del incremento: la interfaz explica
una recomendacion registrada, pero no simula un ciclo de gobierno que todavia
no existe.

## 7. Significado cientifico

El resultado demuestra una propiedad de ingenieria: siete decisiones ya
disponibles pueden convertirse de forma determinista en una representacion
agregada, trazable y resistente a manipulaciones, sin borrar desacuerdos ni
confundir un origen no LLM con autoria agentica.

No demuestra que Qwen pueda producir mejores propuestas bajo este contrato. La
sintesis no evalua si las recomendaciones estan semanticamente sostenidas por
las filas citadas, si son tecnicamente adecuadas ni si producirian un efecto
beneficioso. `observation`, `workflow` o `no_change` son categorias
consultivas, no resultados de una intervencion.

Este incremento tampoco altera la evidencia publicada. V2 y V3 conservan sus
artefactos, cifras y bloqueos; `current.json` sigue apuntando al resultado V3.

## 8. Verificacion realizada

La verificacion se limita a pruebas focales de software con decisiones y
clientes simulados. Comprueba el contrato canonico, las siete contribuciones,
el mapeo cerrado, unanimidad, desacuerdo, `invalid_review` ante fallback, OR de
revision humana, resolucion de handles, persistencia, manipulacion, traza y
proyeccion visual. El contrato exige las siete decisiones antes de construir
la propuesta.

No se ha llamado a Qwen, no se ha recorrido de nuevo NASA IMS Set 2, no se ha
ejecutado una bateria `3 x 4 x 7` y no se ha publicado una V4. Las fixtures y
los recuentos de tests no son replicas cientificas ni evidencia de calidad
agentica.

## 9. Claims permitidos

Este incremento permite afirmar que:

- existe un contrato agregado, estricto y hasheado para representar de forma
  consultiva las siete recomendaciones de una run hija;
- cada contribucion conserva su autor, decision y soporte por registro;
- la autoria de la sintesis queda autocontenida como
  `proposal_origin=deterministic_server`;
- el servidor aplica un mapeo semantico cerrado sin inventar numeros, targets o
  versiones de politica;
- unanimidad, desacuerdo y origen no LLM permanecen distinguibles, mientras
  una revision sin las siete decisiones no produce una propuesta;
- una necesidad de revision humana puede recomendarse sin presentarla como
  aprobacion;
- propuesta, traza y vista web declaran siempre que no hubo aplicacion;
- las invariantes anteriores se han comprobado mediante pruebas focales de
  software.

## 10. Claims prohibidos

Este incremento no permite afirmar:

- que Qwen haya ejecutado o superado el nuevo contrato;
- que los agentes hayan elegido un parametro, valor numerico o nueva version;
- que exista consenso cuando las siete acciones no sean unanimes;
- que una categoria consultiva constituya un cambio validado o ejecutable;
- que la evidencia citada confirme semanticamente la recomendacion;
- que haya ocurrido revision, aprobacion o aplicacion humana;
- que exista una politica candidata, activa o adaptativa;
- que hayan cambiado scoring, umbral, triggers, replay o estado de salud;
- que la propuesta mejore deteccion, falsas alarmas, anticipacion, onset o RUL;
- que exista generalizacion, tiempo real o preparacion industrial.

## 11. Trabajo pendiente

El siguiente cierre está preparado en
`141_fase11_campana_monitorizacion_agentiva_56h.md`: una única campaña P3
histórica acelerada, prerregistrada y con cuatro revisiones sobre la ventana
`353..688`. Mantiene este mismo contrato, memoria OFF y propuestas no aplicadas,
y separa el veredicto operativo del agentivo. En el cierre descrito por la hoja
141 la campaña todavía no se ha ejecutado; solo existe un smoke diagnóstico
separado del primer trigger, que no constituye el resultado de campaña.

Antes de una politica aplicable siguen siendo necesarios hitos separados:
evaluacion independiente de soporte y utilidad, un contrato que permita
proponer valores dentro de rangos predeclarados, `ValidationRecord`, Human
Review real y `ApplicationRecord` exclusivamente hacia delante. Solo entonces
podra estudiarse `adaptive_replay_exploratory`, sin convertir una activacion
correcta en evidencia automatica de mejora.
