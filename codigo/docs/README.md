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
- `05_ejecutor_profile_cwru.md`: implementacion y verificacion del perfilador
  determinista que genera `profile.json`.
- `06_ejecutor_limpieza_cwru.md`: implementacion y verificacion del ejecutor
  determinista que genera senales limpias.
- `07_ejecutor_estructuracion_cwru.md`: implementacion y verificacion del
  ejecutor que genera ventanas, features y particiones reproducibles.
- `08_ejecutor_modelado_cwru.md`: implementacion y verificacion del primer
  modelo base de deteccion de anomalias con Isolation Forest.
- `09_ejecutor_evaluacion_cwru.md`: implementacion y verificacion del ejecutor
  de metricas sobre predicciones.
- `10_adaptadores_entrada.md`: frontera ligera para leer distintos formatos de
  senal sin acoplar los ejecutores al tipo de fichero.
