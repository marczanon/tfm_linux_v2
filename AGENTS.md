# AGENTS.md

Instrucciones de trabajo para futuras sesiones de desarrollo del TFM.

## Contexto del proyecto

Este repositorio corresponde a un TFM sobre una aplicacion multiagente para procesamiento de datos y deteccion de anomalias industriales, especialmente en maquinaria como turbinas, motores, rodamientos y sistemas rotativos con sensores de vibracion.

Documento de referencia principal:

- `Documento TFM_ Arquitectura y Hoja de Ruta.pdf`
- `codigo/docs/133_fase11_reenfoque_hibrido_nasa_replay_agentico.md`
- `codigo/docs/139_fase11_catalogo_evidencia_causal_por_registro.md`
- `codigo/docs/140_fase11_policy_proposal_consultiva.md`
- `codigo/docs/141_fase11_campana_monitorizacion_agentiva_56h.md`
- `codigo/docs/142_fase11_cinematica_monitorizacion_y_export_evidencia.md`
- `codigo/docs/135_fase11_motor_triggers_p3_determinista.md`
- `codigo/docs/131_fase10_sala_control_agentica_historia_visual.md`
- `codigo/docs/95_cierre_fase9_run_to_failure_maximo_nivel.md`
- `codigo/docs/48_hoja_ruta_fase_6_dockerizacion.md`
- `codigo/docs/36_hoja_ruta_fase_5_aplicacion.md`
- `codigo/docs/32_hoja_ruta_fase_4.md`
- `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`
- `codigo/docs/26_hoja_ruta_fase_3.md`
- `codigo/docs/20_hoja_ruta_fase_2.md`
- `codigo/docs/19_estado_actual_mvp.md`

`HOJA_RUTA_TFM.md` queda como referencia historica de la Fase 1. Tras los
cierres operativos de Fases 6, 9 y 10, la guia inmediata para nuevas sesiones
es `codigo/docs/133_fase11_reenfoque_hibrido_nasa_replay_agentico.md`, con el
cierre implementado mas reciente en
`codigo/docs/142_fase11_cinematica_monitorizacion_y_export_evidencia.md`. La hoja
`128_fase11_hoja_ruta_industrializacion_agentica_event_driven.md` se conserva
como propuesta historica amplia; colas, workers, nuevos datasets y despliegue
industrial quedan diferidos. Fases 2--6 permanecen como contexto historico.

La arquitectura objetivo usa LangGraph con patron de supervisor jerarquico. Los agentes toman decisiones y generan configuraciones estructuradas. Los ejecutores Python deterministas realizan las transformaciones reales sobre los datos.

## Reglas principales

- No mezclar memoria academica y codigo.
- El codigo vive en `codigo/`.
- La memoria LaTeX vive en `memoria/`.
- Los recursos academicos, PDFs, referencias y diagramas viven en `recursos/`.
- La memoria debe actualizarse en paralelo al desarrollo.
- Antes de implementar una nueva mejora, revisar
  `codigo/docs/133_fase11_reenfoque_hibrido_nasa_replay_agentico.md`,
  `codigo/docs/142_fase11_cinematica_monitorizacion_y_export_evidencia.md`,
  `codigo/docs/141_fase11_campana_monitorizacion_agentiva_56h.md`,
  `codigo/docs/140_fase11_policy_proposal_consultiva.md`,
  `codigo/docs/139_fase11_catalogo_evidencia_causal_por_registro.md`,
  `codigo/docs/135_fase11_motor_triggers_p3_determinista.md`,
  `codigo/docs/131_fase10_sala_control_agentica_historia_visual.md`,
  `codigo/docs/95_cierre_fase9_run_to_failure_maximo_nivel.md`,
  `codigo/docs/54_cierre_operativo_fase6.md`,
  `codigo/docs/48_hoja_ruta_fase_6_dockerizacion.md` y
  `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`; usar
  `codigo/docs/36_hoja_ruta_fase_5_aplicacion.md`,
  `codigo/docs/32_hoja_ruta_fase_4.md`, `codigo/docs/26_hoja_ruta_fase_3.md`
  y `codigo/docs/20_hoja_ruta_fase_2.md` como contexto historico.
- La Fase 6 queda cerrada operativamente con Docker minimo reproducible. El
  bloque activo es la monitorizacion hibrida NASA mediante replay causal de la
  hoja `133`; los cambios se trasladaran a Docker solo tras estabilizar la
  superficie local. Colas distribuidas, nuevos datasets, SLURM, cloud y
  autenticacion multiusuario siguen fuera de alcance salvo decision explicita.
- No permitir que un agente escriba y ejecute codigo arbitrario para transformar datos.
- Las decisiones de agentes deben pasar por esquemas Pydantic o contratos JSON estrictos.
- Los ejecutores deben ser funciones o modulos Python reproducibles y testeables.
- Mantener trazabilidad de datos, configuraciones, metricas y artefactos.

## Protocolo obligatorio de reutilizacion

Antes de crear codigo nuevo, scripts, contratos, endpoints, servicios o tests, se
debe comprobar si ya existe una pieza equivalente o ampliable. Este paso es
obligatorio y debe hacerse antes del diseno de la solucion.

Checklist minima:

1. Definir en una frase la capacidad que se quiere anadir.
2. Buscar en `codigo/app/`, `codigo/scripts/`, `codigo/tests/` y `codigo/docs/`
   con `rg` usando nombres funcionales, sinonimos y conceptos relacionados.
3. Identificar el modulo canonico que ya posee esa responsabilidad, si existe.
4. Decidir explicitamente una de estas opciones:
   - reutilizar sin cambios;
   - adaptar una funcion o contrato existente;
   - extender una pieza existente manteniendo compatibilidad;
   - crear una pieza nueva solo si no hay propietario claro.
5. Si se crea algo nuevo, documentar por que no encaja en lo existente y que
   frontera de responsabilidad tendra para evitar solapamientos futuros.

Regla practica: no se debe duplicar una funcion, contrato o script porque el
nombre actual parezca especifico. Primero se evalua si conviene renombrar,
envolver o generalizar la pieza existente. Ejemplos actuales:

- ejecucion multi-dataset: `pipeline_runner.py`;
- contratos de ejecucion API: `api_runs.py` extendiendo `PipelineRunRequest`;
- revision humana: `HumanReviewSettings`, `HumanApproval` y `human_review.py`;
- persistencia y consulta de runs: `run_persistence.py` y `run_registry.py`;
- adaptadores de dataset y senal: `dataset_adapters.py` y `signal_adapters.py`;
- memoria RAG: `vector_memory.py`, `agent_memory.py` y servicios asociados.

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
MVP ya construido. Para trabajo nuevo, seguir el cierre operativo de Fase 6 en
`codigo/docs/54_cierre_operativo_fase6.md` y la metodologia de reutilizacion en
`codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`.

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

## Referencias historicas de alcance

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
`codigo/docs/48_hoja_ruta_fase_6_dockerizacion.md`, usando
`codigo/docs/36_hoja_ruta_fase_5_aplicacion.md` como referencia de cierre de la
fase anterior. El proyecto debe avanzar paso a paso, manteniendo
reproducibilidad, trazabilidad y separacion limpia entre aplicacion y memoria
academica.
