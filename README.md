# Sistema multiagente para mantenimiento predictivo industrial

Plataforma experimental de monitorización continua que combina modelos de lenguaje locales con técnicas de análisis de datos y detección de anomalías. Su objetivo es convertir datos de sensores industriales en hipótesis, decisiones y evidencias comprensibles para apoyar el mantenimiento predictivo.

## Enfoque

Los agentes especializados colaboran mediante un flujo orquestado con LangGraph. Cada decisión se valida con contratos Pydantic antes de incorporarse al estado compartido, mientras que las operaciones sobre los datos son ejecutadas por módulos Python deterministas y reproducibles. De este modo, los modelos pueden razonar y adaptarse sin ejecutar código arbitrario ni actuar fuera de los límites establecidos.

La plataforma incluye:

- Procesamiento end-to-end de datos industriales.
- Monitorización temporal y detección de anomalías.
- Revisión multiagente con modelos locales mediante Ollama.
- Registro de hipótesis, decisiones y evidencias causales.
- API FastAPI y panel web interactivo.
- Persistencia de ejecuciones y visualización de su evolución.

## Tecnologías principales

Python, LangGraph, Pydantic, FastAPI, React, scikit-learn, PyTorch, Ollama y Docker.

## Estructura

```text
codigo/app/       Backend, agentes, contratos y ejecutores
codigo/frontend/  Interfaz web
codigo/tests/     Pruebas automatizadas
codigo/docker/    Despliegue local reproducible
codigo/docs/      Documentación técnica
```

## Ejecución con Docker

Desde la raíz del repositorio:

```bash
docker compose --env-file codigo/docker/.env.example \
  -f codigo/docker/docker-compose.yml up --build
```

La interfaz queda disponible en `http://localhost:5173` y la API en `http://localhost:8010`. Para utilizar los agentes locales se requiere una instancia de Ollama accesible desde el backend.
