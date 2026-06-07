# Fase 10 - Hito 10.10 - Informe, evidencia y artefactos

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Ordenar la lectura final de una run sin devolver la aplicacion a una experiencia
textual pesada. El informe, la auditoria, el debate y los artefactos siguen
disponibles, pero pasan a una lectura de evidencia bajo demanda.

## Alcance

Incluido:

- centro de evidencia visible para la run foco en `Nueva run`;
- señales compactas de informe, auditoria, debate, evidence pack y artefactos;
- documentos completos plegados por defecto;
- rutas tecnicas de artefactos plegadas dentro de cada artefacto;
- reutilizacion del mismo centro de evidencia en el detalle del registro;
- acceso corto desde `Agentes` a la evidencia de la run seleccionada.

No incluido:

- cambios backend;
- nuevos endpoints;
- descarga o renderizado nuevo de evidence pack;
- nuevas metricas;
- cambios en la generacion de informes.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Reordenar informe, auditoria, debate y artefactos como evidencia compacta y
auditable desde el frontend.
```

Piezas revisadas:

- `RunDetailView`;
- `ReportPanels`;
- `ReportDocument`;
- `RunHistoryPanel`;
- `PipelineDashboard`;
- `CockpitView`;
- `AgentObservabilityView`;
- endpoints existentes `/runs/{run_id}/report`,
  `/runs/{run_id}/audit-report`, `/runs/{run_id}/report-debate` y
  `/runs/{run_id}/artifacts`.

Decision:

```text
adapt
```

Motivo: los datos, documentos y renderizadores ya existian. El hito necesitaba
reordenar la experiencia y crear una composicion reutilizable, no ampliar
contratos.

## Implementacion

Archivos modificados:

- `codigo/frontend/src/components/reports/ReportPanels.tsx`;
- `codigo/frontend/src/components/runs/RunDetailView.tsx`;
- `codigo/frontend/src/components/pipeline/PipelineDashboard.tsx`;
- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/styles.css`.

Cambios:

- se crea `RunEvidenceHub` como centro de evidencia reutilizable;
- `PipelineDashboard` muestra la evidencia de la run foco como panel visible;
- `RunDetailView` reutiliza `RunEvidenceHub` dentro del registro de runs;
- `ReportPanels` conserva los paneles anteriores, pero el flujo principal usa
  una composicion mas compacta;
- `Agentes` añade un boton pequeno `Evidencia` cuando hay snapshot seleccionado;
- artefactos muestran nombre, tipo, productor y descripcion breve;
- la ruta tecnica queda oculta en un desplegable por artefacto.

## Verificacion

Build:

```text
cd codigo/frontend
npm run build
```

Resultado: correcto.

Nota: Vite mantiene el aviso de chunk WebGL/Three.js mayor de `500 kB`; no
bloquea el hito porque las escenas 3D siguen cargadas de forma diferida.

Servicios locales:

- `GET /health`: correcto;
- `GET /runs`: correcto, con runs persistidas disponibles.

Run usada:

```text
fase9-agentic-modeler-readiness-lite-llm-guardrail-001
```

Playwright:

- desktop `1440x1100`;
- movil `390x920`;
- entrada desde `Cockpit -> Abrir evidencia`;
- panel `RunEvidenceHub` presente;
- 5 señales de evidencia;
- 4 documentos/desplegables principales;
- informe desplegable visible al abrirlo;
- enlace `Evidencia` visible desde `Agentes`;
- sin errores de consola;
- sin respuestas fallidas;
- sin overflow horizontal.

Capturas:

```text
/tmp/tfm-frontend-1010-desktop-evidence-ready.png
/tmp/tfm-frontend-1010-desktop-evidence-open.png
/tmp/tfm-frontend-1010-mobile-evidence-ready.png
/tmp/tfm-frontend-1010-mobile-evidence-open.png
```

## Cierre

El Hito `10.10` queda cerrado. La app ya permite pasar de una run o del cockpit
a una lectura auditada sin mostrar informe, auditoria, debate ni rutas tecnicas
como texto visible por defecto.

Siguiente paso recomendado: `10.11 - Pulido, QA visual y Docker`.
