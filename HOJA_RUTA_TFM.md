# Hoja de ruta del TFM

Documento de referencia para iniciar el desarrollo del TFM:

**Diseno y desarrollo de una arquitectura multiagente basada en LangGraph para el procesamiento, modelado y deteccion de anomalias en entornos industriales.**

Fuente de contexto inicial: `Documento TFM_ Arquitectura y Hoja de Ruta.pdf`.

Fecha de preparacion: 2026-04-30.

## 1. Objetivo del proyecto

Construir una aplicacion multiagente capaz de ejecutar el flujo completo de datos dentro del nicho de deteccion de anomalias industriales, especialmente en maquinaria como turbinas, motores, rodamientos o sistemas rotativos monitorizados mediante sensores de vibracion y variables complementarias.

El sistema debe cubrir:

- Ingestion de datos industriales.
- Perfilado automatico del dataset.
- Limpieza y normalizacion.
- Estructuracion temporal.
- Generacion de ventanas, features o tensores.
- Seleccion y entrenamiento de modelos de deteccion de anomalias.
- Evaluacion de metricas.
- Auditoria de decisiones.
- Generacion de informes tecnicos.
- Exposicion futura mediante API y frontend.

La arquitectura seguira un patron de supervisor jerarquico en LangGraph. Los agentes razonaran y propondran decisiones, pero la transformacion matematica de datos se realizara mediante ejecutores Python deterministas.

## 2. Principios arquitectonicos

- El sistema sera multiagente, no un agente monolitico.
- LangGraph coordinara el flujo mediante un grafo con estado.
- El supervisor sera el nodo central de decision.
- Los agentes especializados no manipularan datasets completos.
- Los agentes deberan producir salidas estructuradas, preferiblemente JSON validado con Pydantic.
- Los ejecutores deterministas aplicaran las operaciones reales sobre los datos.
- El estado global almacenara rutas, configuraciones, metricas, errores, decisiones y artefactos.
- La memoria del TFM se escribira en paralelo al desarrollo.
- La memoria estara separada del codigo y se escribira en LaTeX.
- La persistencia futura se apoyara en PostgreSQL y checkpoints de LangGraph.
- Las ejecuciones costosas deberan pasar por un punto Human-in-the-loop.
- La version inicial debe funcionar localmente antes de avanzar a Docker, SLURM o frontend.

## 3. Primer paso: arquitectura de directorios

El primer paso antes de escribir codigo funcional sera crear una estructura limpia que separe codigo, memoria academica y recursos.

Estructura recomendada:

```text
tfm_linux_v2/
├── codigo/
│   ├── app/
│   │   ├── api/                  # FastAPI: endpoints, streaming, auth futura
│   │   ├── core/                 # configuracion, logging, constantes
│   │   ├── graph/                # LangGraph: grafo, estado, supervisor, transiciones
│   │   ├── agents/               # prompts y logica de agentes
│   │   ├── executors/            # limpieza, estructuracion, entrenamiento, evaluacion
│   │   ├── schemas/              # Pydantic: entradas, salidas, estado, JSON estrictos
│   │   ├── services/             # LLM, persistencia, datasets, SLURM, reportes
│   │   └── utils/
│   ├── data/
│   │   ├── raw/                  # datos originales
│   │   ├── interim/              # datos perfilados o parcialmente procesados
│   │   ├── processed/            # datos limpios
│   │   ├── tensors/              # ventanas, arrays, tensores
│   │   └── external/             # datasets publicos o de referencia
│   ├── experiments/              # notebooks, pruebas exploratorias, resultados
│   ├── models/                   # modelos entrenados, checkpoints, artefactos
│   ├── reports/                  # informes generados por el agente redactor
│   ├── tests/                    # tests unitarios e integracion
│   ├── scripts/                  # comandos auxiliares, carga de datos, entrenamiento
│   ├── slurm/                    # plantillas sbatch y ejecucion HPC futura
│   ├── docker/                   # Dockerfiles y configuracion por servicio
│   └── docs/                     # documentacion tecnica del codigo
│
├── memoria/
│   ├── main.tex
│   ├── capitulos/
│   │   ├── 01_introduccion.tex
│   │   ├── 02_estado_del_arte.tex
│   │   ├── 03_arquitectura.tex
│   │   ├── 04_metodologia.tex
│   │   ├── 05_implementacion.tex
│   │   ├── 06_experimentos.tex
│   │   ├── 07_resultados.tex
│   │   └── 08_conclusiones.tex
│   ├── figuras/
│   ├── tablas/
│   ├── bibliografia/
│   └── anexos/
│
├── recursos/
│   ├── pdfs/
│   ├── referencias/
│   └── diagramas/
│
└── README.md
```

Separacion principal:

- `codigo/`: aplicacion, experimentos, tests, datos y servicios.
- `memoria/`: memoria academica en LaTeX.
- `recursos/`: PDFs, referencias y diagramas de apoyo.

## 4. Paso 2: definir el alcance industrial

Concretar el caso de uso:

- Turbinas, motores, rodamientos, bombas o maquinaria rotativa.
- Sensores de vibracion, temperatura, presion, RPM, corriente, carga, caudal o acustica.
- Tipo de anomalia: fallo incipiente, degradacion, desbalanceo, cavitacion, fallo de rodamiento, sobretemperatura o comportamiento fuera de regimen.
- Disponibilidad de etiquetas: supervisado, semi-supervisado o no supervisado.

Entregable en memoria:

- Introduccion.
- Motivacion industrial.
- Problema.
- Objetivo general.
- Objetivos especificos.
- Alcance y limitaciones iniciales.

## 5. Paso 3: disenar el flujo completo de datos

Pipeline objetivo:

```text
datos crudos
→ perfilado automatico
→ limpieza
→ estructuracion temporal
→ extraccion de ventanas/features
→ entrenamiento de modelos
→ deteccion de anomalias
→ evaluacion
→ informe tecnico
→ visualizacion/API
```

Formatos iniciales:

- CSV para el MVP.
- Parquet en una fase posterior.
- Bases de datos o streaming industrial en una fase avanzada.

## 6. Paso 4: definir el estado global de LangGraph

El `State` debe disenarse antes de programar agentes.

Campos recomendados:

- `thread_id`: identificador de ejecucion.
- `project_context`: objetivo industrial y preferencias.
- `raw_path`: ruta de datos crudos.
- `profile_path`: ruta de perfilado.
- `clean_path`: ruta de datos limpios.
- `tensor_path`: ruta de tensores o ventanas.
- `report_path`: ruta del informe final.
- `messages`: historial de mensajes del grafo.
- `dataset_profile`: metadatos, tipos, nulos, distribuciones y muestra.
- `cleaning_config`: decisiones de limpieza.
- `structuring_config`: escalado, particion, ventanas y features.
- `modeling_config`: algoritmo, hiperparametros y recursos.
- `metrics`: metricas empiricas.
- `evaluation`: juicio del evaluador.
- `errors`: errores capturados.
- `human_approval`: aprobaciones o rechazos.
- `artifacts`: modelos, figuras, logs y salidas.

## 7. Paso 5: construir el MVP multiagente local

Primera version minima:

```text
Supervisor
→ Agente Limpiador
→ Ejecutor Limpieza
→ Agente Estructurador
→ Ejecutor Estructuracion
→ Agente Modelador
→ Ejecutor Modelado
→ Evaluador
→ Redactor
```

Restricciones del MVP:

- Sin frontend.
- Sin Docker complejo.
- Sin SLURM.
- Sin entrenamiento distribuido.
- Con dataset pequeno y reproducible.
- Con logs suficientes para auditar el flujo.

## 8. Paso 6: agentes y salidas JSON estrictas

Cada agente debe devolver estructuras validadas, no texto libre.

Agentes principales:

- Supervisor: decide la siguiente fase.
- Limpiador: propone imputacion, renombrado, eliminacion de columnas y tratamiento de outliers.
- Estructurador: decide escalado, particion train/validation/test y ventanas temporales.
- Modelador: selecciona algoritmo e hiperparametros.
- Evaluador: interpreta metricas segun el objetivo industrial.
- Redactor: genera informe tecnico del experimento.

La salida de los agentes debe validarse con Pydantic. Si una respuesta es invalida, el sistema debe capturar el error, pedir correccion y no continuar con un estado corrupto.

## 9. Paso 7: ejecutores deterministas

Los agentes no escriben codigo dinamico. Solo deciden.

Ejecutores necesarios:

- Perfilado de datos.
- Limpieza.
- Estructuracion temporal.
- Generacion de ventanas.
- Entrenamiento.
- Evaluacion.
- Exportacion de resultados.
- Generacion de informes.

Cada ejecutor debe recibir una configuracion validada y producir rutas o artefactos verificables.

## 10. Paso 8: modelos base de anomalias

Modelos recomendados para empezar:

- Isolation Forest.
- One-Class SVM.
- Local Outlier Factor.
- PCA reconstruction error.
- Autoencoder denso.
- LSTM Autoencoder o Temporal Convolutional Autoencoder para series temporales.

La primera meta no es tener muchos modelos, sino una bateria pequena, estable, comparable y bien documentada.

## 11. Paso 9: metricas y criterios de exito

Metricas tecnicas:

- Precision.
- Recall.
- F1-score.
- ROC-AUC si hay etiquetas.
- PR-AUC si las anomalias son raras.
- Tasa de falsos positivos.
- Tiempo de deteccion.
- Error de reconstruccion.
- Matriz de confusion.

Criterios industriales:

- Alta sensibilidad para fallos tempranos.
- Control de falsos positivos.
- Explicabilidad minima del evento detectado.
- Reproducibilidad del experimento.

## 12. Paso 10: persistencia

Introducir persistencia para:

- Reanudar ejecuciones.
- Auditar decisiones.
- Depurar estados anteriores.
- Conservar checkpoints del grafo.

Camino recomendado:

1. Persistencia local simple para el MVP.
2. PostgreSQL con checkpoints de LangGraph.
3. Politicas de limpieza de checkpoints antiguos.

## 13. Paso 11: Human-in-the-loop

Antes de entrenamientos costosos, el supervisor debe pedir aprobacion.

El usuario revisara:

- Dataset seleccionado.
- Perfil estadistico.
- Configuracion de limpieza.
- Ventanas temporales.
- Modelo candidato.
- Coste estimado.
- Tiempo previsto.

Si aprueba, continua. Si rechaza, vuelve al supervisor o genera informe parcial.

## 14. Paso 12: API con FastAPI

Rutas previstas:

- Crear ejecucion.
- Consultar estado.
- Subir dataset.
- Lanzar pipeline.
- Aprobar o rechazar punto humano.
- Descargar informe.
- Recibir streaming de eventos del grafo.

La API convertira LangGraph en un servicio usable por frontend o clientes externos.

## 15. Paso 13: observabilidad

Registrar:

- Decisiones de agentes.
- Prompts.
- Respuestas JSON.
- Errores.
- Metricas.
- Rutas de artefactos.
- Coste aproximado de llamadas LLM.
- Duracion de fases.

Futuras integraciones:

- Langfuse.
- Prometheus.
- Dashboards propios.

## 16. Paso 14: contenerizacion

Cuando el MVP local funcione, pasar a Docker Compose.

Servicios previstos:

- API FastAPI.
- PostgreSQL.
- Redis.
- Worker de tareas.
- Servicio frontend futuro.
- Volumenes persistentes.

## 17. Paso 15: SLURM/HPC

Preparar SLURM solo despues del MVP.

Elementos previstos:

- Plantillas `sbatch`.
- Dependencias `afterok`.
- Job arrays para grid search.
- Captura de logs.
- Devolucion de resultados al estado LangGraph.
- Integracion con el punto Human-in-the-loop.

## 18. Paso 16: frontend

Primera interfaz recomendada:

- React para dashboard tecnico.

Vistas:

- Datasets.
- Ejecuciones.
- Estado del grafo.
- Metricas.
- Logs.
- Informes.
- Aprobaciones humanas.

Flutter puede quedar como cliente futuro para una experiencia multiplataforma mas comercial.

## 19. Paso 17: memoria en paralelo

La memoria debe escribirse durante el desarrollo.

Capitulos sugeridos:

- Introduccion.
- Estado del arte.
- Arquitectura.
- Metodologia.
- Implementacion.
- Experimentos.
- Resultados.
- Conclusiones.

Por cada fase de codigo, actualizar tambien:

- Decisiones tecnicas.
- Justificacion de arquitectura.
- Diagramas.
- Resultados parciales.
- Limitaciones.
- Futuras mejoras.

## 20. Orden practico para empezar

1. Crear estructura de directorios.
2. Crear esqueleto LaTeX de la memoria.
3. Definir caso de uso industrial y datasets.
4. Disenar estado global.
5. Disenar contratos JSON de cada agente.
6. Implementar ejecutores deterministas.
7. Montar grafo LangGraph minimo.
8. Probar pipeline completo con un dataset pequeno.
9. Anadir persistencia.
10. Anadir API.
11. Anadir evaluacion seria.
12. Anadir informes.
13. Dockerizar.
14. Preparar SLURM.
15. Crear frontend.

## 21. Recomendacion de arranque

El primer bloque de trabajo real debe ser:

1. Crear la arquitectura de directorios.
2. Crear la memoria base en LaTeX.
3. Definir el estado global del sistema.

Esto deja una base limpia antes de escribir la primera linea funcional de la aplicacion.
