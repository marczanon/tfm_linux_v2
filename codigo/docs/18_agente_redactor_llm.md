# Agente redactor LLM

## Objetivo

Introducir el agente LLM que decide la estructura del informe tecnico final.
El agente devuelve una `ReportDecision`; no escribe el informe directamente, no
modifica artefactos previos y no ejecuta codigo. La generacion real del
Markdown queda delegada en:

```text
codigo/app/executors/reporting.py
```

## Que decide

El agente redactor propone:

- ruta de salida del informe;
- formato de salida;
- secciones que debe contener el documento;
- si una seccion debe incluir metricas o artefactos;
- rutas fuente que justifican cada seccion.

Para el MVP CWRU, las validaciones restringen la decision a:

```text
output_path = codigo/reports/cwru_bearing/final_report.md
output_format = markdown
```

Tambien se exigen las secciones:

```text
Resumen ejecutivo
Contexto y datos
Configuraciones del pipeline
Metricas y evaluacion
Artefactos generados
Limitaciones y siguientes pasos
```

El LLM puede ordenar y justificar la estructura del informe, pero no puede
inventar rutas fuente. `source_paths` solo puede contener rutas ya presentes en
el estado: manifiesto, perfil, datos limpios, tensores, splits, metricas o
artefactos registrados.

## Implementacion

Archivos principales:

```text
codigo/app/agents/report_writer.py
codigo/app/executors/reporting.py
codigo/app/graph/pipeline.py
codigo/tests/test_report_writer_agent.py
codigo/tests/test_reporting_executor.py
```

El agente expone:

```text
decide_report_action(state, llm_client=None, use_llm=None) -> ReportDecision
```

Rutas disponibles:

- `decide_report_action_with_llm(...)`: usa un cliente LLM JSON.
- `decide_report_action_deterministic(...)`: fallback reproducible.

El ejecutor expone:

```text
generate_technical_report(state, decision) -> ReportExecutorResult
```

## Encaje en el grafo

El supervisor solo enruta al redactor cuando la evaluacion existe y su
`next_action` es `continue`. Si la evaluacion rechaza la ejecucion, el grafo
termina en `failed`.

La fase final queda asi:

```text
supervisor
-> evaluator
-> supervisor
-> evaluation_agent
-> supervisor
-> report_writer
-> supervisor
-> END
```

El nodo `report_writer` combina dos pasos:

1. el agente genera una `ReportDecision` validada;
2. el ejecutor determinista escribe el informe Markdown y registra el artefacto
   `report`.

## Validaciones de seguridad

La respuesta del LLM queda limitada por varias capas:

- debe devolver JSON parseable;
- debe validar contra `ReportDecision`;
- `output_format` debe ser `markdown`;
- `output_path` debe ser la ruta final del MVP;
- deben aparecer todas las secciones obligatorias;
- las rutas fuente deben existir en el estado;
- cualquier fallo activa el fallback determinista.

Esta separacion conserva la idea central del TFM: los agentes toman decisiones
propias sobre configuracion, juicio o presentacion, pero las operaciones reales
se ejecutan mediante codigo determinista, testeable y trazable.

## Configuracion LLM local

Por defecto se usa el fallback determinista. Para activar el redactor LLM:

```bash
export TFM_REPORT_WRITER_MODE=llm
export TFM_LLM_PROVIDER=ollama
export TFM_LLM_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
```

El cliente JSON mantiene `TFM_LLM_THINK=false` por defecto para llamadas JSON
estrictas. Si se quiere probar razonamiento visible se puede usar
`TFM_LLM_THINK=true`, y si se prefiere omitir el parametro en Ollama se puede
usar `TFM_LLM_THINK=auto`.

## Tests

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

La verificacion cubre:

- uso de una decision LLM valida;
- fallback ante rutas o secciones invalidas;
- escritura determinista del informe Markdown;
- rechazo de formatos no soportados por el ejecutor;
- ruta completa del grafo hasta `completed` con informe final generado.

## Siguiente paso

Con el redactor integrado, el MVP local ya cubre el ciclo principal de datos:
manifiesto, perfilado, limpieza, estructuracion, modelado, evaluacion,
juicio agentico e informe tecnico. El siguiente paso logico sera consolidar la
persistencia ligera de ejecuciones y preparar una API minima solo cuando el MVP
local quede estable.
