# Fase 10 - Hito 10.5C - Memoria agentica en retrieval y uso

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Mejorar la lectura de memoria dentro de la pestana `Agentes`, haciendo mas
claro que recuerdos se recuperan, cuales se usan, cuales se ignoran y que
senales de calidad observable acompanian al retrieval.

El alcance queda limitado a frontend. No se cambian backend, contratos API,
esquemas Pydantic, grafo, agentes ni ejecutores.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mostrar mejor el uso de memoria en Agentes reutilizando AgentMemoryPanel y los
eventos runtime ya persistidos.
```

Pieza canonica reutilizada:

- `codigo/frontend/src/components/memory/AgentMemoryPanel.tsx`;
- `AgentRuntimeEvent`;
- `memory_usage_summary`;
- `memory_record_uses`;
- `retrieved_memory_record_ids`;
- `cited_memory_record_ids`;
- `ignored_memory_record_ids`;
- items de retrieval con rank, similitud, rol, veredicto y origen.

Decision:

```text
adapt
```

Motivo: la memoria ya tenia propietario modular dentro del frontend. Crear otra
vista o tocar `App.tsx` habria duplicado estado y debilitado la separacion
conseguida en Hito 10.2.

## Cambios implementados

En `AgentMemoryPanel`:

- se anade un resumen compacto `Retrieval actual`;
- se separan conteos de recuerdos recuperados, usados, ignorados y excluidos;
- se corrige la lectura de recuerdos usados para no confundir IDs recuperados
  con IDs citados;
- se muestra `memory_usage_summary` cuando existe;
- se muestran declaraciones `memory_record_uses` como chips de apoyo,
  adaptacion, contradiccion o ignorado;
- cada item recuperado muestra rank, similitud y una senal observable derivada
  de campos ya persistidos: similitud, rol, veredicto, outcome, fuente y tags;
- la lista de recuerdos distingue `usado`, `ignorado` y `excluido`.

En `styles.css`:

- se anaden estilos compactos para el resumen de retrieval;
- se anaden chips de calidad observable y uso;
- se conserva responsive, incluyendo el nuevo grid en movil.

## Criterios metodologicos

La UI no inventa diagnosticos nuevos:

- no crea metricas persistidas;
- no llama a endpoints nuevos;
- no decide por el agente;
- no modifica memoria;
- solo resume campos ya presentes en eventos runtime y registros de memoria.

Las senales de calidad son lectura visual frontend de evidencia existente, no un
quality gate backend ni una politica nueva.

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

## Siguiente paso

Hito 10.5 queda suficientemente reforzado para pasar al siguiente bloque
visual. El siguiente paso natural es Hito 10.6: mejorar `Visualizacion` 2D con
lectura temporal mas clara de score, Health Index, bandas, onset, alerta
persistente y comparacion, manteniendo frontend-only salvo que falte un dato
imprescindible en contratos existentes.
