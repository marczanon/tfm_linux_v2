# Agente estructurador LLM

## Objetivo

Introducir el agente LLM que decide la estructuracion temporal del dataset. El
agente devuelve una `StructuringDecision`; no genera ventanas, features ni
tensores directamente. La ejecucion real sigue delegada en:

```text
codigo/app/executors/structuring.py
```

## Que decide

El agente estructurador propone:

- tamano de ventana;
- solapamiento;
- canal principal;
- frecuencia objetivo;
- modo de etiquetas;
- lista de features temporales;
- rutas esperadas de features, tensores y splits.
- alternativas comparables en `comparison_candidates`, cuando el agente quiera
  proponer un experimento de sensibilidad.

Para el MVP CWRU y la Fase 3, las validaciones restringen la decision a valores
soportados por el ejecutor:

```text
window_size in {1024, 2048, 4096}
overlap in {0.25, 0.5, 0.75}
main_channel = DE_time
target_sample_rate_hz = 12000
label_mode = binary_anomaly
```

## Implementacion

Archivos principales:

```text
codigo/app/agents/structurer.py
codigo/app/graph/pipeline.py
codigo/tests/test_structurer_agent.py
```

El agente expone:

```text
decide_structuring_action(state, llm_client=None, use_llm=None) -> StructuringDecision
```

Rutas disponibles:

- `decide_structuring_action_with_llm(...)`: usa un cliente LLM JSON.
- `decide_structuring_action_deterministic(...)`: fallback reproducible.

## Encaje en el grafo

La fase `structuring` queda dividida en decision y ejecucion:

```text
supervisor
-> structuring_agent
-> supervisor
-> structuring_executor
```

El supervisor enruta a `structuring_agent` si `structuring_config` todavia es
`null`. El agente escribe la configuracion en el estado y despues el supervisor
autoriza el ejecutor determinista.

## Verificacion LLM local

Modelo usado:

```text
qwen3.5:4b
```

Resultado validado:

```text
window_size = 2048
overlap = 0.5
main_channel = DE_time
target_sample_rate_hz = 12000
label_mode = binary_anomaly
features = mean, std, rms, min, max, peak_to_peak, skewness,
           kurtosis, crest_factor, energy
confidence = 0.9
```

La respuesta valido correctamente contra `StructuringDecision` y
`StructuringConfig`.

## Alternativas agenticas

En Fase 3 se ha ampliado el contrato con `comparison_candidates`. El agente
puede devolver varias configuraciones candidatas con su justificacion. El
protocolo experimental solo las ejecuta si vienen del agente; no crea una
segunda alternativa por reglas internas.

Validacion real:

```text
python -m codigo.scripts.run_cwru_agentic_window_comparison \
  --model qwen3.5:4b \
  --plan-id cwru-agentic-window-qwen-fase3
```

Qwen propuso 2048/50%, 1024/50% y 4096/50%. La configuracion de 1024 muestras
obtuvo el mejor F1 y la menor tasa de falsos positivos sobre CWRU.

## Tests

Comando:

```bash
conda run -n tfm_v2 python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 69 tests
OK
```

Prueba integrada del pipeline:

```text
current_stage = completed
messages = 17
supervisor_decisions = 9
cleaner_decisions = 1
structurer_decisions = 1
f1_score = 0.9995747093847462
```

## Siguiente paso

El agente modelador queda documentado en `16_agente_modelador_llm.md` y el
agente evaluador en `17_agente_evaluador_llm.md`. El siguiente avance tecnico
sera introducir el agente redactor para generar el informe final.
