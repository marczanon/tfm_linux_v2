# Gestion ligera de runs y artefactos en Fase 3

## Objetivo

Conservar evidencia reproducible sin que el directorio de trabajo crezca de
forma descontrolada. En Fase 3 hay dos tipos de persistencia:

- `codigo/reports/runs/`: snapshots ligeros de estado, decisiones, metricas y
  evaluacion. Actualmente son pequenos y deben conservarse como evidencia.
- artefactos ejecutables en `codigo/experiments/`, `codigo/data/tensors/`,
  `codigo/data/processed/`, `codigo/models/` y `codigo/reports/<dataset>/`.
  Estos pueden crecer mucho porque incluyen tensores, modelos y features.

## Politica recomendada

1. Mantener los snapshots ligeros de `codigo/reports/runs/` salvo que sean
   pruebas claramente fallidas o duplicadas.
2. Mantener una evidencia canonica por hito experimental:
   - baseline CWRU Fase 2;
   - comparacion agentica de ventanas CWRU;
   - comparacion agentica de modelos CWRU;
   - smoke NASA IMS sin etiquetas supervisadas;
   - benchmark NASA IMS sintetico etiquetado, cuando exista.
3. Para experimentos comparativos, conservar siempre:
   - `experiment_plan.json`;
   - `comparison.json`;
   - `results_table.md`;
   - snapshots correspondientes en `codigo/reports/runs/`.
4. Tratar como regenerables los artefactos grandes:
   - `windows_raw.npz`;
   - modelos `.joblib`;
   - senales limpias generadas;
   - datos sinteticos generados por scripts.
5. Antes de borrar artefactos grandes, comprobar que existe una tabla o snapshot
   que recoja las metricas principales.

## Estado observado el 2026-05-27

Inventario local:

```text
codigo/reports/runs       ~876K
codigo/experiments        ~160M
codigo/reports/nasa_ims_bearing ~20K
```

Conclusion: el riesgo de tamano no esta en los snapshots de runs, sino en los
artefactos de experimentos CWRU. Por tanto, no conviene borrar
`codigo/reports/runs/` como primera medida; conviene podar artefactos pesados
solo cuando ya haya resultados persistidos.

## Runs canonicas actuales

Snapshots ligeros a conservar:

```text
cwru_iforest_threshold_v1_baseline_threshold_099
cwru_iforest_threshold_v1_conservative_threshold_100
cwru-agentic-window-qwen-fase3_win_1024_ov_50_win_1024_ov_50
cwru-agentic-window-qwen-fase3_win_2048_ov_50_selected
cwru-agentic-window-qwen-fase3_win_4096_ov_50_win_4096_ov_50
cwru-agentic-model-qwen-fase3_iforest_thr_0_99_selected
cwru-agentic-model-qwen-fase3_pca_nc_0_95_pca_reconstruction_error
cwru-agentic-model-qwen-fase3_iforest_thr_1_0_iforest_conservative_threshold
nasa-ims-qwen-smoke-fase3-qwen
nasa-ims-synth-agentic-qwen-fase3
nasa-ims-synth-agentic-qwen-fase3-retry-attempt-01
nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02
```

Runs candidatas a borrar cuando se quiera limpiar ruido historico:

```text
run-fase2-wrapper-check
run-fase2-persistence-check
nasa-ims-qwen-smoke-fase3
```

Estas candidatas son utiles como comprobaciones operativas, pero no son la
evidencia principal de Fase 3.

## Regla practica

No borrar un directorio de run canonico si no hay una tabla o documento que
resuma sus resultados. Si el problema es espacio, priorizar la poda de tensores
y modelos regenerables antes que la poda de snapshots.

## Benchmark sintetico NASA IMS

La run `nasa-ims-synth-agentic-qwen-fase3` queda marcada como canonica para
Fase 3 porque aporta metricas supervisadas no perfectas sobre un dataset
sintetico controlado:

```text
snapshot: codigo/reports/runs/nasa-ims-synth-agentic-qwen-fase3/
raw sintetico: ~4.4M
processed: ~452K
tensors: ~396K
models: ~628K
```

No se borra por ahora porque su coste de almacenamiento es bajo y su valor
documental es alto: contiene decisiones reales de Qwen y una evaluacion
rechazada por metricas insuficientes.

## Reintentos agenticos NASA IMS sintetico

Los snapshots `nasa-ims-synth-agentic-qwen-fase3-retry-attempt-01` y
`nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02` quedan tambien como
evidencia canonica de Fase 3. No son runs exitosas: son evidencia de
aprendizaje y parada segura.

Resumen:

| Run | Precision | Recall | F1 | FPR | Estado |
| --- | ---: | ---: | ---: | ---: | --- |
| Base | 0.9130 | 0.6000 | 0.7241 | 0.1429 | rechazado |
| Retry 1 | 0.8846 | 0.6571 | 0.7541 | 0.2143 | rechazado |
| Retry 2 | 0.7143 | 1.0000 | 0.8333 | 1.0000 | stop por limite |

El segundo reintento demuestra por que no basta con maximizar recall: el agente
recupero todas las anomalias, pero a costa de marcar todos los normales de test
como anomalos. Se conserva porque documenta un caso defendible de aprendizaje
agentico, intercambio tecnico y control contra bucles infinitos.

Cada reintento conserva tambien una auditoria de razonamiento:

```text
reasoning_postmortem.json
reasoning_postmortem.md
human_reasoning_review_request.json
human_reasoning_review_request.md
human_reasoning_review_template.json
```

Estos ficheros son ligeros y tienen valor documental alto. Permiten que una
persona etiquete el razonamiento como correcto, parcialmente correcto,
incorrecto, inseguro o insuficiente. Esa etiqueta queda separada de las metricas
de la run y puede usarse despues como memoria supervisada para RAG o ejemplos
de comportamiento.

Inventario tras estos reintentos:

```text
codigo/reports/runs              ~972K
codigo/reports/nasa_ims_bearing  ~160K
codigo/models/nasa_ims_bearing   ~1.9M
```

Sigue sin ser necesario borrar snapshots de `reports/runs`: el peso de los
reintentos es bajo y su valor documental es alto.

Nota de trazabilidad: los snapshots NASA se han normalizado para reemplazar
nombres heredados `cwru_*` por identificadores comunes de artefacto. Esto no
convierte runs antiguas en nuevos experimentos; solo mejora la legibilidad de
los artefactos persistidos.
