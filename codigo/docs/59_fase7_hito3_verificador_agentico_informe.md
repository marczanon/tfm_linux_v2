# Fase 7 - Hito 3: verificador agentico del informe final

Fecha: 2026-06-01.

## Capacidad buscada

Anadir un agente `report_verifier` que revise si el informe final generado por
`report_writer` contiene afirmaciones falsas, exageradas o sin evidencia,
manteniendo tolerancia sobre estilo, orden y enfasis.

El objetivo no es forzar un informe literal, sino evitar alucinaciones
factuales o metodologicas:

- metricas inexistentes;
- artefactos no registrados;
- aprobacion no respaldada por el evaluador;
- validacion industrial exagerada;
- etiquetas oficiales donde solo hay proxy, sinteticas o politica temporal;
- omision de limitaciones criticas.

## Inventario previo anti-duplicacion

Se revisaron:

- `codigo/app/agents/report_writer.py`;
- `codigo/app/executors/reporting.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/pipeline_runner.py`;
- `codigo/app/services/llm_agents.py`;
- `codigo/tests/test_report_writer_agent.py`;
- `codigo/tests/test_reporting_executor.py`;
- `codigo/tests/test_graph_pipeline.py`;
- `codigo/tests/test_run_persistence.py`;
- `codigo/docs/55_recap_mejoras_fase7.md`;
- `codigo/docs/58_fase7_hito2_informe_auditoria_ejecucion.md`.

Decision:

```text
extend
```

Motivo: ya existian propietarios claros. El contrato de decisiones agenticas
debia ampliarse, el grafo ya poseia el tramo de reporting, el informe final ya
se materializaba mediante `reporting.py` y los snapshots ya sabian extraer
decisiones y artefactos. No se crea otro runner ni otro flujo de reporting.

## Diseno aplicado

El nuevo verificador sigue esta frontera:

```text
El agente interpreta si el informe se sale de la evidencia.
Las herramientas deterministas construyen el catalogo cerrado de evidencias.
La salida se valida con Pydantic y se persiste como artefacto.
```

Se ha anadido el contrato `ReportVerificationDecision`, con:

- `verification_status`: `approved`, `needs_revision` o `blocked`;
- resumen de la verificacion;
- afirmaciones sin soporte;
- afirmaciones enganosas o de politica;
- limitaciones ausentes;
- correcciones requeridas;
- notas de tolerancia aceptable;
- referencias de evidencia citadas.

Cada incidencia usa `ReportVerificationIssue` con:

- tipo de problema;
- severidad;
- texto de la afirmacion;
- motivo;
- referencias de evidencia;
- correccion sugerida.

## Agente verificador

Se ha creado `codigo/app/agents/report_verifier.py`.

Cuando hay LLM habilitado, el agente recibe:

- Markdown del informe final;
- catalogo cerrado de evidencias;
- reglas de tolerancia;
- esquema JSON esperado.

El prompt explicita que:

- no se exige coincidencia literal;
- se aceptan diferencias de estilo, orden y enfasis;
- no se aceptan afirmaciones factuales no respaldadas;
- cada incidencia debe citar evidencia permitida o `missing:evidence`;
- no puede inventar evidencias ni ejecutar codigo.

El fallback determinista no pretende sustituir al agente. Solo detecta riesgos
evidentes, como:

- declarar validacion industrial o uso productivo;
- presentar NASA IMS con etiquetas oficiales;
- ocultar que una run no fue aprobada;
- omitir limitaciones persistidas.

## Integracion en el grafo

El verificador se ejecuta despues de que `reporting.py` escriba
`final_report.md`.

No bloquea todavia la run ni reescribe el informe. Deja preparada la base para
el siguiente paso de debate controlado entre agentes:

```text
report_writer -> final_report.md -> report_verifier -> artefactos de verificacion
```

La decision se anade al estado como mensaje de agente:

```text
name = report_verifier
```

Tambien se emite un evento runtime `agent_decision` para que la observabilidad
muestre el resultado de la verificacion.

## Artefactos generados

Por cada informe generado correctamente se escriben:

```text
<directorio_del_informe>/evidence/report_verification.json
<directorio_del_informe>/evidence/report_verification.md
```

El JSON conserva la decision estructurada. El Markdown ofrece una vista humana
con estado, incidencias, correcciones requeridas y notas de tolerancia.

## Auditoria de ejecucion

`execution_audit.md` incorpora ahora un bloque:

```text
## Verificacion del informe
```

Este bloque resume:

- estado de verificacion;
- decision del verificador;
- conteo de incidencias;
- correcciones obligatorias;
- referencias de evidencia citadas.

Si una run antigua no tiene `report_verifier`, la auditoria lo declara
explicitamente en lugar de fallar.

## Fronteras mantenidas

- No se crea un nuevo runner.
- No se crea un endpoint nuevo.
- No se reescribe el informe automaticamente.
- No se permite ejecutar codigo generado por agentes.
- No se convierte el verificador en autoridad metodologica absoluta.
- La tolerancia estilistica queda separada de los errores factuales.
- El debate controlado queda diferido hasta tener estabilizada esta base.

## Verificacion

Pruebas ejecutadas:

```text
python -m unittest \
  codigo.tests.test_report_verifier_agent \
  codigo.tests.test_agent_decisions_schema \
  codigo.tests.test_graph_pipeline \
  codigo.tests.test_run_persistence
```

Resultado:

```text
Ran 32 tests
OK
```

La unica salida no funcional observada es el warning de deprecacion de
LangGraph ya conocido.

## Estado

El Hito 3 deja implementada la primera base del informe verificable:

- existe un agente `report_verifier`;
- su salida esta validada por contrato Pydantic;
- se distingue tolerancia estilistica de falsedad factual;
- la verificacion queda persistida como JSON y Markdown;
- la auditoria de ejecucion resume la verificacion;
- el grafo queda preparado para un futuro bucle de debate controlado entre
  `report_writer` y `report_verifier`.
