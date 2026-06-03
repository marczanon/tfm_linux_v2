# Fase 7 - Hito 4: debate controlado del informe

Fecha: 2026-06-01.

## Objetivo

Implementar una primera ronda de debate controlado entre `report_writer` y
`report_verifier` para corregir el informe final cuando el verificador detecta
afirmaciones no soportadas, exageraciones o limitaciones ausentes.

El objetivo no es forzar una redaccion exacta. El objetivo es evitar que el
informe termine publicando conclusiones falsas o no respaldadas, manteniendo
tolerancia de estilo y dejando una traza humana de como se han tratado las
incidencias.

## Reutilizacion aplicada

Capacidad anadida:

```text
Permitir que el informe final pase por una revision agentica acotada y
auditable antes de cerrar la run.
```

Inventario revisado:

- `codigo/docs/60_fase7_investigacion_debate_controlado_informe.md`;
- `codigo/app/agents/report_writer.py`;
- `codigo/app/agents/report_verifier.py`;
- `codigo/app/executors/reporting.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/run_registry.py`;
- `codigo/app/api/routes.py`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/api.ts`;
- `codigo/tests/`.

Decision:

```text
extend
```

No se ha creado un runner paralelo ni un segundo generador de informes. El
debate vive dentro del tramo de reporting del grafo y reutiliza:

- `report_writer` para proponer el informe y su revision;
- `report_verifier` para verificar el borrador inicial y el revisado;
- `reporting.py` para materializar Markdown de forma determinista;
- `run_persistence.py` y `run_registry.py` para persistir y consultar evidencia.

La unica pieza nueva es `codigo/app/services/report_debate.py`, justificada como
coordinador y renderizador del registro de debate. No toma decisiones nuevas:
solo compone turnos, estado final y artefactos a partir de decisiones ya
validadas.

## Contratos nuevos

Se ha extendido `agent_decisions.py` con:

- `ReportRevisionDecision`: decision estructurada del redactor al responder al
  verificador. Incluye ronda, decision revisada, decision del verificador,
  secciones nuevas, incidencias aceptadas o rechazadas, justificacion de
  rechazos, resumen de cambios y evidencias.
- `issue_id` opcional en `ReportVerificationIssue`, para poder enlazar cada
  objecion con la respuesta del redactor.

Se ha extendido `reasoning.py` con:

- `ReportDebateTurn`: turno resumido y legible del debate;
- `ReportDebateRecord`: registro completo con estado final, rondas usadas,
  turnos, incidencias no resueltas y recomendacion de revision humana.

Estos contratos evitan conversacion libre como salida principal. Cada agente
sigue produciendo JSON validado y el Markdown visible se genera despues a partir
de datos estructurados.

## Flujo implementado

El tramo final del grafo queda asi:

```text
report_writer -> ReportDecision
reporting.py -> final_report.md inicial
report_verifier -> ReportVerificationDecision inicial

si approved:
  cerrar debate como approved_without_revision

si needs_revision o blocked:
  report_writer -> ReportRevisionDecision
  reporting.py -> final_report.md revisado
  report_verifier -> ReportVerificationDecision final
  cerrar debate como approved_after_revision, needs_human_review o blocked
```

La version actual permite una ronda de revision (`max_rounds = 1`). Si tras esa
ronda el verificador no aprueba el informe, el debate queda como
`needs_human_review` o `blocked`; no hay aprobacion silenciosa.

## Artefactos

El debate se persiste bajo el directorio de evidencias del informe:

```text
<directorio_del_informe>/evidence/report_debate.json
<directorio_del_informe>/evidence/report_debate.md
<directorio_del_informe>/evidence/final_report_initial.md
<directorio_del_informe>/evidence/final_report_revision_001.md
```

`report_debate.json` conserva la traza estructurada completa. `report_debate.md`
extrae lineas humanas: agente, intencion, resumen, objeciones, cambios pedidos,
cambios aplicados y evidencias citadas. Esto permite inspeccionar como se
adapta el redactor sin exponer ruido innecesario del JSON.

La auditoria de ejecucion incorpora ahora una seccion `Debate del informe` con
estado, rondas, resumen y conversacion resumida.

## API y frontend

Se ha anadido el endpoint:

```text
GET /runs/{run_id}/report-debate
```

Devuelve `report_debate.md` como `text/markdown`. Si solo existe el JSON, el
registro puede renderizar una vista fallback.

La app carga el debate al seleccionar una run y muestra un panel propio
`Debate del informe`, situado despues del informe final y la auditoria de
ejecucion. Tambien se ha anadido `report_verifier` a la oficina agentica y se
han mejorado las traducciones humanas de eventos para campos como
`verification_status`, `debate_round`, `human_summary`, correcciones y cambios.

## Conversacion agentica en la pestana de agentes

La pestana de agentes incorpora ahora una conversacion compacta, inspirada en
una app de mensajeria, que sustituye al timeline tecnico como vista principal
de comunicacion. La conversacion se alimenta de los eventos runtime y filtra el
ruido de job, ejecutores y JSON completo. Cada mensaje muestra:

- nombre del agente;
- rol funcional;
- accion resumida;
- momento;
- fase, confianza, memoria o veredicto cuando aporta contexto.

El hilo conserva el orden real de trabajo, incluyendo supervisor y todos los
agentes que participen:

```text
supervisor: decide siguiente paso
cleaner: propone limpieza
structurer: organiza ventanas y features
modeler: selecciona algoritmo
evaluator: interpreta metricas
report_writer: prepara o revisa el informe
report_verifier: audita el informe
```

Cada burbuja es clicable y selecciona el agente correspondiente, por lo que la
vista humana se mantiene limpia y el JSON tecnico sigue disponible solo cuando
se necesita inspeccion detallada.

La fuente canonica para el runtime en directo son los eventos de
`AgentRuntimeRecorder`. Para una futura vista historica de conversaciones
persistidas, la fuente natural sera `report_debate.json` y los snapshots de run.

## Ajuste tras prueba completa

Durante una run completa (`prueba_conversaciones`) se detectaron dos problemas:

- el LLM del verificador podia devolver un JSON semanticamente razonable pero
  con nombres de campo fuera de `ReportVerificationDecision`;
- el verificador determinista castigaba disclaimers como "no equivale a
  validacion industrial final", tratandolos como si fueran claims industriales.

Se ha anadido una normalizacion determinista de alias frecuentes antes de la
validacion Pydantic estricta y se ha cambiado el fallback para que no exponga
errores Pydantic crudos en la UI. Tambien se ha hecho la regla de "validacion
industrial" sensible a negaciones, alcance local y disclaimers metodologicos.

Ademas, el evento runtime del verificador usa ahora `summary` humano como
resumen visible, dejando el `rationale` tecnico en el detalle JSON.

## Verificacion

Pruebas ejecutadas:

```text
python -m py_compile codigo/app/schemas/agent_decisions.py codigo/app/schemas/reasoning.py codigo/app/agents/report_writer.py codigo/app/agents/report_verifier.py codigo/app/services/report_debate.py codigo/app/graph/pipeline.py codigo/app/services/llm_agents.py codigo/app/services/pipeline_runner.py codigo/app/services/run_persistence.py codigo/app/services/run_registry.py codigo/app/api/routes.py
python -m unittest codigo.tests.test_agent_decisions_schema codigo.tests.test_report_writer_agent codigo.tests.test_report_verifier_agent codigo.tests.test_report_debate codigo.tests.test_graph_pipeline codigo.tests.test_run_persistence codigo.tests.test_run_registry codigo.tests.test_api_runs codigo.tests.test_pipeline_runner
npm run build
```

Resultado:

```text
83 tests OK
frontend build OK
```

Verificacion adicional de la conversacion agentica:

```text
npm run build
```

Resultado:

```text
frontend build OK
```
