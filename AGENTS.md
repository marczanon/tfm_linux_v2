# AGENTS.md

Instrucciones de trabajo para futuras sesiones de desarrollo del TFM.

## Contexto del proyecto

Este repositorio corresponde a un TFM sobre una aplicacion multiagente para procesamiento de datos y deteccion de anomalias industriales, especialmente en maquinaria como turbinas, motores, rodamientos y sistemas rotativos con sensores de vibracion.

Documento de referencia principal:

- `Documento TFM_ Arquitectura y Hoja de Ruta.pdf`
- `codigo/docs/20_hoja_ruta_fase_2.md`
- `codigo/docs/19_estado_actual_mvp.md`

`HOJA_RUTA_TFM.md` queda como referencia historica de la Fase 1. A partir del
cierre del MVP local, la guia operativa para nuevas sesiones es la hoja de ruta
de Fase 2.

La arquitectura objetivo usa LangGraph con patron de supervisor jerarquico. Los agentes toman decisiones y generan configuraciones estructuradas. Los ejecutores Python deterministas realizan las transformaciones reales sobre los datos.

## Reglas principales

- No mezclar memoria academica y codigo.
- El codigo vive en `codigo/`.
- La memoria LaTeX vive en `memoria/`.
- Los recursos academicos, PDFs, referencias y diagramas viven en `recursos/`.
- La memoria debe actualizarse en paralelo al desarrollo.
- Antes de implementar una fase, revisar `codigo/docs/20_hoja_ruta_fase_2.md`.
- Priorizar un MVP local antes de Docker, SLURM o frontend.
- No permitir que un agente escriba y ejecute codigo arbitrario para transformar datos.
- Las decisiones de agentes deben pasar por esquemas Pydantic o contratos JSON estrictos.
- Los ejecutores deben ser funciones o modulos Python reproducibles y testeables.
- Mantener trazabilidad de datos, configuraciones, metricas y artefactos.

## Primer paso de implementacion

El primer paso de codigo sera crear la arquitectura de directorios:

```text
codigo/
memoria/
recursos/
```

Despues, crear subdirectorios:

```text
codigo/app/api/
codigo/app/core/
codigo/app/graph/
codigo/app/agents/
codigo/app/executors/
codigo/app/schemas/
codigo/app/services/
codigo/app/utils/
codigo/data/raw/
codigo/data/interim/
codigo/data/processed/
codigo/data/tensors/
codigo/data/external/
codigo/experiments/
codigo/models/
codigo/reports/
codigo/tests/
codigo/scripts/
codigo/slurm/
codigo/docker/
codigo/docs/
memoria/capitulos/
memoria/figuras/
memoria/tablas/
memoria/bibliografia/
memoria/anexos/
recursos/pdfs/
recursos/referencias/
recursos/diagramas/
```

## Orden recomendado de desarrollo

Este orden historico corresponde a la Fase 1 y se conserva como contexto del
MVP ya construido. Para trabajo nuevo, seguir la Fase 2 definida en
`codigo/docs/20_hoja_ruta_fase_2.md`.

1. Crear estructura de directorios.
2. Crear esqueleto LaTeX de la memoria.
3. Definir caso de uso industrial y dataset inicial.
4. Disenar el estado global de LangGraph.
5. Crear esquemas Pydantic para entradas, salidas y configuraciones.
6. Implementar perfilado de datos.
7. Implementar ejecutor de limpieza.
8. Implementar ejecutor de estructuracion temporal.
9. Implementar generacion de ventanas o tensores.
10. Implementar modelos base de anomalias.
11. Implementar evaluacion de metricas.
12. Montar grafo LangGraph minimo.
13. Anadir agente redactor e informes.
14. Anadir persistencia.
15. Exponer API con FastAPI.
16. Dockerizar.
17. Preparar integracion SLURM.
18. Crear frontend.

## Nodos del grafo

Nodos previstos:

- Supervisor: decide la siguiente fase del flujo.
- Limpiador: analiza perfil estadistico y propone limpieza.
- Ejecutor de limpieza: aplica operaciones deterministas.
- Estructurador: decide escalado, particion y ventanas.
- Ejecutor de estructuracion: genera datasets procesados o tensores.
- Modelador: selecciona algoritmo e hiperparametros.
- Ejecutor de modelado: entrena y predice.
- Evaluador: interpreta metricas y decide si aprobar.
- Redactor: genera informe tecnico.
- Human Review: punto de aprobacion para trabajos costosos.

## Estado global recomendado

El estado de LangGraph debe incluir:

- `thread_id`
- `project_context`
- `raw_path`
- `profile_path`
- `clean_path`
- `tensor_path`
- `report_path`
- `messages`
- `dataset_profile`
- `cleaning_config`
- `structuring_config`
- `modeling_config`
- `metrics`
- `evaluation`
- `errors`
- `human_approval`
- `artifacts`

No cargar datasets completos dentro del estado. Usar rutas y resumentes estadisticos.

## Contratos de agentes

Cada agente debe devolver JSON valido o un objeto validable con Pydantic.

Evitar:

- Texto libre como salida principal.
- Decisiones ambiguas.
- Campos omitidos cuando deberian ser `null`.
- Codigo generado dinamicamente para ejecutarse sobre datos.

Preferir:

- Esquemas cerrados.
- Validacion estricta.
- Mensajes de error claros.
- Reintento controlado si el JSON es invalido.

## Ejecutores deterministas

Los ejecutores son responsables de:

- Leer artefactos desde disco.
- Aplicar transformaciones.
- Guardar resultados.
- Devolver rutas, metricas y logs.

Los ejecutores no deben depender de razonamiento generativo. Deben ser reproducibles, testeables y seguros.

## Modelos base

Modelos iniciales recomendados:

- Isolation Forest.
- One-Class SVM.
- Local Outlier Factor.
- PCA reconstruction error.
- Autoencoder denso.
- LSTM Autoencoder en fase posterior.

## Memoria LaTeX

La memoria debe estar separada del codigo.

Estructura prevista:

```text
memoria/main.tex
memoria/capitulos/01_introduccion.tex
memoria/capitulos/02_estado_del_arte.tex
memoria/capitulos/03_arquitectura.tex
memoria/capitulos/04_metodologia.tex
memoria/capitulos/05_implementacion.tex
memoria/capitulos/06_experimentos.tex
memoria/capitulos/07_resultados.tex
memoria/capitulos/08_conclusiones.tex
```

Cada avance tecnico debe tener reflejo en la memoria:

- Que se ha hecho.
- Por que se ha elegido.
- Como se ha validado.
- Que limitaciones quedan.

## Verificacion

Cuando se escriba codigo, verificar con tests o ejecuciones pequenas antes de avanzar.

Prioridades de verificacion:

- Tests de esquemas Pydantic.
- Tests de ejecutores.
- Prueba del pipeline con dataset pequeno.
- Validacion de rutas y artefactos generados.
- Revision de que la memoria sigue separada del codigo.

## Fases futuras

No abordar dentro de la Fase 2:

- PostgreSQL para checkpoints.
- Redis.
- Docker Compose completo.
- SLURM.
- React.
- Flutter.
- Observabilidad avanzada.

## Nota operativa

Antes de empezar cualquier cambio de codigo, leer este archivo y
`codigo/docs/20_hoja_ruta_fase_2.md`. El proyecto debe avanzar paso a paso,
manteniendo reproducibilidad, trazabilidad y separacion limpia entre aplicacion
y memoria academica.
