# Datasets crudos

Datos descargados el 2026-05-06 para el caso de uso inicial del TFM:
deteccion de anomalias en rodamientos de motores electricos mediante senales de
vibracion.

## CWRU Bearing Dataset

- Ruta local: `codigo/data/raw/cwru_bearing/mat/`
- Fuente oficial:
  - https://engineering.case.edu/bearingdatacenter/normal-baseline-data
  - https://engineering.case.edu/bearingdatacenter/12k-drive-end-bearing-fault-data
- Alcance descargado: datos normales de referencia y fallos de rodamiento a
  12 kHz en el drive-end.
- Formato original: ficheros MATLAB `.mat`.
- Conteo local verificado: 64 ficheros `.mat`.
- Uso previsto: dataset principal del MVP para entrenar y evaluar deteccion de
  anomalias frente a operacion normal.

## NASA IMS Bearing Dataset

- Ruta local: `codigo/data/raw/nasa_ims_bearing/4.+Bearings.zip`
- Fuente oficial:
  - https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip
- Pagina de referencia NASA PCoE:
  - https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- Tamano verificado: 1,075,597,174 bytes.
- Integridad basica: `unzip -t` sin errores.
- Uso previsto: dataset de validacion/extension para degradacion run-to-failure
  en rodamientos. Se conserva comprimido hasta que el MVP local necesite
  incorporarlo.

## Criterio de uso

- Mantener estos datos como artefactos crudos e inmutables.
- Guardar conversiones, perfiles y subconjuntos en `codigo/data/interim/`,
  `codigo/data/processed/` o `codigo/data/tensors/`.
- No cargar datasets completos en el estado de LangGraph; usar rutas,
  metadatos y resumenes estadisticos.
