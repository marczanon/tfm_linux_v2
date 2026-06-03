# Fase 7 - Hito 1: integracion frontend del informe final

Fecha: 2026-05-31.

## Capacidad buscada

Encajar el informe final como documento principal de cierre de una run, no como
un artefacto tecnico mas dentro del historial.

## Inventario previo anti-duplicacion

Se revisaron las piezas existentes antes de tocar el frontend:

- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/styles.css`;
- `codigo/frontend/src/types.ts`;
- `codigo/frontend/src/api.ts`;
- endpoint existente `GET /runs/{run_id}/report`.

Decision:

```text
extend
```

Motivo: el frontend ya cargaba el informe con `getRunReport(...)` y lo mostraba
en `RunDetailView`. No hacia falta endpoint nuevo ni componente externo; habia
que recolocarlo y renderizarlo mejor.

## Cambios implementados

- El informe pasa a mostrarse como seccion principal `Informe final` dentro del
  detalle de una run.
- La evidencia tecnica queda debajo, separada visualmente, como soporte del
  informe y no como elemento equivalente.
- La previsualizacion deja de ser un bloque `pre` monoespaciado y se renderiza
  como documento:
  - titulo;
  - metadatos clave;
  - secciones;
  - parrafos;
  - hallazgos;
  - recomendaciones;
  - listas de metricas.
- La UI filtra bloques de fuentes tecnicas y rutas locales para respetar la
  decision de no mostrar rutas de ficheros en la pagina web.
- `RunSnapshot` admite los nuevos campos opcionales de evidence pack sin
  exponerlos todavia en la pantalla.

## Fronteras mantenidas

- No se han creado endpoints nuevos.
- No se lee ningun fichero local desde el navegador.
- No se cambia el contrato de ejecucion.
- No se duplica el informe: se usa el Markdown servido por la API existente.
- No se muestran rutas locales en la UI.

## Verificacion

Prueba ejecutada:

```text
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

## Estado

La run seleccionada presenta ahora el informe final como cierre analitico y la
evidencia tecnica como soporte secundario. El siguiente paso funcional podria
ser exponer una vista de auditoria para el evidence pack, separada del informe
final para no mezclar documento de analista y trazabilidad tecnica.

Actualizacion posterior: esa vista separada se implementa como informe
determinista de auditoria de ejecucion en
`codigo/docs/58_fase7_hito2_informe_auditoria_ejecucion.md`.
