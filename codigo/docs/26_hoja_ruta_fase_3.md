# Hoja de ruta Fase 3

Fecha de inicio propuesta: 2026-05-25.

## Punto de partida

La Fase 2 deja el MVP local consolidado como una aplicacion reproducible,
auditable y consultable. El sistema ya dispone de:

- pipeline CWRU completo con LangGraph;
- agentes LLM con salidas JSON/Pydantic y fallback determinista;
- ejecutores deterministas para manifiesto, perfilado, limpieza,
  estructuracion, modelado, evaluacion y reporting;
- persistencia local por `run_id`;
- registro consultable y comparacion de runs;
- protocolo experimental local;
- API FastAPI de lectura para runs, artefactos, informes y comparaciones.

La Fase 3 debe usar esa base para validar mejor la tesis central del proyecto:
que una arquitectura multiagente puede tomar decisiones utiles sobre datos
industriales, siempre que el poder de los agentes este acotado por contratos,
validaciones y ejecutores reproducibles.

## Objetivo de la Fase 3

Ampliar el MVP desde un flujo correcto sobre CWRU hacia una plataforma local de
experimentacion multi-dataset y multi-modelo, donde los agentes tengan mas
capacidad de decision sin perder seguridad, reproducibilidad ni trazabilidad.

La Fase 3 debe producir:

- soporte inicial para datasets industriales mas complejos que CWRU;
- contratos y adaptadores que permitan describir datasets heterogeneos;
- mas modelos de deteccion de anomalias con ejecutores deterministas;
- agentes con mayor capacidad de proponer configuraciones, comparar
  alternativas y justificar decisiones;
- experimentos que comparen decisiones agenticas frente a politicas
  deterministas;
- una politica clara para `POST /runs` y Human Review antes de permitir
  ejecuciones costosas desde la API;
- documentacion tecnica y memoria academica actualizadas.

## Decision de enfoque

La Fase 3 no debe convertirse solo en una ampliacion de API ni solo en una
coleccion de modelos. El centro sigue siendo el sistema multiagente.

El avance debe equilibrar tres ejes:

1. **Validez industrial**: incorporar datasets mas dificiles, con condiciones
   temporales, formatos y degradaciones menos controladas.
2. **Capacidad de decision**: permitir que los agentes elijan entre mas
   estrategias, modelos y configuraciones, no solo que rellenen valores fijos.
3. **Control reproducible**: cada decision agentica debe terminar en un
   contrato validado y en un ejecutor determinista; si no existe ejecutor, la
   decision debe quedar como propuesta no ejecutable.

## Fuera de alcance de la Fase 3

No se abordara todavia:

- SLURM;
- ejecucion HPC;
- entrenamiento distribuido;
- frontend React o Flutter;
- Docker Compose completo como requisito operativo;
- PostgreSQL o Redis como dependencias obligatorias;
- observabilidad avanzada;
- agentes que escriban y ejecuten codigo arbitrario;
- busquedas de hiperparametros sin limites de coste;
- descarga automatica de datasets desde URLs no auditadas.
- RAG de memoria agentica supervisada alimentado por revisiones humanas.

Docker, SLURM y frontend quedan para fases posteriores. La Fase 3 debe seguir
siendo local, verificable y defendible academicamente.
La memoria agentica supervisada queda apuntada para Fase 4 en:

```text
codigo/docs/31_backlog_fase_4_memoria_agentica.md
```

## Principios de trabajo

- Mantener CWRU como benchmark de regresion: todo avance debe conservar el
  pipeline CWRU funcionando.
- Introducir datasets nuevos mediante contratos y adaptadores, no mediante
  cambios ad hoc en ejecutores existentes.
- No exponer un modelo a los agentes si no existe un ejecutor reproducible y
  testeado para ese modelo.
- Dar mas poder a los agentes ampliando el espacio de decisiones validas, no
  eliminando validaciones.
- Separar decision, ejecucion y evaluacion: agente decide, ejecutor transforma,
  evaluador mide y registro persiste.
- Persistir todas las configuraciones, decisiones, metricas, artefactos y
  limitaciones.
- Comparar decisiones agenticas contra baselines deterministas siempre que sea
  posible.
- Actualizar la memoria cuando cambie la metodologia, el alcance experimental o
  la arquitectura.

## Guardarrailes para agentes con mas poder

Los agentes podran:

- elegir entre adaptadores de dataset registrados;
- proponer configuraciones de limpieza, remuestreo y seleccion de canal;
- proponer tamanos de ventana, solapamientos y familias de features;
- seleccionar modelos disponibles en un registro de modelos soportados;
- proponer planes experimentales acotados;
- comparar runs persistidos y justificar la mejor alternativa;
- solicitar Human Review cuando una accion supere limites de coste, tiempo o
  riesgo metodologico;
- redactar interpretaciones tecnicas a partir de metricas y artefactos.

Los agentes no podran:

- ejecutar codigo generado dinamicamente;
- modificar ficheros de codigo durante una ejecucion del pipeline;
- invocar comandos de shell;
- descargar datos sin una fuente previamente aprobada;
- seleccionar modelos sin ejecutor determinista;
- cambiar rutas fuera de los directorios permitidos;
- lanzar experimentos multiples sin limites explicitos;
- aprobar una ejecucion que incumpla umbrales tecnicos obligatorios.

Cuando un agente detecte una capacidad necesaria pero no implementada, debera
devolver una propuesta estructurada de capacidad pendiente, por ejemplo:

```text
required_capability = "pca_reconstruction_executor"
status = "unsupported"
next_action = "implement_executor"
```

La implementacion de esa capacidad corresponde al desarrollo determinista, no a
la ejecucion autonoma del agente.

## Hito 1: Cierre operativo de Fase 2

Objetivo: declarar la Fase 2 como base estable antes de ampliar el sistema.

Tareas:

- mantener `codigo/docs/20_hoja_ruta_fase_2.md` como documento historico de
  cierre;
- usar esta hoja de ruta como guia activa de nuevas sesiones;
- comprobar que la suite completa sigue pasando antes de modificar ejecutores;
- conservar los runs persistidos y experimentos CWRU como evidencia base.

Criterio de aceptacion:

- `conda run -n tfm_v2 python -m unittest discover codigo/tests` pasa;
- la documentacion tecnica enlaza la Fase 3;
- la memoria identifica la Fase 3 como trabajo posterior o en curso.

## Hito 2: Soporte multi-dataset

Objetivo: permitir datasets mas complejos sin romper CWRU.

Dataset candidato principal:

- NASA IMS Bearing Dataset.

Otros candidatos posteriores:

- Paderborn Bearing Dataset;
- FEMTO-ST / PRONOSTIA;
- datos sinteticos controlados para pruebas unitarias;
- datasets tabulares o multicanal de vibracion industrial si encajan con los
  contratos.

Trabajo previsto:

- definir un contrato comun de descriptor de dataset;
- separar manifiestos especificos por dataset de un contrato comun de salida;
- crear un registro de adaptadores de entrada;
- implementar un manifiesto inicial para NASA IMS o un subconjunto pequeno;
- validar perfilado y limpieza con datos multicanal o series mas largas;
- documentar diferencias metodologicas frente a CWRU.

Diseno tecnico:

```text
codigo/docs/27_diseno_soporte_multidataset.md
codigo/docs/29_agentes_expertos_llm_locales.md
```

Criterio de aceptacion:

- CWRU sigue funcionando sin cambios de comportamiento;
- existe al menos un dataset adicional perfilado con artefactos persistidos;
- los agentes reciben resumenes comparables entre datasets;
- no se cargan senales completas en el estado global.

## Hito 3: Perfilado y diagnostico agentico enriquecido

Objetivo: que los agentes dispongan de informacion mas rica para tomar
decisiones utiles sobre datasets heterogeneos.

Trabajo previsto:

- ampliar el perfil estadistico con diagnosticos de calidad de senal;
- registrar duracion, frecuencia estimada, canales, huecos, valores no finitos,
  deriva, saturacion y distribucion por condicion;
- crear un resumen de dataset orientado a decision agentica;
- permitir que el limpiador justifique estrategias distintas por dataset;
- anadir tests con perfiles sinteticos de casos problematicos.

Criterio de aceptacion:

- el agente limpiador puede distinguir entre un caso limpio, un caso con
  remuestreo necesario y un caso con calidad insuficiente;
- las decisiones siguen validandose por `CleaningDecision`;
- los diagnosticos quedan persistidos como artefactos consultables.

## Hito 4: Estructuracion temporal mas flexible

Objetivo: permitir que el estructurador elija configuraciones relevantes para
datasets y modelos distintos.

Trabajo previsto:

- permitir variaciones controladas de `window_size` y `overlap`;
- introducir familias de features temporales y frecuenciales;
- registrar el coste aproximado de cada estructuracion;
- validar que las particiones evitan fuga de informacion por fichero, carga,
  run o condicion experimental;
- preparar experimentos de sensibilidad de ventanas.

Criterio de aceptacion:

- al menos dos configuraciones de ventana comparables se ejecutan y persisten;
- el estructurador solo puede elegir valores dentro de rangos permitidos;
- los artefactos generados son compatibles con los modelos soportados.

## Hito 5: Portafolio de modelos deterministas

Objetivo: ampliar el espacio de decision del agente modelador con modelos
realmente ejecutables.

Orden recomendado:

1. PCA con error de reconstruccion.
2. One-Class SVM.
3. Local Outlier Factor.
4. Autoencoder denso.
5. LSTM Autoencoder en fase posterior si el coste y los datos lo justifican.

Regla obligatoria:

```text
No anadir un modelo al contrato seleccionable por agentes si no existe ejecutor,
tests, persistencia de artefactos y evaluacion comparable.
```

Trabajo previsto:

- crear un registro de modelos soportados;
- implementar ejecutores deterministas por modelo o una interfaz comun;
- unificar salida de predicciones para que `evaluation.py` siga siendo estable;
- guardar hiperparametros, semilla, columnas de entrada y umbrales;
- comparar modelos sobre CWRU antes de usarlos en datasets mas complejos.

Criterio de aceptacion:

- al menos dos modelos adicionales se ejecutan con tests focalizados;
- el modelador puede elegir entre modelos soportados mediante contrato;
- la comparacion de runs muestra metricas homogenas;
- los informes tecnicos explican ventajas y limitaciones de cada modelo.

## Hito 6: Mas poder agentico con control

Objetivo: hacer que los agentes sean mas centrales en el sistema sin convertir
la ejecucion en una caja negra.

Capacidades nuevas propuestas:

- decisiones con alternativas ordenadas, no solo una configuracion final;
- estimacion de trade-offs esperados antes de ejecutar;
- explicacion de por que se descarta una alternativa;
- modo `dry_run` para validar configuraciones sin entrenar modelos costosos;
- agente evaluador comparativo que recomiende el mejor run entre varios;
- agente planificador experimental que proponga un plan acotado y validable.

Contratos candidatos:

```text
DatasetSelectionDecision
ExperimentPlanDecision
ModelSelectionDecision
RunComparisonDecision
UnsupportedCapabilityDecision
```

Criterio de aceptacion:

- cada nueva decision tiene esquema Pydantic estricto;
- existe fallback determinista para tests;
- las decisiones agenticas se comparan contra una politica determinista;
- las propuestas no ejecutables quedan registradas sin romper el pipeline.

## Hito 7: API de ejecucion controlada y Human Review

Objetivo: definir `POST /runs` sin abrir una puerta a ejecuciones costosas o
ambiguas.

Trabajo previsto:

- definir contrato de solicitud para `POST /runs`;
- soportar primero ejecuciones locales acotadas y sincronas o pseudo-sincronas;
- rechazar solicitudes sin dataset, modelo o limites claros;
- introducir Human Review para planes experimentales multiples o modelos
  costosos;
- persistir aprobacion, revisor, motivo, limites aceptados y fecha;
- exponer estado de ejecucion sin streaming avanzado.

Endpoints candidatos:

```text
POST /runs
POST /experiment-plans
GET /runs/{run_id}/status
GET /experiment-plans/{plan_id}
```

Criterio de aceptacion:

- `POST /runs` no permite rutas arbitrarias;
- las solicitudes se validan antes de ejecutar;
- las ejecuciones quedan persistidas igual que los runs lanzados por Python;
- existe flujo aprobado y flujo rechazado para Human Review.

## Hito 8: Campanas experimentales multi-dataset

Objetivo: producir evidencia academica mas fuerte que una ejecucion aislada.

Campanas candidatas:

- CWRU con sensibilidad a ventana y modelo;
- CWRU con decision agentica frente a politica determinista;
- NASA IMS con perfilado, limpieza y baseline inicial;
- comparacion de modelos clasicos en el mismo protocolo;
- analisis de falsas alarmas por condicion experimental.

Criterio de aceptacion:

- cada campana genera plan, runs persistidos, comparacion y tabla Markdown;
- la memoria recoge resultados, limitaciones y amenazas a la validez;
- los resultados distinguen validacion del pipeline de generalizacion
  industrial real.

## Hito 9: Actualizacion academica

Objetivo: reflejar la Fase 3 en la memoria del TFM.

Capitulos afectados:

```text
memoria/capitulos/03_arquitectura.tex
memoria/capitulos/04_metodologia.tex
memoria/capitulos/05_implementacion.tex
memoria/capitulos/06_experimentos.tex
memoria/capitulos/07_resultados.tex
memoria/capitulos/08_conclusiones.tex
```

Puntos a documentar:

- por que CWRU no basta como unica validacion;
- como se generaliza el pipeline a datasets heterogeneos;
- como se aumenta el poder de los agentes sin permitir ejecucion arbitraria;
- que modelos nuevos se incorporan y por que;
- que decisiones agenticas mejoran o no mejoran frente a baselines
  deterministas;
- limitaciones computacionales y metodologicas.

## Orden de ejecucion recomendado

1. Cerrar operativamente Fase 2 y actualizar referencias.
2. Disenar soporte multi-dataset.
3. Implementar primer adaptador/manifiesto para NASA IMS o subconjunto
   equivalente.
4. Enriquecer perfilado y diagnostico agentico.
5. Hacer mas flexible la estructuracion temporal.
6. Implementar PCA reconstruction error como segundo modelo base.
7. Implementar One-Class SVM o LOF como tercer modelo.
8. Ampliar el agente modelador para elegir entre modelos soportados.
9. Introducir decisiones agenticas con alternativas y modo `dry_run`.
10. Definir politicas de `POST /runs` y Human Review.
11. Ejecutar campanas experimentales multi-dataset.
12. Actualizar memoria y resultados.

## Primer paso concreto siguiente

Tras crear el diseno tecnico multi-dataset, la primera capa de contratos, el
wrapper comun `generate_dataset_manifest(...)` para CWRU y la inspeccion local
de NASA IMS, se ha implementado un manifiesto NASA IMS solo para carpetas
preextraidas y sinteticas:

```text
codigo/app/services/dataset_adapters.py
codigo/tests/test_dataset_adapters.py
codigo/tests/test_dataset_manifest_executor.py
```

La generacion directa desde el paquete `zip -> 7z -> rar` queda fuera del
siguiente paso. Primero se ha validado una estructura preextraida compatible
con los sets observados en `codigo/docs/28_inspeccion_nasa_ims.md`.

## Siguiente paso concreto

Se ha adaptado el perfilado para aceptar el manifiesto comun NASA IMS y producir
un resumen comparable con CWRU: numero de ficheros, canales, frecuencia,
duracion, valores no finitos y estadisticos ligeros. La lectura de snapshots
IMS sin extension se resuelve como tabla numerica, con canales normalizados
`channel_1`, `channel_2`, etc. La capa de adaptadores expone ademas
`read_signal_frame(...)` para interactuar directamente con esos snapshots como
`DataFrame`.

## Avance concreto tras el perfilado

Se ha adaptado la limpieza para consumir manifiestos comunes y seleccionar
canales de forma controlada en NASA IMS. `CleaningConfig` incorpora
`selected_channel`; el ejecutor valida el canal contra `channel_names` cuando
existen, usa `primary_channel` como valor por defecto en el manifiesto comun y
mantiene compatibilidad con el campo historico `sensor_channel` de CWRU.

Esta validacion se ha hecho primero con carpetas sinteticas preextraidas:
manifiesto NASA IMS, perfilado comun, limpieza de `channel_2` y rechazo de un
canal no declarado. No se ha avanzado todavia a estructuracion ni modelado
NASA IMS.

## Avance concreto de diagnostico agentico

Se ha incorporado al perfilado un `decision_summary` orientado al agente. Este
bloque convierte estadisticos de senal en un expediente experto ligero:

- `quality_status`;
- `required_actions`;
- `recommended_channels`;
- `candidate_channels`;
- `supported_cleaning_options`;
- `blocking_warnings`;
- `non_blocking_warnings`.

El agente limpiador recibe este bloque dentro del resumen de perfil y puede
elegir entre opciones soportadas sin depender de conocimiento interno del LLM
sobre datasets de nicho. El criterio de diseno queda documentado en:

```text
codigo/docs/29_agentes_expertos_llm_locales.md
```

## Siguiente paso concreto tras el diagnostico agentico

Se ha extendido el mismo patron al estructurador. A partir de senales limpias,
el sistema genera un resumen de decision con:

- configuraciones candidatas de `window_size` y `overlap`;
- estimacion de ventanas y coste;
- conjuntos de features temporales soportados;
- advertencias de fuga por fichero, run o secuencia temporal;
- capacidades no soportadas, como features frecuenciales o split temporal
  run-to-failure para NASA IMS.

El agente estructurador ya no queda limitado a una constante fija de 2048
muestras y 50% de solape: puede elegir entre ventanas y solapes soportados,
siempre dentro del contrato validado y de los limites del ejecutor.

Tambien queda como idea posterior un agente investigador controlado, orientado a
resolver dudas de otros agentes mediante `ResearchRequest` y `EvidenceReport`,
primero sobre RAG local y despues, si se habilita, con fuentes externas
autorizadas. El diseno queda recogido en:

```text
codigo/docs/29_agentes_expertos_llm_locales.md
```

## Ejecucion agentica controlada con Qwen sobre NASA IMS

Se ha ejecutado una prueba smoke completa del grafo con agentes Qwen/Ollama
sobre una carpeta NASA IMS sintetica preextraida, usando:

```text
python -m codigo.scripts.run_nasa_ims_qwen_smoke \
  --model qwen3.5:4b \
  --run-id nasa-ims-qwen-smoke-fase3-qwen
```

El objetivo no era entrenar un modelo NASA IMS, sino comprobar si los agentes
locales usan los expedientes expertos y respetan los bloqueos metodologicos. El
snapshot persistido queda en:

```text
codigo/reports/runs/nasa-ims-qwen-smoke-fase3-qwen/
```

Resultado observado:

- el limpiador Qwen selecciono `channel_1` a partir del perfil y del manifiesto;
- el estructurador Qwen eligio `window_size = 1024`, `overlap = 0.5` y features
  temporales soportadas;
- el modelador Qwen propuso `isolation_forest`, que es el unico modelo
  ejecutable actual, pero todavia con una expectativa de ruta heredada de CWRU;
- el supervisor genero varias decisiones validas, aunque algunas transiciones
  invalidas activaron el fallback determinista;
- el flujo genero manifiesto, perfil, senales limpias, features, tensores y
  splits;
- el modelado se bloqueo de forma deliberada con estado final `failed`, porque
  NASA IMS no tiene etiquetas por ventana ni una politica temporal validada.

Esta prueba confirma que el patron "expediente experto + decision estructurada"
es viable con un LLM local, pero tambien muestra que las dudas metodologicas no
deben resolverse con otra regla rigida que reste protagonismo al agente. La
linea de trabajo pasa a reforzar la deliberacion agentica: alternativas,
autocrítica, solicitud de evidencia y comparacion de resultados.

## Siguiente paso concreto tras la prueba Qwen/NASA IMS

En lugar de anadir una compuerta determinista previa al modelador, se ha dado
mas protagonismo al estructurador: `StructuringDecision` puede incluir ahora
`comparison_candidates`, es decir, alternativas comparables propuestas por el
propio agente con su justificacion y efecto esperado. El protocolo experimental
no inventa configuraciones si el agente no las propone; solo materializa y mide
las alternativas validas.

Se ha ejecutado una comparacion agentica de ventanas en CWRU:

```text
python -m codigo.scripts.run_cwru_agentic_window_comparison \
  --model qwen3.5:4b \
  --plan-id cwru-agentic-window-qwen-fase3
```

Qwen propuso tres configuraciones: 2048/50% como seleccion principal, 1024/50%
para mayor resolucion temporal y 4096/50% para mayor contexto por ventana. Los
resultados quedan persistidos en:

```text
codigo/experiments/cwru_local/cwru-agentic-window-qwen-fase3/
codigo/reports/runs/cwru-agentic-window-qwen-fase3_*/
```

Resultado resumido:

| Ventana | Solape | Precision | Recall | F1 | FPR |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2048 | 0.50 | 0.9991 | 1.0000 | 0.9996 | 0.0513 |
| 1024 | 0.50 | 0.9996 | 0.9999 | 0.9998 | 0.0212 |
| 4096 | 0.50 | 0.9991 | 1.0000 | 0.9996 | 0.0517 |

La alternativa de 1024 muestras fue la mejor por precision, F1 y tasa de falsos
positivos, mientras que la configuracion principal de 2048 mantuvo recall
perfecto. Este resultado refuerza una direccion mas alineada con el TFM: el
agente propone hipotesis tecnicas y la aplicacion las transforma en evidencia
experimental trazable.

## Avance concreto de comparacion agentica de modelos

Se ha implementado un segundo modelo ejecutable: PCA con error de
reconstruccion. `ModelingDecision` puede incluir ahora
`comparison_candidates`, de forma analoga al estructurador. El modelador puede
proponer alternativas soportadas y el protocolo las ejecuta sin inventarlas.

Ejecucion real:

```text
python -m codigo.scripts.run_cwru_agentic_model_comparison \
  --model qwen3.5:4b \
  --plan-id cwru-agentic-model-qwen-fase3
```

Qwen propuso Isolation Forest, PCA reconstruction error y una variante
conservadora de Isolation Forest. La comparacion se ejecuto con la ventana
1024/50%, seleccionada en el experimento anterior.

| Modelo | Umbral | Precision | Recall | F1 | FPR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Isolation Forest | 0.99 | 0.9996 | 0.9999 | 0.9998 | 0.0212 |
| PCA reconstruction | 0.99 | 1.0000 | 0.9623 | 0.9808 | 0.0000 |
| Isolation Forest conservador | 1.00 | 0.9999 | 0.9994 | 0.9996 | 0.0085 |

Este resultado responde a una limitacion importante: ya no toda la evidencia
experimental presenta recall 1.0000. PCA muestra un trade-off mas realista:
elimina falsos positivos en este protocolo, pero pierde recall.

## Primer diagnostico NASA sin etiquetas supervisadas

Para empezar a analizar NASA IMS sin inventar etiquetas por ventana, se ha
anadido un diagnostico no supervisado de degradacion:

```text
python -m codigo.scripts.run_nasa_ims_degradation_diagnostics
```

El diagnostico usa features temporales ya generadas y calcula tendencia
temporal, ratio final/inicial y severidad relativa. No calcula recall, F1 ni
precision porque NASA IMS sigue sin una politica de etiquetado defendible.

Resultado sobre la prueba smoke sintetica NASA IMS:

```text
trend_status = increasing_degradation_signal
late_early_ratio = 2.2296
trend_slope_per_file = 0.1893
n_files = 3
n_windows = 21
```

El siguiente paso sera preparar un benchmark adicional no trivial, sintetico o
NASA preextraido con politica temporal explicita, para que los agentes comparen
modelos y configuraciones sobre datos que no produzcan metricas artificialmente
perfectas.

## Benchmark NASA sintetico etiquetado para metricas no triviales

Se ha creado un benchmark sintetico temporal inspirado en NASA IMS Set 2 para
obtener metricas supervisadas sin atribuir etiquetas por ventana al dataset real.
La generacion queda encapsulada en:

```text
codigo/app/services/synthetic_nasa_ims.py
codigo/scripts/run_nasa_ims_synthetic_temporal_benchmark.py
codigo/tests/test_synthetic_nasa_ims.py
```

El benchmark mantiene la forma de entrada de NASA IMS, pero las etiquetas
`normal` / `fault` son generadas por construccion. Por tanto, solo valida el
comportamiento multi-dataset del pipeline y de los agentes; no debe presentarse
como resultado oficial sobre NASA IMS.

Ejecucion canonica:

```text
python -m codigo.scripts.run_nasa_ims_synthetic_temporal_benchmark \
  --model qwen3.5:4b \
  --run-id nasa-ims-synth-agentic-qwen-fase3
```

Resultado:

| Metrica | Valor |
| --- | ---: |
| Precision | 0.9130 |
| Recall | 0.6000 |
| F1-score | 0.7241 |
| ROC-AUC | 0.8041 |
| PR-AUC | 0.8842 |
| FPR | 0.1429 |

Qwen tomo decisiones validas en limpiador, estructurador, modelador y evaluador:
selecciono `channel_1`, eligio ventanas 2048/50%, propuso Isolation Forest y
rechazo la ejecucion al detectar que las metricas no cumplian los umbrales
locales. Este caso es valioso porque introduce un resultado no perfecto y
obliga al sistema a iterar sobre decisiones agenticas, en lugar de cerrar todos
los experimentos con recall 1.0000.

## Iteracion agentica acotada con aprendizaje de errores

Se ha anadido un bucle de reintento para el modelador que no ejecuta busquedas
automaticas ni reglas deterministas de optimizacion. El sistema genera un
analisis de fallo con matriz de confusion, falsos negativos, falsos positivos,
umbral efectivo y convencion de puntuacion; el agente modelador decide si
reintentar o parar mediante `ModelingRetryDecision`.

Ejecucion:

```text
python -m codigo.scripts.run_nasa_ims_agentic_retry \
  --model qwen3.5:4b \
  --source-run-id nasa-ims-synth-agentic-qwen-fase3 \
  --run-id-prefix nasa-ims-synth-agentic-qwen-fase3-retry \
  --max-attempts 2
```

Resultado:

| Run | Umbral cuant. | Precision | Recall | F1 | FPR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base | 0.99 | 0.9130 | 0.6000 | 0.7241 | 0.1429 |
| Reintento 1 | 0.95 | 0.8846 | 0.6571 | 0.7541 | 0.2143 |
| Reintento 2 | 0.50 | 0.7143 | 1.0000 | 0.8333 | 1.0000 |

El agente aprendio de los falsos negativos que bajar el umbral aumentaba la
sensibilidad. El primer reintento mejoro recall y F1 de forma moderada. En el
segundo reintento, Qwen priorizo demasiado la sensibilidad: alcanzo recall
1.0000, pero clasifico tambien todos los normales de test como anomalias
(`FPR=1.0000`). El evaluador rechazo la ejecucion y el bucle se cerro con
`next_action = stop` porque se habia agotado el presupuesto de dos reintentos.

Artefactos principales:

```text
codigo/reports/runs/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-01/
codigo/reports/runs/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/iteration/retry_comparison.json
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/iteration/reasoning_postmortem.md
codigo/reports/nasa_ims_bearing/nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02/iteration/human_reasoning_review_request.md
```

Este resultado es metodologicamente util: los agentes no alcanzan metricas
magicamente perfectas, pero si razonan sobre el fallo, prueban una hipotesis
tecnica trazable y se detienen cuando el intercambio recall/FPR deja de ser
aceptable.

### Auditoria del razonamiento y human-on-the-loop

Se ha anadido una capa de post-mortem para saber si un cambio agentico fue
razonado o simplemente afortunado. El post-mortem compara la hipotesis
declarada por el agente con el resultado real y clasifica el caso:

```text
partially_supported
overcorrected
contradicted
validated
```

En la run NASA sintetica:

- retry 1 queda como `partially_supported`: mejora recall y F1, pero aun con
  FPR excesiva;
- retry 2 queda como `overcorrected`: la direccion era correcta, pero la
  magnitud fue insegura porque FPR subio a 1.0000.

Con el trigger `--request-human-review`, el sistema crea una solicitud de
revision humana y una plantilla JSON para que una persona etiquete la calidad
del razonamiento. Esta revision no altera la evaluacion tecnica; sirve como
memoria supervisada para futuros prompts, RAG local o filtrado de patrones de
decision erroneos.

### Pulido de trazabilidad multi-dataset

Se han eliminado nombres heredados de CWRU en artefactos comunes generados por
estructuracion, modelado, evaluacion y reporting. Los ejecutores siguen
aceptando rutas CWRU por defecto para mantener el MVP historico, pero los
artefactos nuevos usan nombres neutrales:

```text
windows_features
windows_raw
windows_splits
isolation_forest_model
model_predictions
modeling_summary
evaluation_metrics
evaluation_summary
final_report
```

Los snapshots NASA persistidos se han normalizado para que no aparezcan
artefactos `cwru_*` dentro de runs `nasa_ims_bearing`. Se conserva compatibilidad
de lectura para runs antiguos que aun tengan `cwru_modeling_summary`.

Tambien se ha documentado una politica ligera de conservacion de runs en:

```text
codigo/docs/30_gestion_runs_fase_3.md
```

El inventario muestra que `codigo/reports/runs/` sigue siendo pequeno; lo que
puede crecer son tensores, modelos y artefactos regenerables de experimentos.
Por ello se conservaran snapshots canonicos y tablas de resultados, podando
artefactos grandes solo cuando ya exista evidencia persistida.

## Cierre operativo de Fase 3

Fecha de cierre operativo: 2026-05-27.

La Fase 3 queda cerrada como una fase de validacion multiagente local. No se
considera cerrada porque se hayan agotado todas las ampliaciones posibles, sino
porque ya existe una cadena defendible de evidencias:

- CWRU se mantiene como benchmark de regresion;
- NASA IMS entra mediante contratos comunes, adaptadores y diagnosticos, sin
  forzar metricas supervisadas no defendibles;
- los agentes Qwen locales toman decisiones sobre expedientes expertos y no
  sobre conocimiento interno no verificable;
- el estructurador propone alternativas de ventana que se ejecutan y comparan;
- el modelador compara Isolation Forest y PCA reconstruction error;
- el benchmark NASA sintetico introduce metricas no perfectas;
- el bucle de reintento agentico aprende de falsos negativos, mejora recall y
  se detiene ante sobrecorreccion;
- el razonamiento de los agentes queda auditado y puede solicitar revision
  humana;
- los artefactos comunes usan nombres neutrales multi-dataset.

Quedan deliberadamente fuera del cierre de Fase 3:

- `POST /runs` con ejecucion desde API;
- Human Review interactivo dentro de una interfaz;
- RAG de memoria agentica supervisada;
- SLURM, Docker Compose completo y frontend;
- evaluacion supervisada sobre NASA IMS real sin politica temporal validada;
- nuevos modelos como One-Class SVM o LOF, salvo que se abran como primer hito
  de una fase posterior.

## Regla operativa para fases posteriores

La redaccion academica debe avanzar en paralelo a las ejecuciones de codigo. En
Fase 3 se ha comprobado que, si la memoria se actualiza solo al final, los
resultados, limitaciones y decisiones metodologicas quedan dispersos en runs y
documentos tecnicos. Para Fase 4 y siguientes, cada ejecucion canonica debe
cerrarse con:

- snapshot de run y artefactos ligeros;
- tabla o resumen tecnico en `codigo/docs/`;
- reflejo academico en el capitulo correspondiente de `memoria/`;
- verificacion reproducible documentada;
- decision explicita sobre si el resultado es evidencia principal, caso
  frontera, fallo util o artefacto descartable.
