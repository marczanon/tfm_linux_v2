# Grafo LangGraph minimo CWRU

Nota: esta pagina documenta la primera version secuencial del grafo. La version
actual del pipeline incorpora el supervisor determinista descrito en
`12_supervisor_determinista.md`.

## Objetivo

Encadenar los ejecutores deterministas del MVP en un grafo LangGraph local,
sin introducir todavia razonamiento generativo ni puntos Human-in-the-loop.

El flujo implementado es:

```text
manifest_executor
-> profiler_executor
-> cleaning_executor
-> structuring_executor
-> modeling_executor
-> evaluator
-> completed
```

## Implementacion

Archivo principal:

```text
codigo/app/graph/pipeline.py
```

Funciones y componentes:

- `PipelineExecutors`: contenedor inyectable de ejecutores deterministas.
- `build_cwru_pipeline(...)`: compila el grafo secuencial.
- `run_cwru_pipeline(...)`: ejecuta el grafo desde un estado inicial validado.

El grafo usa `TFMState` como vista ligera de LangGraph y valida cada transicion
contra `TFMStateModel`. Los nodos no guardan senales ni arrays en el estado:
solo rutas, configuraciones, metricas ligeras, mensajes, errores y referencias
a artefactos.

## Actualizacion del estado

Cada nodo:

1. valida el estado entrante;
2. comprueba que existan las rutas necesarias para su fase;
3. ejecuta el modulo determinista correspondiente;
4. anade artefactos, errores y un mensaje de trazabilidad;
5. avanza `current_stage` y `next_node` si el resultado es correcto;
6. detiene el grafo con `current_stage = failed` si hay error.

Mientras no existan agentes especializados, el grafo usa las configuraciones
por defecto de limpieza, estructuracion y modelado:

- `DEFAULT_CLEANING_CONFIG`;
- `DEFAULT_STRUCTURING_CONFIG`;
- `DEFAULT_MODELING_CONFIG`.

## Compatibilidad con LangGraph

Durante la verificacion se detecto que `checkpoint_id` es un nombre reservado
por LangGraph 1.1. Por ese motivo se ha eliminado de la vista `TypedDict` usada
por el grafo. La persistencia futura debera modelarse mediante el sistema de
checkpoints de LangGraph o con un campo de aplicacion que no colisione con
nombres reservados.

## Verificacion

Se ha anadido:

```text
codigo/tests/test_graph_pipeline.py
```

La prueba usa ejecutores simulados para validar la orquestacion sin reprocesar
el dataset completo:

- orden de llamada de los nodos;
- actualizacion de rutas y artefactos;
- propagacion de configuraciones por defecto;
- lectura ligera de perfil y metricas;
- parada controlada ante un ejecutor fallido.

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 50 tests
OK
```

Prueba integrada con CWRU real:

```text
current_stage = completed
next_node = None
artifacts = 12
metrics_path = codigo/reports/cwru_bearing/evaluation/metrics.json
f1_score = 0.9995747093847462
```

## Siguiente paso

Este paso ya ha evolucionado en `12_supervisor_determinista.md`, donde el grafo
pasa a enrutar todas las transiciones mediante un nodo `supervisor` con salida
`SupervisorDecision` validada por Pydantic.
