# Fase 7 - Hito 5.1: catalogo minimo de herramientas agenticas

Fecha: 2026-06-01.

## Objetivo

Iniciar una capa comun de herramientas seguras para agentes sin convertir esas
herramientas en reglas hardcodeadas. La primera version declara un catalogo y
una unica herramienta read-only, `evidence_lookup`, que permite consultar
evidencia de una run de forma estructurada.

La herramienta no decide por el agente. Solo devuelve una observacion
validable: secciones de evidencia, referencias citables y un resumen humano. El
agente conserva la responsabilidad de elegir y justificar su decision dentro de
su contrato Pydantic.

## Inventario previo anti-duplicacion

Piezas revisadas:

- `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`;
- `codigo/docs/55_recap_mejoras_fase7.md`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/services/agent_memory.py`;
- `codigo/app/services/decision_memory.py`;
- `codigo/app/agents/report_verifier.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/tests/test_reasoning_memory_schema.py`;
- `codigo/tests/test_report_verifier_agent.py`.

Decision:

```text
extend
```

Motivo: los contratos de trazabilidad y razonamiento ya viven en
`reasoning.py`, y la evidencia factual ya existia parcialmente en
`report_verifier.py`. Se extrae esa responsabilidad comun a un servicio de
herramientas en lugar de crear una logica paralela por agente.

## Contratos anadidos

En `codigo/app/schemas/reasoning.py` se incorporan:

- `AgentToolSpec`: declaracion de herramienta, agentes autorizados, efecto,
  esquema de entrada y esquema de salida;
- `AgentToolRequest`: solicitud estructurada de un agente;
- `AgentToolObservation`: observacion devuelta por la herramienta, con estado,
  resumen, referencias de evidencia y payload.

La primera politica de efectos distingue:

```text
read_only
writes_artifact
requires_human_review
```

En esta version solo se implementa `read_only`.

## Servicio canonico

Se crea `codigo/app/services/agent_tools.py` como propietario del catalogo
minimo:

- `agent_tool_catalog(...)`;
- `get_agent_tool_spec(...)`;
- `run_agent_tool_request(...)`;
- `build_state_evidence_catalog(...)`.

`build_state_evidence_catalog(...)` queda como catalogo cerrado de evidencias
citables de una run. El verificador del informe lo reutiliza para mantener una
frontera unica de evidencia factual.

## Herramienta evidence_lookup

`evidence_lookup` puede devolver secciones seleccionables:

```text
project_context
paths
configs
metrics
evaluation
artifacts
errors
policy
```

Ejemplo conceptual de solicitud:

```json
{
  "tool_name": "evidence_lookup",
  "agent_name": "modeler",
  "purpose": "Consultar metricas y artefactos antes de decidir.",
  "arguments": {
    "include": ["metrics", "evaluation", "artifacts"],
    "artifact_limit": 5
  }
}
```

La observacion puede incluir referencias como:

```text
metric:recall
evaluation:approved
artifact:evaluation_metrics
policy:local_dataset
```

Estas referencias son evidencia que el agente puede citar despues, no una
decision automatica.

## Fronteras metodologicas

Esta primera version no:

- llama automaticamente a herramientas desde los agentes;
- introduce tool-calling libre;
- ejecuta codigo generado por LLM;
- modifica datos, modelos, metricas ni informes;
- anade efectos secundarios ni artefactos nuevos por uso de herramienta.

El siguiente paso natural sera debatir como conectar `evidence_lookup` a un
agente concreto, probablemente `report_writer` o `modeler`, de forma que la
solicitud y la observacion queden visibles en la conversacion agentica.

## Validacion

Validaciones ejecutadas:

```text
python -m py_compile codigo/app/schemas/reasoning.py codigo/app/schemas/__init__.py codigo/app/services/agent_tools.py codigo/app/services/__init__.py codigo/app/agents/report_verifier.py
python -m unittest codigo.tests.test_agent_tools codigo.tests.test_report_verifier_agent
```

Resultado: contratos y herramienta pasan las pruebas enfocadas, y
`report_verifier` conserva compatibilidad con el catalogo cerrado de evidencias.
