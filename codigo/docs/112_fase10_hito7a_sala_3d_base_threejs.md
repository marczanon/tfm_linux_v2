# Fase 10 - Hito 10.7A - Sala 3D base con Three.js

Fecha: 2026-06-06.

Estado: implementado y verificado con build local.

## Objetivo

Abrir el Hito 10.7 con una escena 3D industrial aislada y opcional dentro de
`Visualizacion`, sin sustituir la sala 2D cerrada en el Hito 10.6.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Anadir una sala 3D industrial opcional en Visualizacion usando datos ya
expuestos por RunVisualizationData y TemporalRunSeries.
```

Busquedas y piezas revisadas:

- `codigo/frontend/package.json`;
- `codigo/frontend/src/components/visualization/VisualizationView.tsx`;
- `codigo/frontend/src/styles.css`;
- `codigo/frontend/src/types.ts`;
- `codigo/docs/96_fase10_hoja_ruta_frontend_cockpit_visual.md`;
- `codigo/docs/111_fase10_cierre_hito6_visualizacion_2d_avanzada.md`;
- busqueda de `three`, `3D`, `WebGL`, `canvas`, `VisualizationView`.

Pieza canonica reutilizada:

- `VisualizationView` sigue siendo el propietario de la visualizacion;
- `RunVisualizationData` y `TemporalRunSeries` siguen siendo la fuente de datos;
- la sala 2D permanece como modo por defecto.

Decision:

```text
new + reuse
```

Motivo: no existia ningun componente 3D previo que ampliar. Se crea una pieza
nueva con frontera clara, pero se integra en la vista canonica y consume los
contratos existentes.

## Cambios implementados

Dependencias frontend:

- se anade `three`;
- se anade `@types/three` como dependencia de desarrollo para mantener
  TypeScript estricto.

Nuevas piezas:

- `codigo/frontend/src/components/visualization/IndustrialScene3D.tsx`;
- `codigo/frontend/src/components/visualization/WebGLFallback.tsx`;
- `codigo/frontend/src/lib/visualization3d.ts`.

Integracion:

- `VisualizationView` incorpora un selector compacto `2D`/`3D` en la tarjeta
  temporal;
- el modo `2D` sigue siendo el valor por defecto;
- la escena `IndustrialScene3D` se carga con `React.lazy` y `Suspense`, por lo
  que `three` no engorda el bundle principal;
- si WebGL no esta disponible, se muestra un fallback limpio;
- la escena incluye una sala industrial minima con suelo, pared, maquina
  rotativa, beacon de estado, camara orbit limitada y boton de recentrado.

## Criterios metodologicos

- La escena 3D no sustituye la lectura 2D.
- No se inventan metricas ni diagnosticos.
- En este subhito solo se usa el estado actual de la run para colorear la
  senal visual basica.
- El mapeo temporal 3D de puntos, bandas, alertas y fallo queda para un subhito
  posterior.
- No se crea ningun endpoint ni contrato nuevo.

## Verificacion

Comando ejecutado:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Observacion de bundle:

- el bundle principal queda alrededor de `281 kB`;
- la escena 3D queda separada en un chunk `IndustrialScene3D` cargado bajo
  demanda;
- Vite avisa de que el chunk 3D supera 500 kB minificado, esperado por
  `three`, pero no afecta al modo 2D inicial.

Comprobaciones locales:

- `GET http://127.0.0.1:5173/` responde desde Vite;
- `GET http://127.0.0.1:5173/api/health` responde mediante proxy;
- `GET /api/runs/fase9-hito4b-ae-readiness-lite-001_autoencoder_dense/visualization`
  responde con serie temporal, Health Index y estado actual.

Limitacion de verificacion visual:

- no hay Playwright, Chromium ni Google Chrome disponibles en el entorno local;
- por tanto, no se pudo ejecutar screenshot/canvas-pixel automatizado en este
  subhito sin introducir una instalacion adicional pesada;
- queda pendiente una verificacion visual con navegador al activar el modo `3D`
  en `http://127.0.0.1:5173/`.

## Siguiente paso

Hito 10.7B deberia convertir la escena base en una representacion temporal:
mapear puntos reales de `TemporalRunSeries` a bandas o marcadores 3D, usando
colores por `health_state`, intensidad por riesgo y marcadores para primer
aviso, aviso sostenido y fallo historico.
