# Documentacion tecnica

Esta carpeta recoge decisiones de diseno e implementacion de la aplicacion. La
memoria academica se mantiene separada en `memoria/`; aqui se documentan
contratos, rutas, artefactos y criterios tecnicos que deben guiar el codigo.

Documentos iniciales:

- `01_diseno_pipeline_datos.md`: diseno del flujo de datos para el MVP con
  CWRU Bearing Dataset y extension futura con NASA IMS.
- `02_diseno_state_langgraph.md`: contrato del estado global usado por el grafo
  y validado mediante Pydantic.
- `03_diseno_contratos_pydantic.md`: contratos Pydantic para datasets,
  decisiones de agentes y resultados de ejecutores.
- `04_ejecutor_manifest_cwru.md`: implementacion y verificacion del ejecutor
  determinista que genera `manifest.csv`.
