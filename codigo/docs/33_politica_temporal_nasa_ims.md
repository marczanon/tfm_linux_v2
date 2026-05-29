# Politica temporal NASA IMS v1

Fecha: 2026-05-29.

## Objetivo

Definir una politica explicita, versionada y trazable para permitir ejecuciones
completas sobre NASA IMS sin presentar etiquetas inventadas como si fueran
anotaciones oficiales del dataset.

La politica se identifica como:

```text
nasa_ims_temporal_v1
```

## Alcance

Esta version se aplica a manifiestos comunes de `nasa_ims_bearing` generados a
partir de carpetas preextraidas. No modifica datos crudos, no llama a LLMs y no
crea senales sinteticas. Solo reescribe un nuevo manifiesto derivado:

```text
manifest_temporal_policy_v1.csv
```

El manifiesto original se conserva para trazabilidad.

## Regla de etiquetado proxy

NASA IMS es un dataset run-to-failure. En ausencia de etiquetas por ventana
oficiales en la copia local, la politica v1 usa el orden cronologico dentro de
cada `run_id`:

- el tramo inicial se etiqueta como `normal`;
- el tramo posterior se etiqueta como `degradation`;
- las etiquetas se declaran como `temporal_proxy_v1`;
- `official_nasa_labels` queda siempre en `false`.

Esto permite entrenar detectores de anomalias con ventanas nominales iniciales
y evaluar contra una degradacion proxy, pero las metricas resultantes son
evidencia metodologica, no un resultado oficial sobre NASA IMS.

## Regla de particion

La politica escribe `split_hint` en `metadata_json` para evitar que el ejecutor
de estructuracion tenga que deducir particiones por su cuenta.

Para cada secuencia temporal:

- al menos un registro inicial normal va a `train`;
- si hay suficientes registros normales, puede reservarse uno para
  `validation`;
- los registros normales restantes se reservan como `test`;
- todos los registros de degradacion proxy van a `test`.

El ejecutor `structuring.py` usa estos hints solo si todos los registros
limpios los declaran. Si no existen, mantiene la politica historica CWRU:
ventanas normales para entrenamiento/validacion y fallos para test.

## Guardarrailes

- NASA IMS completo sigue bloqueado si no se declara `dataset_policy_id`.
- La politica v1 requiere al menos tres registros por `run_id`.
- La planificacion rechaza politicas desconocidas para el dataset.
- Las metricas producidas con esta politica deben citar
  `dataset_policy_id=nasa_ims_temporal_v1`.
- Ningun informe debe describir estas etiquetas como oficiales de NASA.

## Integracion

La politica se implementa en:

```text
codigo/app/services/nasa_ims_temporal_policy.py
codigo/app/services/pipeline_runner.py
codigo/app/executors/structuring.py
codigo/scripts/run_dataset_pipeline_with_memory.py
codigo/tests/test_nasa_ims_temporal_policy.py
codigo/tests/test_pipeline_runner.py
```

Uso desde el runner comun:

```text
python -m codigo.scripts.run_dataset_pipeline_with_memory \
  --dataset-id nasa_ims_bearing \
  --adapter-id nasa_ims_bearing \
  --raw-path codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen \
  --run-id nasa-runner-temporal-policy-v1-completed-low-metrics-002 \
  --dataset-policy-id nasa_ims_temporal_v1
```

## Validacion inicial

La ejecucion local
`nasa-runner-temporal-policy-v1-completed-low-metrics-002` comprobo que el
runner ya no se bloquea por falta de politica, alcanza modelado y evaluacion,
y genera informe aunque las metricas no alcancen los umbrales del MVP.

Resultado tecnico:

- planificacion: `can_execute_requested_stages=true`;
- estado final: `completed`;
- evaluacion: `approved=false`;
- manifiesto derivado: `manifest_temporal_policy_v1.csv`;
- labels por manifiesto: 2 `normal`, 1 `degradation`;
- estrategia de split: `metadata_json_split_hint`;
- ventanas: 3 train normales, 6 test;
- test: 3 ventanas normales y 3 de degradacion;
- precision 0.5000, recall 1.0000, F1 0.6667, FPR 1.0000.

El evaluador marca la run como no aprobada por FPR excesiva, pero el supervisor
la deja completada con informe tecnico. Esto es correcto: la politica habilita
una ejecucion completa y auditable, pero no convierte automaticamente el
resultado en evidencia aprobada.

## Limitaciones

- La politica v1 es simple y conservadora; no modela estados intermedios de
  degradacion ni severidad continua.
- En subconjuntos muy pequenos, la estimacion de FPR y umbrales es inestable.
- Para resultados principales del TFM se necesitara revisar la politica sobre
  secuencias NASA IMS mas largas y justificar el tramo nominal elegido.
- La comparacion con CWRU debe evitarse salvo como validacion de infraestructura,
  porque la semantica experimental y las etiquetas son distintas.
