# Fase 7 - Hito 1: evidence pack e informe agentico para analistas

Fecha: 2026-05-31.

## Capacidad buscada

Hacer que cada run deje una base minima auditable y que el agente
`report_writer` no solo decida la estructura del informe, sino que redacte
contenido narrativo entendible para analistas humanos, manteniendo contratos
Pydantic y ejecutores deterministas.

## Inventario previo anti-duplicacion

Antes de implementar se revisaron las piezas existentes relacionadas con
reporting, snapshots, decisiones y planificacion:

- `codigo/app/agents/report_writer.py`;
- `codigo/app/executors/reporting.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/pipeline_runner.py`;
- `codigo/app/schemas/pipeline_run.py`;
- `codigo/tests/test_report_writer_agent.py`;
- `codigo/tests/test_reporting_executor.py`;
- `codigo/tests/test_run_persistence.py`;
- `codigo/tests/test_pipeline_runner.py`.

Decision:

```text
extend
```

Motivo: ya existian propietarios canonicos. La persistencia de runs es la
frontera correcta para el evidence pack, el runner comun es la frontera correcta
para conservar request/plan de ejecucion, el agente redactor es la frontera
correcta para el criterio narrativo y el ejecutor `reporting.py` es la frontera
correcta para materializar Markdown.

## Cambios implementados

### Evidence pack por snapshot

`run_persistence.py` genera ahora, junto a cada snapshot:

```text
codigo/reports/runs/<run_id>/evidence_pack.json
codigo/reports/runs/<run_id>/evidence_pack.md
```

El JSON es el artefacto auditable estructurado. Incluye:

- version del esquema;
- identificacion de run, dataset, estado final y aprobacion;
- contexto del proyecto;
- configuraciones de limpieza, estructuracion y modelado;
- metricas y evaluacion;
- revision humana si existe;
- decisiones agenticas normalizadas;
- artefactos con estado de existencia, tipo, productor, tamano y checksum
  SHA-256 cuando el fichero esta disponible;
- errores capturados;
- solicitud y plan de ejecucion cuando la run viene del runner comun.

El Markdown es una vista humana del mismo paquete, pensada para inspeccion
rapida. No sustituye al informe final de analista.

### Request y plan como evidencia de ejecucion

`pipeline_runner.py` escribe dos artefactos `config` antes de ejecutar:

```text
codigo/reports/<dataset>/<run_id>/evidence/pipeline_request.json
codigo/reports/<dataset>/<run_id>/evidence/pipeline_plan.json
```

Estos ficheros permiten auditar que se pidio, que politica aplico el sistema,
que fases eran efectivas y si existian bloqueos antes de transformar datos.

### Report writer con contenido humano

`ReportSection` se ha ampliado de forma compatible con:

- `body`;
- `key_findings`;
- `recommendations`;
- `evidence_refs`.

El agente `report_writer` sigue devolviendo un `ReportDecision` validado por
Pydantic, pero ahora puede incluir redaccion narrativa en castellano tecnico.
El JSON no es el entregable para el usuario final: es el contrato interno que
permite validar seguridad, rutas y secciones. El documento que lee el analista
se genera en Markdown por el ejecutor determinista.

### Renderizado determinista del informe

`reporting.py` conserva la responsabilidad de escribir el fichero final, pero
ahora renderiza el contenido redactado por el agente cuando existe:

- cuerpo narrativo por seccion;
- hallazgos principales;
- recomendaciones;
- detalle de metricas y artefactos cuando la seccion lo solicita;
- fuentes tecnicas asociadas.

Si una seccion no trae cuerpo narrativo, el ejecutor conserva el fallback
determinista anterior.

## Fronteras mantenidas

- No se ha creado otro runner.
- No se han inventado endpoints nuevos.
- No se ha permitido ejecutar codigo generado por agentes.
- No se han cambiado los contratos externos de la API.
- No se ha cambiado la logica metodologica del pipeline.
- No se ha convertido ningun bloqueo metodologico en error tecnico.
- El informe final sigue siendo Markdown, no JSON expuesto como documento.

## Verificacion

Pruebas ejecutadas:

```text
python -m unittest \
  codigo.tests.test_report_writer_agent \
  codigo.tests.test_reporting_executor \
  codigo.tests.test_run_persistence \
  codigo.tests.test_pipeline_runner
```

Resultado:

```text
Ran 21 tests
OK
```

La unica salida no funcional observada es un warning de deprecacion procedente
de `langgraph.cache.base`; no afecta al hito.

## Estado del hito

El Hito 1 de Fase 7 queda implementado a nivel backend/documental:

- cada snapshot nuevo puede dejar evidence pack estructurado y legible;
- las ejecuciones del runner comun conservan request y plan como evidencia;
- el agente redactor gana capacidad narrativa sin perder validacion estricta;
- el informe final se mantiene como documento humano para analistas.

Actualizacion posterior: el informe final ya se ha integrado en frontend como
documento principal de cierre de run en
`codigo/docs/57_fase7_hito1_frontend_informe_final.md`. Queda pendiente una
vista especifica de auditoria para el evidence pack, separada del informe final
para no mezclar documento de analista y trazabilidad tecnica.
