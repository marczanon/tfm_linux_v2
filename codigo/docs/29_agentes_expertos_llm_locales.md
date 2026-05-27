# Agentes expertos viables con LLM locales

## Problema

El objetivo central del TFM son los agentes de IA, no una sucesion de
ejecutores hardcodeados. Sin embargo, los modelos locales pequenos no deben
depender de conocimiento interno sobre datasets industriales de nicho. No es
razonable esperar que un LLM local sepa, por memoria parametica, si una ventana
concreta, un canal o una politica temporal es mejor para NASA IMS, CWRU u otro
dataset especializado.

Si se deja al LLM decidir sin contexto, el sistema seria fragil. Si se fija todo
en reglas cerradas, los agentes perderian protagonismo. La solucion adoptada es
una autonomia agentica asistida por evidencia.

## Decision de diseno

Los agentes no seran expertos porque el LLM recuerde conocimiento industrial
de nicho, sino porque la aplicacion les entrega un expediente experto antes de
cada decision. Ese expediente se calcula con codigo determinista y contiene:

- resumen del dataset y del manifiesto;
- diagnosticos de calidad de senal;
- canales candidatos con puntuaciones y advertencias;
- acciones requeridas, como remuestreo o seleccion de canal;
- opciones ejecutables por los contratos actuales;
- limitaciones y bloqueos metodologicos;
- capacidades no soportadas cuando haga falta proponer trabajo futuro.

El agente conserva libertad en la parte realmente agentica:

- elegir entre opciones soportadas;
- ordenar alternativas;
- justificar la eleccion con evidencia;
- rechazar una ejecucion si la calidad es insuficiente;
- pedir revision humana o nueva capacidad;
- comparar resultados persistidos frente a una politica determinista.

El ejecutor conserva el control reproducible:

- valida el contrato Pydantic;
- aplica solo operaciones implementadas;
- rechaza rutas, canales o modelos no soportados;
- persiste configuracion, metricas y artefactos.

## Patron: expediente experto + decision estructurada

El patron operativo es:

```text
datos / artefactos
-> ejecutor determinista de diagnostico
-> expediente experto ligero
-> agente LLM con personalidad y rol tecnico
-> decision JSON/Pydantic
-> validador de limites
-> ejecutor determinista
-> artefactos y metricas persistidas
```

La personalidad del agente afecta a su criterio, tono tecnico y prioridades,
pero no elimina los contratos. Por ejemplo, un agente limpiador puede actuar
como un ingeniero de fiabilidad conservador: prioriza no contaminar datos,
explica riesgos y bloquea perfiles insuficientes. Aun asi, su salida principal
es `CleaningDecision`.

## Primera aplicacion: perfilado enriquecido

El perfilador genera ahora un `decision_summary` dentro de `profile.json`.
Este bloque no contiene senales completas, sino informacion ligera para decidir:

```text
quality_status
required_actions
recommended_channels
candidate_channels
supported_cleaning_options
blocking_warnings
non_blocking_warnings
agent_guidance
```

Ejemplos de estados:

- `clean`: hay un canal claro y no se requiere remuestreo;
- `needs_resampling`: la frecuencia de origen difiere de la frecuencia objetivo;
- `needs_channel_selection`: hay varios canales viables y el agente debe elegir;
- `insufficient_quality`: no hay canal viable para continuar.

Esto permite que el agente limpiador no dependa de saber de memoria que canal es
mejor en NASA IMS. Puede ver canales candidatos, puntuaciones, advertencias y
opciones soportadas, y decidir con trazabilidad.

## Por que no es hardcoding

No se fija una decision final en el codigo. Se fija un espacio de decision
seguro:

- los umbrales diagnostican calidad;
- los registros enumeran capacidades ejecutables;
- los contratos limitan configuraciones validas;
- el agente elige y justifica dentro de ese espacio;
- las decisiones agenticas se podran comparar contra politicas deterministas.

Este enfoque hace viable usar LLM locales: el conocimiento de dominio se
externaliza en artefactos verificables y el LLM se usa para deliberar, priorizar
y explicar, no para inventar hechos tecnicos.

## Siguientes extensiones

El mismo patron debe aplicarse despues a:

- estructuracion temporal: candidatos de ventana, solapamiento, coste estimado
  y riesgo de fuga temporal;
- modelado: registro de modelos soportados, hiperparametros validos, coste y
  compatibilidad con etiquetas;
- experimentacion: planes acotados, alternativas ordenadas y modo `dry_run`;
- evaluacion: comparacion de runs persistidos y justificacion de la mejor
  alternativa frente a baseline determinista.

## Alternativas propuestas por agentes

Para reforzar el protagonismo agentico, `StructuringDecision` ya no se limita a
una unica configuracion final. El agente estructurador puede devolver
`comparison_candidates`: alternativas comparables, cada una con su
`StructuringConfig`, justificacion y efecto esperado.

El protocolo experimental no genera una segunda opcion por reglas internas. Si
el agente no propone al menos dos configuraciones unicas, el plan comparativo no
se construye. Con esto se evita disfrazar una heuristica determinista como si
fuera criterio del agente.

La primera validacion real se ha ejecutado con:

```text
python -m codigo.scripts.run_cwru_agentic_window_comparison \
  --model qwen3.5:4b \
  --plan-id cwru-agentic-window-qwen-fase3
```

Qwen propuso:

- 2048 muestras y 50% de solape como configuracion principal;
- 1024 muestras y 50% de solape para aumentar resolucion temporal;
- 4096 muestras y 50% de solape para aumentar contexto por ventana.

La alternativa de 1024 muestras obtuvo el mejor F1 y la menor tasa de falsos
positivos en CWRU. El resultado queda en:

```text
codigo/experiments/cwru_local/cwru-agentic-window-qwen-fase3/results_table.md
```

El mismo enfoque se ha extendido al modelador. `ModelingDecision` acepta ahora
alternativas comparables y se ha implementado PCA con error de reconstruccion
como segundo ejecutor soportado:

```text
python -m codigo.scripts.run_cwru_agentic_model_comparison \
  --model qwen3.5:4b \
  --plan-id cwru-agentic-model-qwen-fase3
```

La comparacion mostro un trade-off mas realista: PCA obtuvo precision 1.0000 y
FPR 0.0000, pero recall 0.9623. Esto evita que toda la evidencia dependa de
recalls perfectos en CWRU.

## Validacion inicial con Qwen y NASA IMS

Se ha realizado una prueba smoke con el grafo completo, agentes Qwen/Ollama y
una carpeta NASA IMS sintetica preextraida:

```text
python -m codigo.scripts.run_nasa_ims_qwen_smoke \
  --model qwen3.5:4b \
  --run-id nasa-ims-qwen-smoke-fase3-qwen
```

El snapshot queda persistido en:

```text
codigo/reports/runs/nasa-ims-qwen-smoke-fase3-qwen/
```

La prueba confirma dos aspectos:

- el LLM local puede tomar decisiones utiles cuando recibe expedientes
  calculados por la aplicacion: selecciono `channel_1`, una ventana de 1024
  muestras, solape del 50% y features temporales soportadas;
- la autonomia debe seguir acotada: el modelador propuso `isolation_forest`,
  pero NASA IMS no debe entrenarse todavia sin etiquetas por ventana ni split
  temporal defendible.

El resultado final fue `failed` por guardarrail metodologico de la prueba, no
por un error de procesamiento. La direccion de diseno no sera anadir una nueva
funcion determinista que quite decision al agente, sino ampliar su capacidad de
expresar incertidumbre, pedir evidencia y proponer alternativas comparables
antes de ejecutar.

Como primer paso NASA sin etiquetas supervisadas se ha anadido un diagnostico
no supervisado de degradacion. No calcula precision, recall ni F1; mide
tendencia temporal y severidad relativa:

```text
python -m codigo.scripts.run_nasa_ims_degradation_diagnostics
```

En la prueba smoke sintetica detecta `increasing_degradation_signal` con ratio
final/inicial 2.2296.

## Extension futura: agente investigador

Como capacidad posterior, se considera viable introducir un agente investigador
para resolver incertidumbres que los agentes de ejecucion no puedan justificar
con los expedientes locales. No debe ser una navegacion libre de cualquier
agente, sino un flujo estructurado:

```text
agente de dominio
-> ResearchRequest validado
-> supervisor
-> agente investigador
-> EvidenceReport con fuentes, citas, fecha y limitaciones
-> agente de dominio decide con ese contexto
```

Reglas propuestas:

- empezar con RAG local sobre `codigo/docs/`, `memoria/` y `recursos/`;
- permitir internet solo con fuentes autorizadas, por ejemplo documentacion
  oficial de datasets, articulos academicos y repositorios tecnicos primarios;
- exigir citas, fecha de consulta, tipo de fuente y nivel de confianza;
- impedir que el investigador ejecute codigo, descargue datasets o cambie
  configuraciones directamente;
- registrar la evidencia como artefacto consultable;
- usar Human Review si una recomendacion afecta a metodologia, coste alto o
  validez experimental.

Este agente reforzaria la personalidad y autonomia del sistema sin romper el
principio central: investigar produce evidencia, pero ejecutar sigue siendo
responsabilidad de contratos y ejecutores deterministas.
