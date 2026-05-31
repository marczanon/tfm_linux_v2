# Recap y propuestas para Fase 7

Fecha: 2026-05-31.

## Objetivo del documento

Preparar el regreso al nucleo del TFM tras el cierre operativo de Docker:
agentes de IA, deteccion autonoma de anomalias, trazabilidad de decisiones y
reporte para analistas humanos.

Este documento no es todavia la hoja de ruta de Fase 7. Su funcion es:

- resumir que hace hoy la aplicacion;
- separar lo imprescindible para que sea auditable en un TFM;
- listar mejoras importantes que aumentan valor sin ser existenciales;
- proponer ideas agenticas avanzadas compatibles con la metodologia del
  proyecto;
- conservar la regla de no duplicar runners, contratos, memoria ni ejecutores.

## Metodologia que debe mantenerse

Capacidad buscada:

```text
Evolucionar la aplicacion multiagente hacia una herramienta auditable de
deteccion autonoma de anomalias con informe tecnico para analistas humanos.
```

Inventario previo revisado:

- `codigo/docs/54_cierre_operativo_fase6.md`;
- `codigo/docs/48_hoja_ruta_fase_6_dockerizacion.md`;
- `codigo/docs/36_hoja_ruta_fase_5_aplicacion.md`;
- `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`;
- `codigo/app/api/routes.py`;
- `codigo/app/services/pipeline_runner.py`;
- `codigo/app/graph/pipeline.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/vector_memory.py`;
- `codigo/app/services/agent_memory.py`;
- `codigo/app/services/decision_memory.py`;
- `codigo/app/services/reasoning_audit.py`;
- `codigo/app/services/memory_usage_audit.py`;
- `codigo/app/services/transversal_memory_audit.py`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/api.ts`;
- `codigo/frontend/src/types.ts`;
- `codigo/tests/`.

Decision inicial:

```text
extend
```

Motivo: la aplicacion ya tiene propietarios claros para ejecucion, API,
memoria, auditoria, UI y Docker. La Fase 7 debe ampliar esas piezas, no crear
otra aplicacion ni otro pipeline paralelo.

Reglas de trabajo:

- antes de crear cualquier modulo, endpoint, agente, script o test, buscar
  propietario canonico;
- si existe contrato Pydantic, extenderlo con compatibilidad;
- si existe servicio canonico, reutilizarlo o adaptarlo;
- los agentes no escriben ni ejecutan codigo arbitrario;
- los agentes devuelven decisiones estructuradas;
- los ejecutores siguen siendo deterministas, testeables y trazables;
- los bloqueos metodologicos no se presentan como errores tecnicos;
- cada avance tecnico debe reflejarse en docs y memoria;
- primero se valida en local y despues se reconstruye/valida Docker si el
  cambio toca backend, frontend, dependencias, variables o artefactos.

## Recap de la aplicacion actual

### Proposito

La aplicacion es un entorno local para ejecutar un pipeline multiagente de
deteccion de anomalias industriales sobre senales de vibracion. El objetivo no
es sustituir al analista humano, sino producir una ejecucion trazable con:

- decisiones estructuradas de agentes;
- transformaciones deterministas;
- metricas reproducibles;
- artefactos persistidos;
- informe tecnico;
- observabilidad de agentes;
- memoria consultable;
- puerta de revision humana.

### Arquitectura actual

```text
Frontend React/Vite o Nginx
  -> FastAPI
      -> dataset_adapters.py / signal_adapters.py
      -> pipeline_runner.py
      -> graph/pipeline.py
      -> agents/*
      -> executors/*
      -> run_persistence.py / run_registry.py
      -> vector_memory.py / agent_memory.py
      -> Docker compose minimo
```

La entrada canonica de ejecucion es `POST /runs`. El frontend consume la API y
no debe leer ficheros internos directamente.

### Datasets y politicas

La aplicacion reconoce:

- `cwru_bearing`: benchmark principal, con pipeline completo permitido.
- `nasa_ims_bearing`: dataset run-to-failure con politica temporal explicita;
  permite diagnostico y solo permite modelado/evaluacion supervisada cuando se
  declara politica temporal versionada o etiquetas sinteticas/controladas.
- `generic_tabular_signal`: adaptador de descriptor, todavia sin politica de
  ejecucion completa.

Los bloqueos de NASA IMS son metodologicos: no son fallos tecnicos.

### Pipeline

El pipeline esta dividido en fases:

- `manifest`: creacion de manifiesto comun;
- `profiling`: perfil estadistico y calidad de senal;
- `cleaning`: limpieza y normalizacion;
- `structuring`: ventanas temporales y features;
- `modeling`: entrenamiento/prediccion de anomalias;
- `evaluation`: metricas;
- `reporting`: informe tecnico;
- `memory`: memoria agentica, disponible en piezas internas pero bloqueada en
  ejecucion API general.

Los modos principales son:

- `diagnostic`: corta antes de modelado/evaluacion cuando procede;
- `full`: ejecuta el pipeline completo si la politica del dataset lo permite.

### Agentes

Agentes actuales:

- `supervisor`: decide siguiente nodo/fase;
- `cleaner`: propone configuracion de limpieza;
- `structurer`: decide ventanas, features y alternativas;
- `modeler`: selecciona modelo e hiperparametros;
- `evaluator`: interpreta metricas y aprueba o no;
- `report_writer`: decide estructura del informe.

Los agentes pueden funcionar con reglas deterministas o con Ollama/Qwen cuando
`use_llm=true`. La salida se valida contra esquemas Pydantic. La aplicacion
expone decisiones, rationale y confianza, pero no cadena de pensamiento
privada.

### Ejecutores

Los ejecutores son deterministicos y son los unicos que transforman datos:

- manifiesto;
- perfilado;
- limpieza;
- estructuracion temporal;
- modelado;
- evaluacion;
- reporting.

El modelado soporta actualmente:

- Isolation Forest;
- PCA reconstruction error.

La evaluacion calcula metricas como precision, recall, F1, ROC-AUC, PR-AUC,
FPR y matriz de confusion cuando existen etiquetas binarias validas.

### API

Endpoints principales:

- `GET /health`;
- `GET /llm/status`;
- `GET /datasets/adapters`;
- `POST /datasets/describe`;
- `POST /runs`;
- `GET /runs`;
- `GET /runs/{run_id}`;
- `GET /runs/{run_id}/artifacts`;
- `GET /runs/{run_id}/report`;
- `GET /runs/{run_id}/visualization`;
- `GET /runs/compare`;
- `GET /run-jobs/{job_id}`;
- `GET /run-jobs/{job_id}/events`;
- `GET /memory/collections`;
- `GET /memory/records`;
- `GET /memory/records/{memory_record_id}`.

`POST /runs` soporta `dry_run`, `background`, `use_llm`, `human_review` y
`human_approval`. `use_memory=true` sigue bloqueado en ejecucion API para no
mezclar memoria productiva sin politica cerrada.

### Frontend

La UI actual permite:

- ver salud de API y estado LLM;
- configurar una run;
- elegir dataset/adaptador;
- activar LLM;
- declarar politica NASA IMS o etiquetas sinteticas;
- planificar/preflight;
- ver bloqueos y razones de revision humana;
- ejecutar en background;
- seguir job y eventos;
- listar runs;
- filtrar runs;
- abrir detalle de snapshot;
- ver metricas, informe y artefactos;
- comparar runs;
- observar agentes en runtime;
- consultar memoria persistida;
- visualizar metricas y PCA 2D cuando hay artefactos.

### Persistencia y evidencia

Las runs se guardan bajo `codigo/reports/runs/` con:

- estado final;
- decisiones extraidas;
- artefactos;
- metricas;
- evaluacion;
- resumen;
- metadata/snapshot.

Tambien existe memoria agentica bajo `codigo/reports/reasoning_memory/` y
artefactos de ejecucion bajo `codigo/data`, `codigo/models` y `codigo/reports`.

### Memoria agentica y auditorias

Ya existen piezas importantes:

- contratos de post-mortem de razonamiento;
- episodios de decision;
- candidatos de memoria;
- memoria vectorial local JSON;
- embeddings con proveedor local hash u Ollama;
- indexacion de memoria;
- auditoria de uso de memoria;
- auditoria transversal;
- consultas por agente/dataset/rol;
- validacion de que el agente solo cite memorias recuperadas.

La memoria esta mas madura en scripts y servicios que en ejecucion API/UI.

### Human Review

Hay una puerta minima `off/passive/required`.

Puede:

- detectar razones de revision;
- bloquear ejecucion si el modo es `required`;
- registrar aprobacion, revisor y razon;
- persistir `human_approval` en snapshot.

Todavia no es un flujo completo de analista con cola de revisiones,
comentarios historicos o versionado de aprobaciones.

### Docker

La Fase 6 deja:

- imagen backend;
- imagen frontend;
- Nginx con proxy `/api`;
- compose local backend/frontend;
- volumenes persistentes;
- Ollama externo;
- validacion manual del stack.

Docker queda como forma de reproducir la app cuando cambie la funcionalidad.

## Mejoras imprescindibles para auditabilidad TFM

Estas mejoras son las que, si faltan, debilitan la defensa academica de la app.

### 1. Evidence pack por run

Cada run debe tener un paquete de evidencia unico, exportable y legible.

Debe incluir:

- solicitud exacta de ejecucion;
- plan/preflight completo;
- politica de dataset aplicada;
- versiones de contratos y prompts;
- agente utilizado por fase;
- modelo LLM, host y configuracion;
- modelo de embeddings, si se usa memoria;
- semillas y parametros deterministas;
- modelo de anomalias e hiperparametros;
- rutas logicas de artefactos;
- checksums de artefactos relevantes;
- version de codigo o identificador de commit si esta disponible;
- modo local o Docker;
- estado final y errores.

Propietarios probables:

- extender `run_persistence.py`;
- extender `RunSnapshot`;
- reutilizar `PipelineRunRequest`, `DatasetPipelinePlan` y `ArtifactRef`.

### 2. Dataset card por dataset/run

La aplicacion debe dejar claro que datos se han usado y con que limites.

Debe incluir:

- dataset;
- fuente/origen;
- licencia o restriccion conocida;
- formato;
- canales;
- frecuencia;
- numero de archivos/senales;
- politica de split;
- procedencia de etiquetas;
- limitaciones metodologicas;
- si las etiquetas son oficiales, proxy o sinteticas.

Esto es especialmente critico para NASA IMS: cualquier metrica con etiquetas
proxy debe declararse como proxy, no como verdad oficial.

Propietarios probables:

- extender `dataset_adapters.py`;
- extender `DatasetDescriptor`;
- generar artefacto desde `pipeline_runner.py` o ejecutor de manifiesto.

### 3. Model card por run

Cada modelo entrenado debe tener una ficha auditable.

Debe incluir:

- objetivo del modelo;
- familia de modelo;
- hiperparametros;
- features usadas;
- split de entrenamiento/evaluacion;
- criterio de umbral;
- metricas por split;
- matriz de confusion;
- limitaciones;
- uso recomendado y no recomendado;
- si el resultado esta aprobado o no.

Propietarios probables:

- extender `modeling.py`;
- extender `evaluation.py`;
- incluir enlace en `reporting.py` y `RunDetailView`.

### 4. Registro auditable de decisiones LLM

Para cada decision LLM se necesita un registro mas completo que el payload
actual.

Debe incluir:

- agente;
- decision_id;
- prompt/schema version;
- JSON solicitado;
- JSON recibido;
- errores de parseo o validacion;
- numero de reintentos;
- latencia;
- proveedor/modelo;
- temperatura si aplica;
- razon declarada;
- confianza;
- alternativas consideradas;
- artefactos/evidencia citada.

No debe incluir cadena de pensamiento privada. La evidencia auditable debe ser
la decision estructurada y su justificacion declarada.

Propietarios probables:

- extender `llm.py`;
- extender `llm_agents.py`;
- extender `AgentRuntimeEvent`;
- persistir junto al snapshot.

### 5. Trazabilidad agente -> evidencia -> artefacto

Cada decision importante debe apuntar a la evidencia que la justifica:

- perfil de datos usado por cleaner;
- resumen de calidad usado por structurer;
- features/modeling summary usado por modeler;
- metrics/evaluation usado por evaluator;
- secciones/fuentes usadas por report_writer.

Ahora hay mensajes y artefactos, pero falta una matriz explicita que permita
decir: esta decision se tomo por estas evidencias y produjo estos artefactos.

Propietarios probables:

- extender `AgentDecisionBase` o crear un subtipo compatible;
- usar `ArtifactRef`;
- ampliar snapshot con `decision_evidence.json`.

### 6. Reporte para analista humano como artefacto principal

El informe debe pasar de "resumen tecnico" a "informe de analista".

Debe incluir:

- resumen ejecutivo;
- dataset y politica;
- calidad de datos;
- configuracion elegida;
- anomalias detectadas;
- metricas e interpretacion;
- limitaciones;
- acciones sugeridas;
- razones de no aprobacion si aplica;
- memoria usada y cautelas;
- anexo tecnico con parametros y artefactos.

Propietarios probables:

- extender `report_writer`;
- extender `reporting.py`;
- exponer secciones en UI con lectura mas profesional.

### 7. Politica clara de memoria en ejecucion API/UI

Ahora la UI consulta memoria, pero `use_memory=true` esta bloqueado en la API.
Para defender aprendizaje agentico hay dos opciones aceptables:

1. mantener memoria como read-only y declarar claramente que no influye en runs
   lanzadas desde UI;
2. habilitar `use_memory=true` de forma controlada, con retrieval, citas,
   auditoria y Human Review.

Para una Fase 7 centrada en agentes, la segunda opcion es mas potente, pero debe
entrar con guardarrailes:

- top_k limitado;
- colecciones por agente;
- solo recuerdos reutilizables;
- citas obligatorias;
- auditoria posterior;
- bloqueo si un agente cita memoria no recuperada;
- UI mostrando memoria usada, no solo memoria disponible.

Propietarios probables:

- `pipeline_runner.py`;
- `PipelineMemoryConfig`;
- `agent_memory.py`;
- `memory_usage_audit.py`;
- `transversal_memory_audit.py`;
- `POST /runs`;
- frontend `Agentes` y `RunDetailView`.

### 8. Reproducibilidad exacta de una run

Debe poder reejecutarse una run desde su configuracion persistida.

Debe existir:

- boton o comando "recrear solicitud";
- export de `PipelineRunRequest`;
- diferenciacion entre reusar mismo `run_id` y clonar con nuevo `run_id`;
- comparacion antes/despues.

Propietarios probables:

- `run_persistence.py`;
- `run_registry.py`;
- frontend de detalle de run.

### 9. Taxonomia de errores y bloqueos

La aplicacion debe distinguir:

- error tecnico;
- bloqueo metodologico;
- falta de datos;
- falta de etiquetas;
- falta de Ollama/modelo;
- fallo de validacion LLM;
- fallo recuperable de ejecutor;
- no aprobacion por metricas.

Esto ya existe parcialmente, pero debe hacerse visible y uniforme en API,
snapshot e interfaz.

### 10. Pruebas de humo y regresion despues de estabilizar Fase 7

Aunque se difirieron en Fase 6, para cerrar Fase 7 seran imprescindibles:

- health API;
- estado LLM;
- preflight CWRU;
- run CWRU pequena;
- bloqueo NASA IMS sin politica;
- run NASA IMS con politica temporal declarada;
- frontend/proxy;
- Docker compose;
- lectura de snapshot, informe, artefactos y memoria.

## Mejoras importantes adicionales

No son existenciales para auditar la app, pero aumentan mucho su valor.

### 1. Mejor gestion de jobs

La cola actual vive en memoria del proceso FastAPI.

Mejoras:

- cancelar job;
- reintentar job fallido;
- ver logs completos;
- persistir estado minimo del job;
- limitar concurrencia;
- mostrar duracion por fase;
- detectar jobs huerfanos si se reinicia la API.

### 2. Navegacion de artefactos

La UI podria mostrar artefactos por tipo:

- datos perfilados;
- resumen de limpieza;
- features;
- predicciones;
- metricas;
- modelo;
- informe;
- memoria.

El usuario no deberia ver rutas internas, sino nombres logicos y descargas o
previews controladas.

### 3. Modelos adicionales con comparacion

Incorporar:

- One-Class SVM;
- Local Outlier Factor;
- autoencoder denso;
- LSTM/temporal autoencoder en fase posterior;
- ensemble simple de scores.

Regla: cada modelo nuevo requiere contrato, test, persistencia de parametros,
metricas comparables y documentacion de limitaciones.

### 4. Analisis de umbral

El umbral de anomalia es critico.

Mejoras:

- curva score/threshold;
- sensibilidad de FPR/recall;
- tabla de umbrales candidatos;
- recomendacion del agente modeler/evaluator;
- justificacion del umbral elegido.

### 5. Analisis temporal y espectral

Para vibracion industrial conviene mejorar features:

- RMS;
- kurtosis;
- crest factor;
- energia por bandas;
- FFT;
- envelopes si procede;
- tendencias temporales por run-to-failure.

Estas features deben implementarse en ejecutores deterministicos.

### 6. Comparacion de runs mas rica

La comparacion actual es basica.

Mejoras:

- comparar configuraciones;
- diferencias de datos;
- diferencias de agentes;
- diferencias de memoria;
- deltas de metricas;
- artefactos nuevos/eliminados;
- mejor run por criterio.

### 7. Analista humano como usuario real

Mejoras UX:

- bandeja de runs pendientes de revision;
- resumen de riesgo;
- comentarios del analista;
- marcar run como aceptada/rechazada;
- checklist de validacion;
- export de informe.

### 8. Datasets personalizados

Para ampliar fronteras:

- contrato de dataset tabular generico;
- mapeo de columnas;
- declaracion de etiqueta o modo no supervisado;
- validacion de frecuencia/canal;
- preview de muestras;
- bloqueo si falta contrato minimo.

### 9. Seguridad local y limpieza operativa

Mejoras:

- limites de tamano por subida;
- saneamiento de nombres;
- cuotas simples de artefactos;
- limpieza controlada de runs;
- export/import de runs;
- aviso cuando Docker monta directorios vacios o incorrectos.

## Ideas agenticas avanzadas para valorar

Estas propuestas son mas ambiciosas. Deben implementarse solo si aportan
evidencia al TFM y respetan la separacion agente/ejecutor.

### 1. ReAct restringido a herramientas seguras

Patron: razonamiento y accion intercalados, pero con herramientas cerradas.

Herramientas permitidas:

- consultar perfil de datos;
- consultar metricas;
- consultar artefactos registrados;
- consultar memoria;
- proponer configuracion;
- solicitar revision humana.

Herramientas prohibidas:

- ejecutar codigo arbitrario;
- escribir transformaciones nuevas;
- leer rutas fuera de raices permitidas;
- modificar artefactos ya cerrados.

Encaje con el proyecto: el agente puede iterar sobre observaciones, pero cada
accion real sigue siendo un contrato y un ejecutor determinista.

### 2. Reflexion supervisada

El proyecto ya tiene post-mortems, memoria y auditorias. Se puede convertir en
un ciclo formal:

1. agente decide;
2. ejecutor produce resultado;
3. evaluador mide;
4. auditor genera critica;
5. humano revisa si procede;
6. memoria guarda leccion;
7. siguiente run recupera la leccion.

La clave es que la memoria no aprueba nada por si sola. Solo aporta contexto
auditado.

### 3. Agente verificador independiente

Anadir un `verifier` o `auditor_agent` que no ejecuta el pipeline.

Responsabilidades:

- revisar si una decision cita evidencia real;
- detectar claims no soportados;
- comprobar coherencia entre metricas e informe;
- comprobar que NASA IMS no se presenta con etiquetas oficiales si usa proxy;
- marcar "needs_human_review".

No sustituye al evaluador. Es una capa de auditoria.

### 4. Debate controlado entre agentes

Para modelado:

- `modeler_proposer`: propone configuracion;
- `modeler_skeptic`: busca riesgos;
- `evaluator`: decide si se permite ejecutar;
- `human_review`: interviene si hay conflicto.

El debate debe producir JSON estructurado, alternativas y riesgos. No debe ser
texto libre largo.

### 5. Planificador de experimentos acotado

Un agente podria proponer un plan de experimentos:

- ventanas candidatas;
- modelos candidatos;
- umbrales candidatos;
- presupuesto maximo;
- criterio de exito;
- criterio de parada.

El ejecutor de experimentos ya tiene piezas (`experiment_protocol.py`), por lo
que la Fase 7 deberia extenderlas antes de crear otro planificador.

### 6. Active learning para analistas

El sistema seleccionaria ventanas o segmentos para que el analista etiquete:

- alta incertidumbre;
- score cercano al umbral;
- discrepancia entre modelos;
- segmentos representativos de clusters.

Esto encaja muy bien con mantenimiento predictivo real, pero exige UI de
revision y contrato de etiquetas humanas.

### 7. Memoria con gobierno

La memoria deberia tener ciclo de vida:

- candidato;
- pendiente de revision;
- reusable;
- warning;
- obsoleta;
- excluida.

Tambien deberia detectar conflictos:

- dos recuerdos recomiendan acciones incompatibles;
- recuerdo de CWRU usado indebidamente en NASA IMS;
- recuerdo antiguo contradice politica actual.

### 8. Observabilidad tipo trazas

La observabilidad actual esta en eventos runtime propios. Una evolucion seria
mapear run/job/agente/ejecutor a spans:

- run span;
- fase span;
- agente span;
- ejecutor span;
- LLM call span;
- artifact write span.

Esto facilitaria auditoria temporal y diagnostico sin cambiar la logica.

### 9. RAG de conocimiento tecnico

Ademas de memoria de decisiones, se puede crear memoria documental:

- notas metodologicas;
- manuales de dataset;
- explicaciones de features;
- criterios de analista;
- limitaciones de modelos.

El agente no "sabe" de rodamientos por magia: recupera fuentes controladas.

### 10. Informes verificables

El redactor podria generar un informe y el verificador revisar:

- todas las metricas citadas existen;
- todos los artefactos citados existen;
- no hay afirmaciones no soportadas;
- las limitaciones estan presentes;
- el informe no confunde proxy labels con etiquetas oficiales.

El informe final podria llevar un bloque "verificacion automatica".

### 11. Politica de autonomia por riesgo

No todas las runs deberian tener la misma autonomia.

Ejemplo:

- CWRU benchmark: autonomia alta.
- NASA IMS con proxy declarado: autonomia media y advertencias.
- Dataset desconocido: solo diagnostico y Human Review.
- Memoria conflictiva: bloquear o pedir revision.
- LLM no disponible: fallback determinista.

Esta politica deberia ser visible en preflight.

### 12. Agente de frontera metodologica

Un agente especializado podria decidir si una peticion es defendible:

- hay etiquetas reales?
- hay politica de split?
- se puede calcular metrica supervisada?
- el dataset permite full run o solo diagnostico?
- que evidencia falta?

Seria especialmente util para NASA IMS y datasets genericos.

## Agrupacion preliminar para futura hoja de ruta

La hoja de ruta de Fase 7 podria organizarse asi, pero debe concretarse en el
siguiente documento:

1. Auditabilidad y evidence pack.
2. Reporte de analista y model/dataset cards.
3. Memoria en ejecucion API/UI con guardarrailes.
4. Verificador/auditor agentico.
5. Mejoras de modelado y umbrales.
6. Mejoras UX para analista humano.
7. Experimentos acotados y comparacion avanzada.
8. Smoke tests y traslado a Docker.

## Riesgos de alcance

La Fase 7 puede crecer demasiado. Para evitarlo:

- cerrar primero auditabilidad;
- no anadir modelos sin comparacion y tests;
- no abrir datasets genericos sin contrato minimo;
- no anadir autonomia sin Human Review;
- no convertir memoria en autoridad automatica;
- no introducir base de datos persistente si JSON local sigue siendo suficiente;
- no crear otro frontend ni otro runner.

## Fuentes externas consultadas

Fuentes primarias o estables revisadas para ideas de auditabilidad y agentes:

- NIST AI Risk Management Framework:
  https://www.nist.gov/itl/ai-risk-management-framework
- LangGraph overview:
  https://docs.langchain.com/oss/python/langgraph
- LangGraph durable execution:
  https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph interrupts / human-in-the-loop:
  https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
- OpenTelemetry documentation:
  https://opentelemetry.io/docs/
- ReAct: Synergizing Reasoning and Acting in Language Models:
  https://arxiv.org/abs/2210.03629
- Reflexion: Language Agents with Verbal Reinforcement Learning:
  https://arxiv.org/abs/2303.11366
- Datasheets for Datasets:
  https://arxiv.org/abs/1803.09010
- Model Cards for Model Reporting:
  https://arxiv.org/abs/1810.03993

Estas referencias no obligan a implementar esos frameworks literalmente. Sirven
para alinear la Fase 7 con criterios reconocibles: transparencia, trazabilidad,
human-in-the-loop, memoria supervisada, acciones restringidas y observabilidad.
