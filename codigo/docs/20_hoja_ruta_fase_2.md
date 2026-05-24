# Hoja de ruta Fase 2

Fecha de inicio: 2026-05-24.

## Punto de partida

La Fase 1 queda cerrada como MVP local funcional. El sistema ya ejecuta el
flujo completo sobre CWRU Bearing Dataset:

```text
datos crudos
-> manifiesto
-> perfilado
-> limpieza
-> estructuracion temporal
-> modelado
-> evaluacion
-> juicio agentico
-> informe tecnico
```

La arquitectura actual ya demuestra la idea central del TFM: agentes LLM que
toman decisiones estructuradas y ejecutores deterministas que realizan las
operaciones reales de datos, modelado, evaluacion y reporting.

Documento de cierre de la Fase 1:

```text
codigo/docs/19_estado_actual_mvp.md
```

## Objetivo de la Fase 2

Convertir el MVP funcional en una aplicacion reproducible, auditable y preparada
para experimentacion. La prioridad ya no es anadir nodos al flujo principal, sino
consolidar ejecuciones, conservar evidencia, comparar resultados y preparar una
interfaz minima de servicio cuando la persistencia este estable.

La Fase 2 debe producir:

- persistencia local de ejecuciones;
- trazabilidad consultable por `run_id`;
- base para comparar experimentos;
- punto Human Review basico;
- API minima solo despues de tener persistencia;
- documentacion tecnica y memoria actualizadas.

## Fuera de alcance de la Fase 2

No se abordara en esta fase:

- SLURM;
- ejecucion HPC;
- entrenamiento distribuido;
- Docker Compose completo;
- frontend;
- PostgreSQL como dependencia obligatoria;
- Redis;
- observabilidad avanzada;
- despliegue en cluster.

Estos puntos quedan para fases posteriores, cuando el nucleo local sea estable,
persistente y consultable.

## Principios de trabajo

- Mantener el MVP local como base estable.
- No romper el pipeline CWRU existente.
- No introducir infraestructura pesada antes de necesitarla.
- Persistir rutas, contratos, decisiones, metricas y artefactos, no datasets
  completos.
- Mantener separacion entre agentes LLM y ejecutores deterministas.
- Cada avance debe tener tests o una ejecucion pequena verificable.
- La memoria LaTeX debe actualizarse cuando una decision cambie la arquitectura,
  metodologia o resultados.

## Hito 1: Persistencia local de ejecuciones

Objetivo: guardar una evidencia completa y ligera de cada ejecucion.

Ruta propuesta:

```text
codigo/reports/runs/
```

Artefactos previstos:

```text
codigo/reports/runs/index.json
codigo/reports/runs/<run_id>/state_final.json
codigo/reports/runs/<run_id>/decisions.json
codigo/reports/runs/<run_id>/artifacts.json
codigo/reports/runs/<run_id>/metrics.json
codigo/reports/runs/<run_id>/evaluation.json
codigo/reports/runs/<run_id>/summary.md
```

Implementacion candidata:

```text
codigo/app/services/run_persistence.py
codigo/tests/test_run_persistence.py
```

Debe permitir:

- guardar el estado final validado;
- extraer decisiones de agentes desde `messages`;
- listar artefactos producidos;
- guardar metricas y evaluacion;
- crear o actualizar un indice de ejecuciones;
- cargar una ejecucion por `run_id`;
- funcionar sin base de datos externa.

Criterio de aceptacion:

- tests unitarios de escritura, lectura e indice;
- prueba integrada con una ejecucion real del pipeline;
- documento tecnico `21_persistencia_local_runs.md`.

## Hito 2: Integracion de persistencia en el pipeline

Objetivo: que cada ejecucion completa deje una carpeta persistida sin pasos
manuales.

Opciones:

- persistir al final de `run_cwru_pipeline`;
- crear un wrapper tipo `run_and_persist_cwru_pipeline`;
- anadir un nodo final de persistencia si encaja en el grafo.

Decision inicial recomendada:

```text
run_and_persist_cwru_pipeline(...)
```

Razon: evita mezclar persistencia con la funcion actual ya verificada y permite
comparar pipeline puro frente a pipeline persistido.

Criterio de aceptacion:

- el pipeline actual sigue pasando tests sin cambios de comportamiento;
- el wrapper genera `codigo/reports/runs/<run_id>/`;
- el indice permite listar la ejecucion;
- el informe final queda enlazado desde el resumen persistido.

## Hito 3: Registro consultable y comparacion basica

Objetivo: poder responder preguntas simples sobre ejecuciones anteriores.

Capacidades:

- listar runs ordenados por fecha;
- filtrar por dataset, estado o aprobacion;
- recuperar metricas principales;
- comparar dos o mas runs por precision, recall, F1 y FPR;
- identificar artefactos principales de cada run.

Implementacion candidata:

```text
codigo/app/services/run_registry.py
codigo/tests/test_run_registry.py
```

Salida prevista:

- estructuras Python validadas o diccionarios JSON simples;
- no requiere frontend;
- no requiere API todavia.

Criterio de aceptacion:

- comparacion reproducible entre al menos dos ejecuciones locales;
- documento tecnico con ejemplo de consulta.

## Hito 4: Protocolo experimental local

Objetivo: pasar de una unica ejecucion valida a un conjunto pequeno de
experimentos comparables.

Experimentos iniciales candidatos:

- baseline actual Isolation Forest;
- variacion de `threshold_quantile`;
- variacion de `n_estimators`;
- variacion controlada del tamano de ventana si el estructurador lo permite en
  una fase posterior;
- comparacion con otro modelo solo cuando exista ejecutor determinista.

Regla importante:

```text
No anadir un nuevo modelo al contrato si no existe un ejecutor reproducible.
```

Criterio de aceptacion:

- definicion de un manifiesto experimental;
- al menos dos ejecuciones persistidas y comparables;
- tabla de resultados para memoria.

## Hito 5: Human Review basico

Objetivo: introducir un punto de aprobacion humana sin complicar la interfaz.

Primera version:

- revision antes de modelado o antes de ejecutar experimentos multiples;
- entrada manual simple en estado o funcion wrapper;
- registro de `human_approval` en el estado persistido.

No objetivo en esta fase:

- UI interactiva completa;
- aprobaciones remotas;
- colas distribuidas.

Criterio de aceptacion:

- test de flujo aprobado;
- test de flujo rechazado;
- registro persistido de aprobacion, revisor y motivo.

## Hito 6: API minima con FastAPI

Objetivo: exponer el MVP solo cuando la persistencia local este funcionando.

Endpoints candidatos:

```text
POST /runs
GET /runs
GET /runs/{run_id}
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/report
```

Restricciones:

- sin streaming avanzado;
- sin autenticacion compleja;
- sin frontend;
- sin base de datos externa obligatoria.

Criterio de aceptacion:

- API levanta localmente;
- endpoints leen desde el registro persistido;
- tests de endpoints con cliente de prueba;
- documentacion tecnica de uso.

## Hito 7: Actualizacion academica

Objetivo: reflejar la Fase 2 en la memoria del TFM.

Puntos a documentar:

- cierre del MVP local;
- motivacion de la persistencia;
- trazabilidad de decisiones agenticas;
- reproducibilidad de experimentos;
- separacion entre ejecucion y consulta;
- limitaciones de CWRU como benchmark controlado.

Capitulos afectados probablemente:

```text
memoria/capitulos/04_metodologia.tex
memoria/capitulos/05_implementacion.tex
memoria/capitulos/06_experimentos.tex
memoria/capitulos/07_resultados.tex
```

## Orden de ejecucion recomendado

1. Hito 1: persistencia local de ejecuciones.
2. Hito 2: wrapper de pipeline persistido.
3. Hito 3: registro consultable y comparacion basica.
4. Hito 4: protocolo experimental local.
5. Hito 5: Human Review basico.
6. Hito 6: API minima.
7. Hito 7: actualizacion academica continua.

## Primer paso concreto

Implementar `codigo/app/services/run_persistence.py` con funciones para guardar
y cargar ejecuciones:

```text
save_run_snapshot(state: TFMStateModel, output_dir: Path) -> RunSnapshot
load_run_snapshot(run_id: str, runs_dir: Path) -> RunSnapshot
update_run_index(snapshot: RunSnapshot, runs_dir: Path) -> None
```

La primera validacion debe usar una ejecucion real del pipeline CWRU y comprobar
que el estado final, decisiones, metricas, evaluacion y artefactos quedan
persistidos sin introducir dependencias externas.
