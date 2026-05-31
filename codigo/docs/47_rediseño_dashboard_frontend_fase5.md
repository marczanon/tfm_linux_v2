# Rediseño dashboard frontend Fase 5

Fecha: 2026-05-31.

## Objetivo

Reestructurar la aplicacion web del TFM Pipeline para que deje de parecer una
interfaz tecnica provisional y pase a comportarse como un dashboard local de
operacion profesional, manteniendo intactos los contratos API y la metodologia
del pipeline.

## Inventario previo

Busquedas realizadas:

```text
rg -n "^function |^const |^type |^interface |export default function|return \\(" codigo/frontend/src/App.tsx
wc -l codigo/frontend/src/App.tsx codigo/frontend/src/styles.css codigo/frontend/src/types.ts codigo/frontend/src/api.ts
```

Piezas encontradas:

- `codigo/frontend/src/App.tsx` concentraba estado, orquestacion de llamadas,
  formulario, preflight, ejecucion, runs, agentes, memoria y visualizacion.
- Existian componentes internos para vistas parciales, pero la pantalla
  principal seguia mezclando responsabilidades visuales.
- `codigo/frontend/src/api.ts` y `types.ts` ya cubrian todos los contratos
  publicos necesarios.
- No era necesario crear endpoints ni modificar backend.

Decision: `extend`.

Motivo: la funcionalidad ya existia. La mejora pendiente era reorganizar el
frontend en una jerarquia visual y de componentes mas propia de una herramienta
SaaS/MLOps.

Impacto en compatibilidad: no cambia ningun contrato con FastAPI, no cambia
`POST /runs`, no cambia lectura de runs, memoria, jobs, visualizaciones ni
Ollama.

## Implementacion

Se reestructura la pantalla alrededor de componentes de producto:

- `AppShell`: marco principal con sidebar, navegacion y area de trabajo.
- `StatusHeader`: cabecera operacional sencilla.
- `HealthSummary`: resumen de API, LLM, adaptadores y runs.
- `PipelineDashboard`: vista principal de operacion.
- `PipelineConfig`: configuracion de run, modos, revision humana, LLM y fases.
- `PreflightPanel`: plan devuelto por `POST /runs` en dry-run.
- `ExecutionStatus`: job local y snapshot al completar.
- `RunHistoryPanel`: filtros, tabla de runs, comparacion y detalle.
- `PanelTitle` y estados reutilizables para reducir ruido visual.

Cambios de UX:

- navegacion principal pasa a un sidebar estable;
- estado global queda separado del flujo operativo;
- configuracion de run queda en una columna propia;
- preflight y ejecucion se separan de la lista historica;
- opciones avanzadas como `adapter_id`, `policy_id` y fases manuales quedan
  agrupadas en un bloque plegable;
- rutas canonicas largas del plan quedan en detalle tecnico plegable;
- tablas, metricas, artefactos y payloads tecnicos conservan su informacion,
  pero con menos competencia visual.

Pulido final:

- la UI deja de mostrar rutas locales de entrada, snapshots, informes,
  artefactos y fuentes de visualizacion;
- el panel `Nueva run` deja de ser pegajoso y permanece en el flujo normal de
  la pagina al hacer scroll.

## Verificacion

Comandos ejecutados:

```text
npm run build
curl -sS http://127.0.0.1:5173/
curl -sS http://127.0.0.1:5173/api/llm/status
```

Resultado:

- TypeScript y Vite compilan correctamente;
- el frontend local responde en `http://127.0.0.1:5173/`;
- el proxy local hacia FastAPI responde para `GET /api/llm/status`;
- no se han modificado endpoints ni contratos backend.

## Limitaciones

- No se anaden dependencias visuales ni librerias de componentes.
- No se instala Playwright; la verificacion automatizada visual queda pendiente
  para un hito posterior de pruebas end-to-end frontend.
