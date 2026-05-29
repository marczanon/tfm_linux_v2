# Human Review operativa en frontend

Fecha: 2026-05-29.

## Objetivo

Hacer operativo el Hito 6 de Fase 5: permitir que la interfaz muestre las
razones de revision humana devueltas por el backend y envie una aprobacion
simple cuando una ejecucion la requiere.

## Inventario previo

Busquedas realizadas:

```text
rg -n "human_review|HumanReview|HumanApproval|human_approval|human_review_reasons" codigo/app codigo/tests codigo/docs codigo/frontend
rg -n "Planificar|Ejecutar|ApiRunRequest|ApiRunResponse|human_review" codigo/frontend/src
```

Piezas encontradas:

- `codigo/app/services/human_review.py`: puerta canonica de revision humana.
- `HumanReviewSettings` y `HumanApproval`: contratos existentes de aprobacion.
- `ApiRunRequest`: ya acepta `human_review` y `human_approval`.
- `ApiRunResponse`: ya devuelve `human_review_reasons` y `human_approval`.
- `codigo/tests/test_api_runs.py`: ya cubre modo `passive`, bloqueo
  `required` sin aprobacion y persistencia de aprobacion en snapshot.

Decision: `extend`.

Motivo: no era necesario crear otro contrato ni endpoint. La capacidad pendiente
era que la UI usara los campos existentes y respetara el bloqueo logico del
backend antes de lanzar una ejecucion.

Impacto en compatibilidad: no cambia rutas FastAPI ni contratos Python. La
interfaz envia los mismos campos que ya aceptaba `POST /runs`.

## Implementacion

El frontend anade controles de Human Review en el formulario de ejecucion:

- selector de modo `off`, `passive` o `required`;
- campo de revisor;
- seleccion de puntos explicitamente marcados para revision:
  `modeling`, `evaluation` y `memory`;
- visualizacion de `human_review_reasons` tras el dry-run;
- formulario de `human_approval` con aprobacion explicita, motivo y marca
  temporal cuando el modo `required` devuelve razones de bloqueo.

La accion `Planificar` sigue usando `POST /runs` con `dry_run=true`. Si el
backend devuelve una puerta de revision humana, la UI la conserva y muestra sus
razones. La accion `Ejecutar` solo se habilita cuando el plan es ejecutable y,
si el modo es `required`, existe una aprobacion explicita.

En modo `passive`, las razones se muestran como aviso operativo, pero no
bloquean la ejecucion. En modo `required`, la UI evita lanzar la run sin
aprobacion y el backend conserva la misma validacion como fuente de verdad.

## Criterios de aceptacion

- Una run en modo `passive` muestra razones de revision sin bloquear.
- Una run en modo `required` no se ejecuta desde la UI hasta marcar aprobacion.
- La aprobacion viaja en `human_approval` hacia `POST /runs`.
- La persistencia de aprobacion en snapshot sigue cubierta por los tests API
  existentes.

## Verificacion

Comandos ejecutados:

```text
npm run build
python -m unittest codigo.tests.test_api_runs codigo.tests.test_api_memory codigo.tests.test_graph_pipeline codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
pdflatex -interaction=nonstopmode main.tex
```

Resultado obtenido:

- `npm run build` compila correctamente;
- la suite backend relevante ejecuta 49 tests correctamente;
- `pdflatex` recompila `memoria/main.pdf` correctamente;
- el frontend local responde en `http://127.0.0.1:5173/`;
- el proxy local responde en `http://127.0.0.1:5173/api/health`.

## Limitaciones

- La revision humana sigue siendo local y ligera; no implementa usuarios,
  firmas ni auditoria multiusuario.
- La UI no aprueba automaticamente a partir de memoria agentica.
- La aprobacion se introduce en el formulario de run y se persiste en el
  snapshot final; no existe todavia una bandeja independiente de aprobaciones.
