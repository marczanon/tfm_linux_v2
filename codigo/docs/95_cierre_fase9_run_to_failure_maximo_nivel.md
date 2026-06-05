# Cierre Fase 9 - run-to-failure al maximo nivel

Fecha: 2026-06-05.

## Estado

Fase 9 cerrada operativamente.

El perfil `run_to_failure_degradation` queda como caso PHM agentico local
defendible: compara familias de modelo, interpreta trayectorias temporales,
calcula Health Indicator, usa readiness para modelos avanzados y conserva el
protagonismo de Qwen/LLM dentro de contratos estrictos.

## Alcance cerrado

- Suite canonica run-to-failure con PCA, Isolation Forest, One-Class SVM y
  `autoencoder_dense`.
- Politica temporal versionada con onset confirmado, aviso sostenido, lead
  persistente, falsas alarmas nominales, episodios y picos aislados.
- Health Indicator avanzado con caida, monotonicidad, robustez, volatilidad,
  tendencia y score agregado.
- Herramienta `temporal_model_readiness_assessor` para condicionar
  autoencoder/RUL a evidencia suficiente.
- Autoencoder PyTorch denso sobre `windows_features.csv`, con hiperparametros
  cerrados, CPU por defecto, `.pt`, scaler, curva de entrenamiento,
  predicciones y summary.
- Integracion agentica: el `modeler` solo puede proponer autoencoder si cita
  readiness y refs `readiness:*`.
- Smoke real de autoencoder y suite ligera con readiness.
- Run agentica real con Qwen donde el `modeler` elige PCA y conserva
  autoencoder como candidato comparable, no como decision forzada.
- Hardening de salidas LLM: reparacion JSON, reintento de contrato,
  `Guardrail correction` para violaciones de contrato y fallback tecnico solo
  para proveedor/JSON irrecuperable.
- Memoria LaTeX actualizada en metodologia, implementacion, experimentos,
  resultados y conclusiones.

## Evidencia principal

- `fase9-hito4-autoencoder-smoke-001`: valida integracion tecnica de
  `autoencoder_dense` y artefactos PyTorch, aunque readiness queda bloqueado por
  pocas ventanas nominales.
- `fase9-hito4b-ae-readiness-lite-001`: suite ligera con readiness en
  `caution`; autoencoder queda aprobado y lidera metricas de Health Indicator.
- `fase9-agentic-modeler-readiness-lite-llm-guardrail-001`: run libre con Qwen,
  `completed`, `approved = true`; el `modeler` elige PCA y deja autoencoder
  como candidato comparable.

Metricas principales de la run agentica final:

- onset confirmado: `1.0000`;
- lead persistente: `7200.7680`;
- FAR nominal: `0.0952`;
- HI drop: `76.4453`;
- HI monotonicidad: `0.5214`;
- tendencia Spearman: `0.7967`;
- F1 proxy: `0.8602`.

## Verificacion

```bash
python -m unittest discover codigo/tests
```

Resultado:

```text
Ran 352 tests
OK (skipped=1)
```

Tambien se ejecuto `git diff --check` sin incidencias.

## Fuera de alcance

- RUL experimental completo con incertidumbre.
- RUL industrial validado.
- LSTM autoencoder.
- Autoencoder sobre senal cruda.
- Segundo dataset run-to-failure real.
- Smoke Docker final tras incorporar PyTorch.

Estos puntos quedan como trabajo futuro y no bloquean el cierre de Fase 9.

## Decision de cierre

Se da por terminada la Fase 9. A partir de este punto, las nuevas sesiones no
deben seguir puliendo esta linea salvo decision explicita. El siguiente bloque
logico seria uno de estos:

- RUL experimental con incertidumbre;
- segundo dataset run-to-failure;
- visualizacion PHM avanzada;
- rebuild/validacion Docker con PyTorch;
- cierre academico final de memoria y demo.
