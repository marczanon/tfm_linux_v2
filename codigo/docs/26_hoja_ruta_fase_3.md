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

Docker, SLURM y frontend quedan para fases posteriores. La Fase 3 debe seguir
siendo local, verificable y defendible academicamente.

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

Adaptar el perfilado para aceptar el manifiesto comun NASA IMS y producir un
resumen comparable con CWRU: numero de ficheros, canales, frecuencia,
duracion, valores no finitos, estadisticos ligeros y advertencias de calidad.
Esta validacion debe hacerse primero con carpetas sinteticas o subconjuntos
preextraidos, sin limpieza, estructuracion ni modelado todavia.
