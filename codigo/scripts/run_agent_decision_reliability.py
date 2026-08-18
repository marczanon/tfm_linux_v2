"""Planifica o ejecuta la bateria agentica decision-only.

Sin ``--execute`` el comando solo imprime el plan y nunca construye un cliente
Ollama. La ejecucion real requiere una autorizacion explicita y sigue sin
invocar datasets, memoria, LangGraph o ejecutores deterministas.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from codigo.app.services.agent_reliability import (
    DEFAULT_AGENT_RELIABILITY_OUTPUT_DIR,
    AgentReliabilityModelConfig,
    build_observed_ollama_client_factory,
    default_agent_reliability_plan,
    run_agent_reliability_plan,
    write_agent_reliability_artifacts,
)
from codigo.app.services.llm import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_NUM_CTX,
    DEFAULT_OLLAMA_NUM_PREDICT,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    plan = default_agent_reliability_plan(
        plan_id=args.plan_id,
        repetitions=args.repetitions,
        minimum_first_pass_rate=args.minimum_first_pass_rate,
    )
    if args.scenario_ids:
        requested = set(args.scenario_ids)
        available = {scenario.scenario_id for scenario in plan.scenarios}
        unknown = sorted(requested - available)
        if unknown:
            raise SystemExit(
                "scenario_id desconocido: " + ", ".join(unknown)
            )
        plan = plan.model_copy(
            update={
                "scenarios": [
                    scenario
                    for scenario in plan.scenarios
                    if scenario.scenario_id in requested
                ]
            }
        )
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "plan_only",
                    "will_execute_ollama": False,
                    "plan": plan.model_dump(mode="json"),
                    "observation_count": len(plan.scenarios) * plan.repetitions,
                    "entrypoints": sorted(
                        {scenario.entrypoint for scenario in plan.scenarios}
                    ),
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    model_config = AgentReliabilityModelConfig(
        provider="ollama",
        model=args.model,
        think=args.think,
        timeout_seconds=args.timeout_seconds,
        num_ctx=args.num_ctx,
        num_predict=args.num_predict,
        max_json_repair_attempts=args.max_json_repair_attempts,
        transport_trace_scope="physical_ollama_chat",
    )
    result = run_agent_reliability_plan(
        plan,
        client_factory=build_observed_ollama_client_factory(
            model_config,
            host=args.ollama_host,
        ),
        model_config=model_config,
    )
    artifacts = write_agent_reliability_artifacts(
        result,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "mode": "execute",
                "gate": result.gate.model_dump(mode="json"),
                "summary": result.summary.model_dump(mode="json"),
                "artifacts": artifacts.model_dump(mode="json"),
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0 if result.gate.verdict == "passed" else 2


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita decisiones LLM sin ejecutar el pipeline de datos."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Imprime el plan sin llamar a Ollama (comportamiento por defecto).",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Autoriza explicitamente las llamadas decision-only a Ollama.",
    )
    parser.add_argument("--plan-id", default="agent-reliability-qwen35-v1")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--scenario-id",
        action="append",
        dest="scenario_ids",
        default=[],
        help=(
            "Limita la bateria a un scenario_id; puede repetirse. "
            "Sin esta opcion se ejecuta el pack completo."
        ),
    )
    parser.add_argument("--minimum-first-pass-rate", type=float, default=0.90)
    parser.add_argument("--model", default=DEFAULT_OLLAMA_CHAT_MODEL)
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_OLLAMA_NUM_CTX)
    parser.add_argument("--num-predict", type=int, default=DEFAULT_OLLAMA_NUM_PREDICT)
    parser.add_argument("--max-json-repair-attempts", type=int, default=1)
    parser.add_argument(
        "--output-root",
        default=DEFAULT_AGENT_RELIABILITY_OUTPUT_DIR.as_posix(),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
