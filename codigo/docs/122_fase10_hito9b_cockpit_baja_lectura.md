# Fase 10 - Hito 10.9B - Cockpit funcional de baja lectura

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Rediseñar `CockpitView` para que funcione mas como consola operacional y menos
como panel textual. La primera lectura debe ser estado, riesgo, accion y run
foco, dejando la evidencia y detalles profundos accesibles sin invadir la vista.

## Alcance

Incluido:

- command deck superior con estado dominante;
- medidor compacto de Health Index y riesgo;
- readiness chips para API, LLM, datos, run y evidencia;
- señales principales mas compactas;
- tarjetas de run, salud, recomendacion, evidencia e historial con mas color
  semantico;
- tipografia de display mediante stack local/fallback;
- traduccion compacta de acciones comunes (`continue` -> `Continuar`).

No incluido:

- cambios backend;
- nuevos datos;
- eliminacion de evidencia;
- rediseño completo de `Nueva run`, `Agentes` o `Visualizacion`.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Hacer que el cockpit comunique estado y accion con baja lectura reutilizando
datos y componentes existentes.
```

Piezas reutilizadas:

- `CockpitView`;
- `StatusPill`;
- `RunVisualizationData`;
- `AgentOperationalRecommendation`;
- `RunIndexEntry`;
- `styles.css`;
- tokens visuales definidos en `10.9A`.

Decision:

```text
adapt + extend
```

Motivo: el cockpit ya recibia todos los datos necesarios. El hito reorganiza la
jerarquia visual y reduce texto visible, sin crear nuevas fuentes ni contratos.

## Cambios implementados

En `CockpitView.tsx`:

- se sustituye el hero anterior por `cockpit-command`;
- el estado dominante sale de `temporalRun.current_health_state` cuando existe;
- se añade medidor de `HI` y `Riesgo`;
- se añaden readiness chips:
  - API;
  - LLM;
  - Datos;
  - Run;
  - Evidencia;
- las acciones se reducen a `Nueva run`, `Ejecutar` y refresh LLM;
- la recomendacion agentica muestra una accion compacta en lugar de parrafo;
- se añade `compactActionText(...)` para traducir acciones persistidas comunes
  sin modificar los datos de origen;
- `MetricTile` y `CockpitSignal` aceptan tonos visuales.

En `styles.css`:

- se añaden stacks tipograficos:
  - `--font-ui`;
  - `--font-display`;
  - `--font-mono`;
- se añade `cockpit-command` con estado, medidor y readiness;
- se añaden estilos por estado `critical`, `warning`, `watch`;
- se refuerzan tarjetas, señales y metricas con color semantico;
- se mantiene responsive sin scroll horizontal.

## Verificacion

Comandos:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Playwright desktop:

- viewport `1440x1100`;
- `cockpit-command` visible;
- señales principales: `6`;
- tarjetas cockpit: `5`;
- accion agentica compacta: `Continuar`;
- scroll horizontal: no;
- errores de consola: `[]`.

Playwright movil:

- viewport `390x920`;
- `cockpit-command` visible;
- accion agentica compacta: `Continuar`;
- scroll horizontal:

```text
innerWidth: 390
docScrollWidth: 390
bodyScrollWidth: 390
```

- errores de consola: `[]`.

Capturas:

```text
/tmp/tfm-frontend-cockpit-109b-desktop-v2.png
/tmp/tfm-frontend-cockpit-109b-mobile-v2.png
```

Pixel check sobre capturas:

```text
desktop: 1440x1303, 20069 colores, OK
mobile: 780x7332, 30445 colores, OK
```

## Limitacion

El cockpit ya reduce lectura y gana identidad, pero las pestañas funcionales
restantes todavia conservan demasiado texto visible. Eso queda para `10.9C`.

## Siguiente paso

Hito 10.9C:

- aplicar la politica de texto a `Nueva run`, `Visualizacion`, `Agentes` y runs;
- ocultar detalles largos por defecto;
- mantener datos bajo demanda;
- validar que no se pierde trazabilidad.
