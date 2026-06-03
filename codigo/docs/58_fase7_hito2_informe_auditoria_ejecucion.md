# Fase 7 - Hito 2: informe de auditoria de ejecucion

Fecha: 2026-05-31.

## Capacidad buscada

Crear un informe separado del informe agentico final para que un humano pueda
entender, de forma clara y estructurada, que ha pasado durante toda una
ejecucion.

Este informe no sustituye al documento del agente `report_writer`. Su funcion
es explicar el proceso: solicitud, plan, agentes, decisiones, artefactos,
metricas, errores, bloqueos y revision humana.

## Inventario previo anti-duplicacion

Se revisaron:

- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/run_registry.py`;
- `codigo/app/api/routes.py`;
- `codigo/frontend/src/api.ts`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/styles.css`;
- `codigo/frontend/src/types.ts`;
- `codigo/tests/test_run_persistence.py`;
- `codigo/tests/test_run_registry.py`;
- `codigo/tests/test_api_runs.py`.

Decision:

```text
extend
```

Motivo: ya existian propietarios claros. La persistencia de runs genera los
artefactos de snapshot, el registro de runs los consulta, la API ya sirve
documentos Markdown de una run y el frontend ya carga el detalle de run. No se
crea un lector de ficheros arbitrario ni un segundo flujo de ejecucion.

## Cambios implementados

### Backend

Cada snapshot nuevo genera:

```text
codigo/reports/runs/<run_id>/execution_audit.md
```

El documento se construye de forma determinista desde `RunEvidencePack` y queda
separado del informe final agentico. Incluye:

- lectura rapida de estado de la run;
- solicitud y plan aplicado;
- cronologia de decisiones agenticas;
- resultado tecnico y metricas;
- artefactos y checksums abreviados;
- incidencias, errores y bloqueos;
- lectura para evaluador humano.

`RunSnapshot` incorpora el campo opcional `audit_report_path` para mantener
compatibilidad con snapshots antiguos.

### Registro y API

`run_registry.py` añade:

- `get_run_evidence_pack(...)`;
- `get_run_audit_report(...)`.

La API añade:

```text
GET /runs/{run_id}/audit-report
```

El endpoint devuelve Markdown y no permite leer rutas arbitrarias desde el
navegador. Si un snapshot antiguo no tiene `execution_audit.md` pero conserva
`evidence_pack.json`, el registro puede renderizar la auditoria desde ese
evidence pack.

### Frontend

El detalle de run carga ahora tres documentos diferenciados:

- informe final agentico;
- auditoria de ejecucion;
- evidencia tecnica como lista de artefactos.

La auditoria aparece en un bloque propio `Auditoria de ejecucion`, separado de
`Informe final`, para no mezclar conclusiones del agente redactor con trazas
operativas del proceso.

## Fronteras mantenidas

- No se cambia la logica del pipeline.
- No se inventa un runner nuevo.
- No se ejecuta codigo generado por agentes.
- No se lee ningun fichero local directamente desde el frontend.
- No se mezcla el informe agentico con la auditoria determinista.
- No se muestran rutas locales crudas en la UI.

## Verificacion

Pruebas ejecutadas:

```text
python -m py_compile \
  codigo/app/services/run_persistence.py \
  codigo/app/services/run_registry.py \
  codigo/app/api/routes.py

python -m unittest \
  codigo.tests.test_run_persistence \
  codigo.tests.test_run_registry \
  codigo.tests.test_api_runs

npm run build
```

Resultado:

```text
Ran 32 tests
OK
frontend build OK
```

La unica salida no funcional observada en tests backend es el warning de
deprecacion de LangGraph ya conocido.

## Estado

El sistema ya diferencia:

- informe final: documento de conclusiones generado por `report_writer`;
- auditoria de ejecucion: documento determinista para evaluar que ocurrio;
- evidence pack: base estructurada y auditable de datos, decisiones y artefactos.

El siguiente paso logico seria conectar de forma mas explicita el informe
agentico con la auditoria: validaciones de que cada afirmacion importante del
`report_writer` queda respaldada por evidencia registrada.
