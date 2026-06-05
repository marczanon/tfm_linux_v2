# Fase 10 - Hito 2C: modularizacion agentes, memoria y constantes

Fecha: 2026-06-05.

Estado: implementado.

Hoja de ruta: `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`.

Subhitos previos:

- `codigo/docs/98_fase10_hito2a_shell_common_frontend.md`;
- `codigo/docs/99_fase10_hito2b_modularizacion_runs_reports_visualizacion.md`.

## Objetivo

Continuar la modularizacion del frontend separando tres responsabilidades que
seguian dentro de `App.tsx`:

- constantes de datasets/pipeline;
- runtime/traduccion de agentes;
- cockpit de memoria agentica.

La meta es que `App.tsx` avance hacia un papel de orquestador de estado y
vistas, no de propietario de todos los componentes.

## Arquitectura aplicada

La estructura frontend queda orientada por dominio:

```text
codigo/frontend/src/
  components/
    agents/
    common/
    memory/
    reports/
    runs/
    shell/
    visualization/
  constants/
  lib/
  types/
```

Decisiones:

- `components/*`: UI por dominio.
- `constants/*`: defaults y listas estables.
- `lib/*`: traducciones, formatos y extraccion segura de payloads.
- `types/*`: tipos UI que no son contratos backend.
- `types.ts`: se mantiene como espejo de contratos backend.
- `api.ts`: se mantiene como frontera unica con FastAPI.

## Cambios implementados

### Constantes

Nuevos archivos:

```text
codigo/frontend/src/constants/datasets.ts
codigo/frontend/src/constants/pipeline.ts
```

Contienen:

- `FALLBACK_ADAPTER`;
- `DATASET_REQUEST_DEFAULTS`;
- `PIPELINE_STAGES`;
- `HUMAN_REVIEW_POINTS`;
- `STAGE_LABELS`;
- `RUN_STAGE_FILTERS`;
- `DEFAULT_RUN_FILTERS`.

### Agentes

Nuevo archivo:

```text
codigo/frontend/src/components/agents/AgentObservabilityView.tsx
```

Contiene:

- `AgentObservabilityView`;
- mapa/oficina de agentes;
- detalle de evento runtime;
- traduccion humana de eventos;
- conversacion agentica.

### Memoria

Nuevo archivo:

```text
codigo/frontend/src/components/memory/AgentMemoryPanel.tsx
```

Contiene:

- cockpit de memoria;
- ciclo candidato/indexado/recuperado/usado/auditado;
- distribuciones de rol y origen;
- flujo runtime de recuperacion;
- lista y detalle de recuerdos;
- acciones de curacion.

### Helpers

Nuevos/extendidos:

```text
codigo/frontend/src/lib/agentRuntime.ts
codigo/frontend/src/lib/memoryRecords.ts
codigo/frontend/src/lib/formatters.ts
```

Contienen:

- perfiles de agentes;
- owner de evento runtime;
- traducciones humanas;
- extraccion segura de payloads;
- labels de memoria;
- `formatDate`;
- `formatEventTime`.

## Resultado estructural

Evolucion de `App.tsx`:

```text
Antes de Fase 10:           5126 lineas
Tras Hito 10.2A:            4895 lineas
Tras Hito 10.2B:            3511 lineas
Tras Hito 10.2C:            2051 lineas
```

Lectura:

```text
App.tsx aun es grande, pero ya no contiene shell, informes, detalle de run,
visualizacion, agentes, memoria ni constantes principales.
```

## No cambios deliberados

- No se modifica `api.ts`.
- No se modifica `types.ts`.
- No se modifica `styles.css`.
- No se anaden dependencias.
- No se cambia la vista por defecto.
- No se introduce todavia `CockpitView`.
- No se alteran endpoints, contratos ni logica backend.
- No se cambia la logica de memoria, curacion, polling ni runtime.

## Verificacion

Comando ejecutado:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
build correcto
```

Tambien se ejecuto:

```text
git diff --check
```

Resultado:

```text
sin errores de whitespace
```

## Siguiente corte recomendado

Para terminar la modularizacion previa al cockpit:

```text
extraer Pipeline/Runs/Jobs/Preflight de App.tsx
```

Destino recomendado:

```text
components/pipeline/
components/jobs/
components/plans/
components/datasets/
components/runs/
components/llm/
```

Despues de ese corte, `App.tsx` deberia quedar suficientemente pequeno para
introducir `CockpitView` como panel principal con menos riesgo.
