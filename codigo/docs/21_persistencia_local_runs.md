# Persistencia local de ejecuciones

## Objetivo

Implementar el primer hito de la Fase 2: guardar evidencia ligera y consultable
de una ejecucion del pipeline sin introducir base de datos externa.

La persistencia local permite auditar:

- estado final validado;
- decisiones del supervisor y agentes;
- artefactos producidos;
- metricas;
- evaluacion;
- errores;
- ruta del informe final.

## Implementacion

Archivo principal:

```text
codigo/app/services/run_persistence.py
```

Tests:

```text
codigo/tests/test_run_persistence.py
```

El servicio expone:

```text
save_run_snapshot(state, output_dir) -> RunSnapshot
load_run_snapshot(run_id, runs_dir) -> RunSnapshot
update_run_index(snapshot, runs_dir) -> None
load_run_index(runs_dir) -> RunIndex
extract_decisions(state) -> list[dict]
```

## Estructura en disco

La ruta por defecto es:

```text
codigo/reports/runs/
```

Cada ejecucion se guarda en una carpeta por `run_id`:

```text
codigo/reports/runs/<run_id>/
```

Ficheros generados:

```text
state_final.json
decisions.json
artifacts.json
metrics.json
evaluation.json
summary.md
snapshot.json
```

Ademas, el directorio raiz mantiene:

```text
index.json
```

## Contenido persistido

`state_final.json` contiene el `TFMStateModel` completo en modo JSON. No incluye
datasets pesados; mantiene rutas, configuraciones, mensajes, metricas,
evaluacion, errores y artefactos.

`decisions.json` extrae los mensajes con rol `supervisor` o `agent`, parsea su
contenido JSON y conserva:

- indice del mensaje;
- rol;
- nombre del nodo;
- fecha del mensaje;
- `agent_name`;
- `decision_id`;
- payload completo.

`artifacts.json` conserva la lista de `ArtifactRef`.

`metrics.json` guarda `MetricsReport` si existe.

`evaluation.json` guarda `EvaluationResult` si existe.

`summary.md` ofrece una vista humana rapida de la ejecucion.

`snapshot.json` guarda la metadata del snapshot, incluyendo rutas de los
ficheros persistidos.

`index.json` contiene entradas compactas para listar ejecuciones sin cargar cada
estado completo.

## Decisiones de diseno

- La persistencia se implementa como servicio puro, no como nodo del grafo.
- No se modifica `run_cwru_pipeline`; el pipeline actual sigue siendo la base
  estable.
- El `run_id` debe ser un nombre simple de carpeta, no una ruta.
- Si se guarda de nuevo el mismo `run_id`, la entrada de `index.json` se
  sustituye en lugar de duplicarse.
- El indice se ordena por fecha descendente.
- No se introduce PostgreSQL, Redis ni checkpoints persistentes todavia.

## Verificacion

Comando focalizado:

```bash
conda run -n tfm_v2 python -m unittest codigo.tests.test_run_persistence
```

Resultado esperado:

```text
Ran 4 tests
OK
```

Comando completo:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

La validacion integrada debe comprobar que una ejecucion real del pipeline CWRU
puede guardarse con:

```python
snapshot = save_run_snapshot(final_state, "codigo/reports/runs")
```

## Encaje con la Fase 2

Este hito prepara el siguiente paso:

```text
run_and_persist_cwru_pipeline(...)
```

La idea es mantener separadas dos capacidades:

- ejecutar el pipeline puro;
- ejecutar el pipeline y persistir la evidencia automaticamente.

Esa separacion evita introducir comportamiento nuevo en una funcion ya validada
y deja una frontera clara para el Hito 2.
