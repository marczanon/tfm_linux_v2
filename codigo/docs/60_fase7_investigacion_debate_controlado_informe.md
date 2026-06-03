# Fase 7 - Investigacion: debate controlado para pulir el informe

Fecha: 2026-06-01.

Estado: investigacion aplicada en el Hito 4. La implementacion final queda
documentada en `codigo/docs/61_fase7_hito4_debate_controlado_informe.md`.

## Capacidad investigada

Encajar un debate controlado entre `report_writer` y `report_verifier` para
pulir el informe final sin permitir conversacion libre, codigo generado ni
afirmaciones fuera de la evidencia.

El objetivo no es que el informe acabe con una redaccion exacta y rigida. El
objetivo es que los agentes puedan discutir incidencias factuales, adaptar el
texto y dejar una traza humana de como se corrigio o se justifico cada punto.

## Inventario previo anti-duplicacion

Busquedas y piezas revisadas:

- `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`;
- `codigo/docs/55_recap_mejoras_fase7.md`;
- `codigo/docs/59_fase7_hito3_verificador_agentico_informe.md`;
- `codigo/app/agents/report_writer.py`;
- `codigo/app/agents/report_verifier.py`;
- `codigo/app/executors/reporting.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/run_registry.py`;
- `codigo/app/services/api_run_jobs.py`;
- `codigo/app/services/memory_usage_audit.py`;
- `codigo/app/services/decision_memory.py`;
- `codigo/app/api/routes.py`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/api.ts`;
- `codigo/frontend/src/types.ts`;
- `codigo/frontend/src/styles.css`;
- `codigo/tests/test_report_verifier_agent.py`;
- `codigo/tests/test_graph_pipeline.py`;
- `codigo/tests/test_run_persistence.py`.

Decision preliminar:

```text
extend
```

Motivo: el sistema ya tiene propietarios claros:

- `report_writer.py` decide y redacta contenido validado;
- `report_verifier.py` verifica factualidad con evidencia cerrada;
- `reporting.py` materializa Markdown de forma determinista;
- `pipeline.py` orquesta reporting y verificacion;
- `run_persistence.py` extrae decisiones, evidence pack y auditoria;
- el frontend ya muestra informe, auditoria, artefactos y eventos runtime.

Crear otro runner o un flujo paralelo de informes duplicaria responsabilidades.
Solo podria justificarse un servicio nuevo pequeno si actua como coordinador de
debate dentro del tramo de reporting, sin sustituir a los agentes ni al
ejecutor.

## Estado actual relevante

Hoy el flujo es:

```text
report_writer -> ReportDecision -> reporting.py -> final_report.md
             -> report_verifier -> ReportVerificationDecision
             -> report_verification.json / report_verification.md
             -> execution_audit.md
```

El verificador ya distingue:

- `approved`;
- `needs_revision`;
- `blocked`.

Tambien deja incidencias estructuradas:

- afirmaciones sin soporte;
- afirmaciones enganosas o de politica;
- limitaciones ausentes;
- correcciones requeridas;
- notas de tolerancia aceptable.

Limitacion actual: la verificacion no devuelve el control al redactor. Si hay
incidencias, quedan auditadas, pero no existe aun una ronda de revision.

## Restricciones metodologicas

El debate debe cumplir estas reglas:

- maximo de rondas fijo, preferiblemente `1` inicialmente y como mucho `2`;
- cada turno debe ser JSON validado por Pydantic;
- no hay conversacion libre persistida como fuente principal;
- no se expone cadena de pensamiento privada;
- se exponen resumenes, objeciones, cambios y evidencias declaradas;
- los agentes no ejecutan codigo ni leen rutas arbitrarias;
- la unica correccion material del informe pasa por `ReportDecision` validado y
  `reporting.py`;
- toda afirmacion nueva debe citar evidencia del catalogo permitido;
- si queda una incidencia critica tras las rondas permitidas, el resultado pasa
  a `needs_human_review` o `blocked`, no a aprobacion silenciosa.

## Encaje recomendado

La forma mas robusta es introducir un coordinador acotado dentro del tramo de
reporting, no un nodo de grafo independiente en esta primera version:

```text
1. report_writer genera ReportDecision inicial.
2. reporting.py escribe borrador inicial.
3. report_verifier verifica el borrador.
4. si approved: se termina el debate con estado approved.
5. si needs_revision o blocked:
   5.1 report_writer recibe incidencias y propone ReportRevisionDecision.
   5.2 reporting.py escribe borrador revisado.
   5.3 report_verifier reevalua el borrador revisado.
6. se persiste el paquete de debate y se expone una vista humana.
```

El debate no deberia modificar metricas, configuraciones ni evaluacion. Solo
puede modificar el informe final o declarar que necesita revision humana.

## Contratos candidatos

### ReportRevisionDecision

Podria vivir en `agent_decisions.py` porque es una decision directa del agente
redactor.

Campos recomendados:

```text
agent_name = report_writer
decision_id
revision_round
revision_of_decision_id
verifier_decision_id
rationale
confidence
accepted_issue_ids
rejected_issue_ids
rejection_rationales
changes_summary
sections: list[ReportSection]
evidence_refs
output_path
output_format = markdown
```

Reglas:

- debe conservar todas las secciones obligatorias;
- debe responder a cada incidencia de severidad alta o critica;
- si rechaza una correccion, debe justificar por que era estilo, no falsedad;
- `source_paths` y `evidence_refs` deben estar en el catalogo cerrado.

### ReportDebateTurn

Podria vivir en `agent_decisions.py` o en un nuevo bloque de `reasoning.py`.
Como representa evidencia de deliberacion mas que una decision ejecutora, el
encaje mas limpio parece `reasoning.py`.

Campos recomendados:

```text
turn_id
round_index
speaker_agent
source_decision_id
intent
human_summary
claims_or_objections
accepted_points
rejected_points
changes_requested
changes_applied
evidence_refs
status
created_at
```

Este contrato permite extraer lineas legibles sin mostrar todo el JSON bruto.

### ReportDebateRecord

Registro completo de la deliberacion:

```text
debate_id
run_id
initial_report_decision_id
final_report_decision_id
final_verifier_decision_id
status
max_rounds
rounds_used
turns
final_summary
unresolved_issues
human_review_recommended
artifacts
created_at
```

Estados recomendados:

```text
approved_without_revision
approved_after_revision
needs_human_review
blocked
inconclusive
```

## Artefactos recomendados

Persistir bajo el directorio de evidencias del informe:

```text
<directorio_del_informe>/evidence/report_debate.json
<directorio_del_informe>/evidence/report_debate.md
<directorio_del_informe>/evidence/final_report_initial.md
<directorio_del_informe>/evidence/final_report_revision_001.md
```

`final_report.md` deberia apuntar a la version final elegida, pero las versiones
intermedias deben conservarse para auditoria. No conviene sobrescribir el
borrador inicial sin dejar copia.

El Markdown humano deberia contener una vista asi:

```text
# Debate controlado del informe <run_id>

## Resultado
- Estado: approved_after_revision
- Rondas usadas: 1/1
- Informe final: final_report.md

## Ronda 1
### Verificador
- Objecion: "validacion industrial completa"
- Motivo: no hay evidencia de despliegue industrial
- Severidad: alta
- Evidencia: report:final_report, objective:binary_anomaly_detection
- Correccion pedida: reformular como validacion local del TFM

### Redactor
- Acepta: si
- Cambio aplicado: sustituye la frase por "validacion local reproducible"
- Evidencia usada: evaluation:approved, metric:f1_score

### Re-verificacion
- Estado: approved
- Incidencias restantes: 0
```

Esto responde al objetivo de ver como procesan informacion y como se adaptan,
sin abrir la puerta a cadena de pensamiento privada.

## Correccion determinista

La "herramienta de correccion" no debe ser un editor libre de texto. Debe ser:

```text
ReportRevisionDecision validado -> reporting.py -> Markdown revisado
```

El agente propone secciones corregidas. El ejecutor determinista renderiza el
documento y vuelve a aplicar las reglas existentes:

- formato Markdown;
- output path controlado;
- secciones obligatorias;
- fuentes permitidas;
- evidencias registradas;
- sin rutas arbitrarias.

Para preservar trazabilidad, el primer incremento no deberia aceptar parches de
texto sobre Markdown. Es mas seguro regenerar el informe completo desde un
contrato de secciones revisadas.

## Encaje en runtime y app

### Durante una run en background

`AgentRuntimeEvent` ya permite mostrar decisiones de agentes en la pestaña
`Agentes`.

Cambios recomendados:

- anadir `report_verifier` a `AGENT_PROFILES`;
- emitir evento `agent_decision` para cada turno del debate;
- ampliar `payloadPlainText(...)` para extraer:
  - `verification_status`;
  - `revision_round`;
  - `accepted_issue_ids`;
  - `required_corrections`;
  - `human_review_recommended`.

Asi la UI podria traducir el JSON a lineas como:

```text
Verificador pide 2 correcciones factuales en la ronda 1.
Redactor acepta 2 objeciones y aplica cambios en Metricas y evaluacion.
Verificador aprueba el informe revisado.
```

### Tras persistir la run

Ya existe `GET /runs/{run_id}/audit-report`, y el frontend lo renderiza en el
detalle de run. El camino minimo es anadir un bloque de debate a
`execution_audit.md`.

Camino mas completo, recomendado despues:

```text
GET /runs/{run_id}/report-debate
```

Este endpoint devolveria `report_debate.md` de forma controlada, igual que
`/report` y `/audit-report`, sin permitir leer rutas arbitrarias. El frontend
podria mostrar un panel `Debate del informe` entre `Informe final` y
`Auditoria de ejecucion`.

## Donde implementar

Propuesta de propietarios:

- contratos:
  - `agent_decisions.py` para `ReportRevisionDecision`;
  - `reasoning.py` para `ReportDebateTurn` y `ReportDebateRecord`;
- agente redactor:
  - extender `report_writer.py` con una funcion de revision;
- agente verificador:
  - reutilizar `report_verifier.py` para re-verificacion;
- coordinador:
  - crear un servicio pequeno `report_debate.py` solo si se mantiene como
    orquestador del tramo de reporting;
- grafo:
  - extender `_report_writer_node(...)`, no crear runner paralelo;
- persistencia:
  - extender `run_persistence.py` para resumir debate en evidence pack/auditoria;
- consulta:
  - extender `run_registry.py` si se anade `get_run_report_debate(...)`;
- API:
  - extender `routes.py` solo si se decide exponer `/report-debate`;
- frontend:
  - ampliar `AGENT_PROFILES`, traduccion de eventos y panel de detalle.

La pieza nueva `report_debate.py` estaria justificada si su responsabilidad se
limita a:

- ejecutar rondas maximas;
- preservar borradores;
- escribir JSON/Markdown de debate;
- devolver artefactos.

No debe:

- decidir contenido por si misma;
- llamar ejecutores de datos;
- leer artefactos fuera del estado;
- sustituir `report_writer`, `report_verifier` o `reporting.py`.

## Riesgos detectados

- Bucle infinito de revision: evitar con `max_rounds`.
- Debate demasiado verbal: evitar con JSON y Markdown derivado.
- Verificador excesivamente rigido: mantener notas de tolerancia y severidad.
- Redactor ignorando criticas severas: exigir respuesta por `issue_id`.
- Reescritura silenciosa del informe: guardar borrador inicial y revision.
- Mezcla con evaluacion: el debate solo valida el informe, no aprueba metricas.
- UI mostrando rutas locales: reutilizar filtrado ya existente en preview.
- Reportes antiguos sin debate: renderizar "no disponible" sin fallar.

## Criterios de aceptacion para implementar

Backend:

- una run con informe aprobado por el verificador genera `report_debate.json`
  con estado `approved_without_revision`;
- una run con incidencia corregible genera una revision y deja
  `approved_after_revision` o `needs_human_review`;
- una incidencia critica no resuelta queda como `blocked` o
  `needs_human_review`;
- cada turno incluye resumen humano y referencias de evidencia;
- `execution_audit.md` resume el debate;
- los borradores quedan preservados;
- no se cambia la evaluacion ni las metricas.

Frontend:

- `report_verifier` aparece en la vista de agentes;
- los eventos del debate tienen lectura humana compacta;
- el detalle de run muestra el debate al menos dentro de la auditoria;
- si se anade endpoint, se muestra un panel `Debate del informe`.

Tests:

- esquemas Pydantic de debate y revision;
- revision del redactor con LLM falso;
- fallback sin LLM;
- debate aprobado sin revision;
- debate con una revision;
- debate agotando rondas;
- persistencia de artefactos;
- auditoria de ejecucion con resumen de debate;
- API/frontend si se expone endpoint nuevo.

## Siguiente paso recomendado

Implementar primero un debate de una sola ronda:

```text
report_writer inicial
report_verifier inicial
si necesita revision:
  report_writer revision
  report_verifier final
persistir debate
mostrar resumen en auditoria
```

Despues, si esta base queda estable, ampliar a dos rondas y panel dedicado en
frontend. Esta secuencia mantiene el caracter agentico sin sacrificar
trazabilidad ni control metodologico.
