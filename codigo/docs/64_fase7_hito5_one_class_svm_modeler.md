# Fase 7 - Hito 5.3: One-Class SVM para el modeler

Fecha: 2026-06-01.

## Objetivo

Ampliar el espacio de decision del `modeler` con una nueva familia no
supervisada soportada por el ejecutor determinista: `one_class_svm`.

La mejora busca dar mas protagonismo real al agente sin desplazar el problema
hacia un ajuste repetitivo de `threshold_quantile`. `one_class_svm` permite
comparar una frontera no lineal de margen frente a:

- `isolation_forest`;
- `pca_reconstruction_error`.

XGBoost queda deliberadamente fuera de esta implementacion. Se considera una
familia supervisada interesante para datasets con etiquetas y politica
metodologica explicita, pero no debe mezclarse con los detectores no
supervisados actuales.

## Inventario previo anti-duplicacion

Piezas revisadas:

- `codigo/app/executors/modeling.py`;
- `codigo/app/agents/modeler.py`;
- `codigo/app/schemas/state.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/services/experiment_protocol.py`;
- `codigo/tests/test_modeling_executor.py`;
- `codigo/tests/test_modeler_agent.py`;
- `codigo/tests/test_experiment_protocol.py`;
- `requirements.txt`.

Decision:

```text
extend
```

Motivo: `ModelingConfig` ya admitia historicamente `one_class_svm`, pero el
ejecutor lo rechazaba por no estar implementado. La responsabilidad canonica de
entrenar y puntuar modelos vive en `modeling.py`, y la responsabilidad de
validar decisiones del LLM vive en `modeler.py`.

## Implementacion

En `codigo/app/executors/modeling.py` se incorpora:

- `DEFAULT_OCSVM_MODELING_CONFIG`;
- `SKLEARN_OCSVM_PARAMS`;
- validacion de hiperparametros;
- entrenamiento con `sklearn.svm.OneClassSVM`;
- escalado con `StandardScaler`;
- `anomaly_score = -decision_function(...)`, manteniendo la convencion del
  proyecto: valores mas altos significan mayor anomalia.

El umbral se calcula igual que en las demas familias soportadas: a partir del
cuantil de scores en validacion si existe, o en train como fallback.

## Hiperparametros soportados

`one_class_svm` acepta:

```text
kernel: linear | poly | rbf | sigmoid
nu: (0, 1]
gamma: scale | auto | float positivo
degree: entero entre 2 y 6
coef0: [-10, 10]
shrinking: bool
tol: [1e-6, 1e-1]
cache_size: [50, 1000]
max_iter: -1 o entero entre 100 y 100000
threshold_quantile: (0, 1]
```

El agente no puede usar otros parametros ni valores fuera de rango.

## Cambios en el modeler

`codigo/app/agents/modeler.py` ahora considera soportados:

```text
isolation_forest
one_class_svm
pca_reconstruction_error
```

El prompt y la plantilla JSON incluyen `one_class_svm` como alternativa
comparable. Tambien se incorpora como candidato en reintentos para evitar que
la deliberacion quede limitada a umbrales.

## Fronteras metodologicas

Esta mejora no:

- introduce dependencias nuevas;
- anade XGBoost ni modelos supervisados;
- permite entrenamiento con codigo generado por el LLM;
- modifica la evaluacion ni las metricas;
- cambia la politica de NASA IMS.

`one_class_svm` sigue siendo un detector no supervisado entrenado con ventanas
normales del split `train`.

## Validacion

Validaciones enfocadas ejecutadas:

```text
python -m py_compile codigo/app/executors/modeling.py codigo/app/agents/modeler.py
python -m unittest codigo.tests.test_modeling_executor codigo.tests.test_modeler_agent codigo.tests.test_agent_decisions_schema codigo.tests.test_experiment_protocol
```

Resultado: `one_class_svm` entrena, persiste modelo, predicciones y resumen; el
agente modelador puede seleccionarlo con hiperparametros acotados; los modelos
no implementados, como `local_outlier_factor`, siguen rechazandose.
