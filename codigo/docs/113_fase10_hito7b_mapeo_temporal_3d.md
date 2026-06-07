# Fase 10 - Hito 10.7B - Mapeo temporal 3D

Fecha: 2026-06-06.

Estado: implementado y verificado con build local.

## Objetivo

Conectar la sala 3D industrial del Hito 10.7A con puntos temporales reales de
`TemporalRunSeries`, manteniendo la escena como capa opcional de inspeccion y
sin sustituir la sala 2D.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Representar en 3D puntos temporales reales de una run usando health_state,
risk_index, first_alert_x, first_persistent_alert_x y failure_x.
```

Piezas revisadas y reutilizadas:

- `codigo/frontend/src/components/visualization/IndustrialScene3D.tsx`;
- `codigo/frontend/src/lib/visualization3d.ts`;
- `TemporalRunSeries`;
- `TemporalSeriesPoint`;
- `RunVisualizationData`;
- `codigo/docs/112_fase10_hito7a_sala_3d_base_threejs.md`.

Decision:

```text
extend
```

Motivo: la escena 3D ya existia como pieza aislada. La mejora correcta era
extender su capa de transformacion y geometria, no crear otro componente ni
otro contrato.

## Cambios implementados

En `visualization3d.ts`:

- se exportan colores canonicos por `HealthState`;
- se crea `buildIndustrialTimeline(run)`;
- se limita la representacion a un maximo de 180 puntos visibles para evitar
  una escena pesada;
- cada punto temporal se transforma a:
  - posicion X normalizada en el dominio temporal real;
  - color por `point.health_state`;
  - altura por `point.risk_index` si existe;
  - fallback de altura por `point.score_ratio` si falta `risk_index`;
  - referencia a `window_id`, score, riesgo y salud en `userData`.
- se crean marcadores 3D desde:
  - `first_alert_x`;
  - `first_persistent_alert_x`;
  - `failure_x`.

En `IndustrialScene3D.tsx`:

- se anade una linea temporal 3D delante de la maquina;
- se renderizan barras por ventana temporal real;
- se renderizan postes para primer pico, aviso sostenido y fallo historico;
- se amplia el overlay con ventanas visibles/totales, alertas y numero de
  marcadores;
- se anade leyenda compacta para estados y marcadores.

En `styles.css`:

- se ajusta el overlay 3D a seis metricas compactas;
- se anade leyenda responsive para colores de estado y marcadores temporales.

## Criterios metodologicos

- La UI no inventa diagnosticos: los colores salen de `health_state`, la altura
  sale de `risk_index` o `score_ratio`, y los eventos salen de campos
  persistidos del contrato temporal.
- La sala 2D sigue siendo el modo por defecto.
- La escena 3D se mantiene cargada bajo demanda.
- No se crea ningun endpoint ni contrato nuevo.
- No se cambia la semantica de comparacion ni de metricas.

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

- el bundle principal sigue alrededor de `281 kB`;
- el chunk `IndustrialScene3D` queda separado y se carga solo al activar `3D`;
- Vite mantiene el aviso de chunk grande por `three`, esperado para este hito.

Limitacion de verificacion visual:

- no hay Playwright, Chromium ni Google Chrome disponibles en el entorno local;
- la validacion visual automatizada con screenshot/canvas-pixel queda pendiente;
- la verificacion manual esperada es abrir `http://127.0.0.1:5173/`, ir a
  `Visualizacion`, seleccionar una run con serie temporal y activar `3D`.

## Siguiente paso

Hito 10.7C deberia anadir interaccion ligera sobre la escena: seleccion o hover
de puntos temporales, lectura compacta de la ventana seleccionada y posible
enfoque automatico de marcadores clave, sin convertir el 3D en el unico modo de
analisis.
