"""Fabricas de agentes LLM para ejecuciones controladas."""

from __future__ import annotations

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.agents.report_writer import (
    decide_report_action,
    decide_report_revision_action,
)
from codigo.app.agents.report_verifier import decide_report_verification_action
from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.agents.supervisor import decide_supervisor_action
from codigo.app.graph.pipeline import PipelineAgents
from codigo.app.services.llm import JSONLLMClient, get_default_json_llm_client


def build_ollama_pipeline_agents(
    llm_client: JSONLLMClient | None = None,
) -> PipelineAgents:
    """Crea agentes que fuerzan llamadas JSON al cliente Ollama configurado."""

    client = llm_client or get_default_json_llm_client()
    return PipelineAgents(
        supervisor=lambda state: decide_supervisor_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        cleaner=lambda state: decide_cleaning_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        structurer=lambda state, memory_context=None: decide_structuring_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        ),
        modeler=lambda state: decide_modeling_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        evaluator=lambda state, memory_context=None: decide_evaluation_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        ),
        report_writer=lambda state: decide_report_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        report_reviser=lambda state, verification, **kwargs: decide_report_revision_action(
            state,
            verification,
            llm_client=client,
            use_llm=True,
            **kwargs,
        ),
        report_verifier=lambda state: decide_report_verification_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
    )
