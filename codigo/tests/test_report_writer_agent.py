import unittest

from codigo.app.agents.report_writer import (
    decide_report_action,
    decide_report_revision_action,
)
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import (
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.schemas.state import EvaluationResult, MetricsReport, ProjectContext
from codigo.tests.agent_hypothesis_fixtures import with_test_agent_hypothesis


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        if isinstance(self.payload, list):
            index = min(self.calls - 1, len(self.payload) - 1)
            return with_test_agent_hypothesis(self.payload[index])
        return with_test_agent_hypothesis(self.payload)


def _state():
    state_dict = create_initial_cwru_state(
        thread_id="cwru-report-test",
        run_id="run-report-001",
    )
    state_dict["manifest_path"] = "codigo/data/interim/cwru_bearing/manifest.csv"
    state_dict["profile_path"] = "codigo/data/interim/cwru_bearing/profile.json"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        recall=1.0,
        f1_score=0.99,
        false_positive_rate=0.05,
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion aprobada.",
        next_action="continue",
        limitations=["Validacion limitada a CWRU."],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        {
            "name": "metrics",
            "artifact_type": "metrics",
            "path": "codigo/reports/cwru_bearing/evaluation/metrics.json",
            "producer": "evaluator",
        }
    ]
    return validate_state(state_dict)


class ReportWriterAgentTests(unittest.TestCase):
    def test_deterministic_report_writer_returns_default_markdown_plan(self):
        decision = decide_report_action(_state())

        self.assertEqual(decision.agent_name, "report_writer")
        self.assertEqual(decision.output_format, "markdown")
        self.assertEqual(
            decision.output_path,
            "codigo/reports/cwru_bearing/run-report-001/final_report.md",
        )
        self.assertIn(
            "Metricas y evaluacion",
            [section.title for section in decision.sections],
        )
        summary_section = next(
            section for section in decision.sections if section.title == "Resumen ejecutivo"
        )
        self.assertIsNotNone(summary_section.body)
        self.assertTrue(summary_section.key_findings)
        self.assertTrue(summary_section.recommendations)
        self.assertEqual(decision.generation_trace.origin, "deterministic")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertEqual(decision.hypothesis.kind, "report_grounding")
        self.assertTrue(decision.hypothesis.expected_observation)

    def test_deterministic_report_writer_prioritizes_temporal_metrics(self):
        decision = decide_report_action(_temporal_state())

        metrics_section = next(
            section
            for section in decision.sections
            if section.title == "Metricas y evaluacion"
        )
        body = metrics_section.body or ""
        findings = " ".join(metrics_section.key_findings)
        self.assertIn("run-to-failure", body)
        self.assertIn("lead time", body)
        self.assertIn("run_to_failure_degradation", findings)
        self.assertIn("F1 auxiliar", findings)
        self.assertIn("ground truth oficial", body)
        context_section = next(
            section
            for section in decision.sections
            if section.title == "Contexto y datos"
        )
        context_findings = " ".join(context_section.key_findings)
        self.assertIn("Procedencia de datos: unknown", context_findings)
        self.assertIn("no pueden presentarse como datos oficiales", context_findings)

    def test_official_v2_report_uses_scoped_operational_semantics(self):
        decision = decide_report_action(_official_v2_temporal_state())

        narrative = " ".join(
            [
                decision.rationale,
                *[
                    text
                    for section in decision.sections
                    for text in [
                        section.body or "",
                        *section.key_findings,
                        *section.recommendations,
                    ]
                ],
            ]
        ).lower()
        self.assertIn("aceptada por controles operativos internos", narrative)
        self.assertIn("alerta algoritmica persistente", narrative)
        self.assertIn("final registrado", narrative)
        self.assertIn("pre-monitorizacion", narrative)
        self.assertIn("ground truth", narrative)
        self.assertNotIn("onset confirmado", narrative)
        self.assertNotIn("lead time persistente hasta fallo", narrative)
        self.assertNotIn("aprobada por el evaluador", narrative)

    def test_official_v2_report_rejects_llm_physical_claims(self):
        state = _official_v2_temporal_state()
        payload = decide_report_action(state).model_dump(mode="json")
        summary = next(
            section
            for section in payload["sections"]
            if section["title"] == "Resumen ejecutivo"
        )
        summary["body"] = "Ejecucion aprobada: onset confirmado y fallo detectado."
        client = FakeLLMClient(payload)

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 2)
        self.assertIn("Guardrail correction", decision.rationale)
        narrative = " ".join(
            section.body or "" for section in decision.sections
        ).lower()
        self.assertNotIn("onset confirmado", narrative)
        self.assertNotIn("fallo detectado", narrative)
        self.assertIn("final registrado", client.messages[-1].content)

    def test_official_v2_report_accepts_explicitly_negated_diagnosis(self):
        state = _official_v2_temporal_state()
        payload = decide_report_action(state).model_dump(mode="json")
        limitations = next(
            section
            for section in payload["sections"]
            if section["title"] == "Limitaciones y siguientes pasos"
        )
        limitations["body"] = (
            "El resultado es un control algoritmico interno; no es un "
            "diagnostico validado ni demuestra un inicio fisico."
        )
        client = FakeLLMClient(payload)

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertIn(
            "no es un diagnostico validado",
            " ".join(section.body or "" for section in decision.sections).lower(),
        )

    def test_official_v2_report_repairs_physical_degradation_and_lead_time_aliases(self):
        state = _official_v2_temporal_state()
        invalid_payload = decide_report_action(state).model_dump(mode="json")
        metrics = next(
            section
            for section in invalid_payload["sections"]
            if section["title"] == "Metricas y evaluacion"
        )
        metrics["body"] = (
            "Degradacion confirmada antes del fallo al 100%. "
            "Lead time medio hasta fallo: 201600.56 segundos."
        )
        valid_payload = decide_report_action(state).model_dump(mode="json")
        client = FakeLLMClient([invalid_payload, valid_payload])

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        narrative = " ".join(
            text
            for section in decision.sections
            for text in [
                section.body or "",
                *section.key_findings,
                *section.recommendations,
            ]
        ).lower()
        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertNotIn("degradacion confirmada", narrative)
        self.assertNotIn("lead time", narrative)
        self.assertIn("no cites las etiquetas rechazadas", client.messages[-1].content)

    def test_official_v2_report_accepts_negated_physical_metric_aliases(self):
        state = _official_v2_temporal_state()
        payload = decide_report_action(state).model_dump(mode="json")
        limitations = next(
            section
            for section in payload["sections"]
            if section["title"] == "Limitaciones y siguientes pasos"
        )
        limitations["body"] = (
            "No se afirma una degradacion confirmada antes del fallo. "
            "No se reporta lead time medio hasta fallo; solo tiempo "
            "retrospectivo hasta el final registrado."
        )
        client = FakeLLMClient(payload)

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn(
            "usa exclusivamente 'trayectorias con alerta algoritmica persistente'",
            client.messages[1].content,
        )

    def test_official_v2_prompt_projects_legacy_metrics_to_reporting_vocabulary(self):
        state = _official_v2_temporal_state()
        payload = decide_report_action(state).model_dump(mode="json")
        client = FakeLLMClient(payload)

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        prompt = "\n".join(message.content for message in client.messages).lower()
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertNotIn(
            "degradation_confirmed_degradation_before_failure_rate",
            prompt,
        )
        self.assertNotIn(
            "degradation_mean_persistent_lead_time_to_failure",
            prompt,
        )
        self.assertNotIn("degradacion confirmada", prompt)
        self.assertNotIn("lead time", prompt)
        self.assertIn(
            "proporcion_trayectorias_con_alerta_algoritmica_persistente",
            prompt,
        )
        self.assertIn(
            "tiempo_retrospectivo_medio_hasta_final_registrado_segundos",
            prompt,
        )
        self.assertIn("201600.5632", prompt)

    def test_official_v2_report_accepts_raw_negative_limitation_without_rewriting(self):
        state = _official_v2_temporal_state()
        payload = decide_report_action(state).model_dump(mode="json")
        limitations = next(
            section
            for section in payload["sections"]
            if section["title"] == "Limitaciones y siguientes pasos"
        )
        raw_limitation = (
            "Las afirmaciones de degradacion confirmada no son validas sin "
            "evidencia fisica externa."
        )
        limitations["body"] = raw_limitation
        client = FakeLLMClient(payload)

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        persisted_limitation = next(
            section.body
            for section in decision.sections
            if section.title == "Limitaciones y siguientes pasos"
        )
        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertEqual(persisted_limitation, raw_limitation)

    def test_llm_report_decision_is_used_when_valid(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_writer",
                "decision_id": "run-report-001:report_writer:001",
                "rationale": "Use a concise technical report structure.",
                "confidence": 0.91,
                "generation_trace": {"forged": True},
                "output_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                "output_format": "markdown",
                "sections": [
                    {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Contexto y datos", "include_metrics": False, "include_artifacts": False, "source_paths": ["codigo/data/interim/cwru_bearing/manifest.csv"]},
                    {"title": "Configuraciones del pipeline", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Metricas y evaluacion", "include_metrics": True, "include_artifacts": False, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Artefactos generados", "include_metrics": False, "include_artifacts": True, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Limitaciones y siguientes pasos", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                ],
            }
        )

        decision = decide_report_action(_state(), llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.91)
        self.assertIn("ReportDecision", str(client.json_schema))
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertEqual(decision.generation_trace.validation_status, "validated")

    def test_llm_report_accepts_accented_equivalent_section_titles(self):
        state = _state()
        payload = decide_report_action(state).model_dump(mode="json")
        metrics_section = next(
            section
            for section in payload["sections"]
            if section["title"] == "Metricas y evaluacion"
        )
        metrics_section["title"] = "Métricas y evaluación"
        client = FakeLLMClient(payload)

        decision = decide_report_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn(
            "Metricas y evaluacion",
            [section.title for section in decision.sections],
        )
        self.assertEqual(len(decision.sections), len(payload["sections"]))

    def test_llm_report_decision_repairs_contract_violation_before_fallback(self):
        valid_sections = [
            {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []},
            {"title": "Contexto y datos", "include_metrics": False, "include_artifacts": False, "source_paths": ["codigo/data/interim/cwru_bearing/manifest.csv"]},
            {"title": "Configuraciones del pipeline", "include_metrics": False, "include_artifacts": False, "source_paths": []},
            {"title": "Metricas y evaluacion", "include_metrics": True, "include_artifacts": False, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
            {"title": "Artefactos generados", "include_metrics": False, "include_artifacts": True, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
            {"title": "Limitaciones y siguientes pasos", "include_metrics": False, "include_artifacts": False, "source_paths": []},
        ]
        client = FakeLLMClient(
            [
                {
                    "agent_name": "report_writer",
                    "decision_id": "run-report-001:report_writer:001",
                    "rationale": "Invalid output path.",
                    "confidence": 0.99,
                    "output_path": "/tmp/report.md",
                    "output_format": "markdown",
                    "sections": valid_sections,
                },
                {
                    "agent_name": "report_writer",
                    "decision_id": "run-report-001:report_writer:001",
                    "rationale": "Corrected after contract feedback.",
                    "confidence": 0.87,
                    "output_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                    "output_format": "markdown",
                    "sections": valid_sections,
                },
            ]
        )

        decision = decide_report_action(_state(), llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.confidence, 0.87)
        self.assertNotIn("Fallback after LLM failure", decision.rationale)
        self.assertIn("contrato del redactor", client.messages[-1].content)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")

    def test_invalid_llm_report_decision_falls_back(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_writer",
                "decision_id": "run-report-001:report_writer:001",
                "rationale": "Invalid output path.",
                "confidence": 0.99,
                "output_path": "/tmp/report.md",
                "output_format": "markdown",
                "sections": [
                    {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []}
                ],
            }
        )

        decision = decide_report_action(_state(), llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 2)
        self.assertEqual(
            decision.output_path,
            "codigo/reports/cwru_bearing/run-report-001/final_report.md",
        )
        self.assertLessEqual(decision.confidence, 0.82)
        self.assertIn("Guardrail correction", decision.rationale)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        self.assertEqual(
            decision.generation_trace.fallback_from_attempt_id,
            "run-report-001:report_writer:001:attempt:002",
        )

    def test_deterministic_revision_accepts_verifier_issues(self):
        verification = _verification_decision()

        decision = decide_report_revision_action(_state(), verification)

        self.assertEqual(decision.agent_name, "report_writer")
        self.assertEqual(decision.revision_round, 1)
        self.assertEqual(decision.verifier_decision_id, verification.decision_id)
        self.assertIn("industrial_claim", decision.accepted_issue_ids)
        self.assertEqual(decision.hypothesis.kind, "revision_effectiveness")
        self.assertEqual(decision.generation_trace.origin, "deterministic")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        limitation_section = next(
            section
            for section in decision.sections
            if section.title == "Limitaciones y siguientes pasos"
        )
        self.assertIn("verificacion agentica", limitation_section.body or "")

    def test_valid_llm_revision_is_used(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_writer",
                "decision_id": "run-report-001:report_writer_revision:001",
                "rationale": "Apply verifier correction.",
                "confidence": 0.86,
                "generation_trace": {"forged": True},
                "revision_round": 1,
                "revision_of_decision_id": "run-report-001:report_writer:001",
                "verifier_decision_id": "run-report-001:report_verifier:001",
                "output_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                "output_format": "markdown",
                "sections": [
                    {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Contexto y datos", "include_metrics": False, "include_artifacts": False, "source_paths": ["codigo/data/interim/cwru_bearing/manifest.csv"]},
                    {"title": "Configuraciones del pipeline", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Metricas y evaluacion", "include_metrics": True, "include_artifacts": False, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Artefactos generados", "include_metrics": False, "include_artifacts": True, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Limitaciones y siguientes pasos", "body": "Validacion limitada a CWRU.", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                ],
                "accepted_issue_ids": ["industrial_claim"],
                "rejected_issue_ids": [],
                "rejection_rationales": {},
                "changes_summary": ["Reformula validacion industrial como validacion local."],
                "evidence_refs": ["report:final_report"],
            }
        )

        decision = decide_report_revision_action(
            _state(),
            _verification_decision(),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.86)
        self.assertIn("ReportRevisionDecision", str(client.json_schema))
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)

    def test_llm_revision_repair_records_second_attempt(self):
        verification = _verification_decision()
        valid_payload = decide_report_revision_action(
            _state(),
            verification,
        ).model_dump(mode="json")
        valid_payload["rationale"] = "Corrected after contract feedback."
        valid_payload["confidence"] = 0.85
        valid_payload["generation_trace"] = {"forged": True}
        invalid_payload = dict(valid_payload)
        invalid_payload["output_path"] = "/tmp/report.md"
        client = FakeLLMClient([invalid_payload, valid_payload])

        decision = decide_report_revision_action(
            _state(),
            verification,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.confidence, 0.85)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")

    def test_invalid_llm_revision_tracks_fallback_after_second_attempt(self):
        verification = _verification_decision()
        invalid_payload = decide_report_revision_action(
            _state(),
            verification,
        ).model_dump(mode="json")
        invalid_payload["output_path"] = "/tmp/report.md"
        client = FakeLLMClient(invalid_payload)

        decision = decide_report_revision_action(
            _state(),
            verification,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        self.assertEqual(
            decision.generation_trace.fallback_from_attempt_id,
            "run-report-001:report_writer_revision:001:attempt:002",
        )

def _verification_decision() -> ReportVerificationDecision:
    return ReportVerificationDecision(
        decision_id="run-report-001:report_verifier:001",
        rationale="Verify report factuality.",
        confidence=0.82,
        report_path="codigo/reports/cwru_bearing/run-report-001/final_report.md",
        verification_status="needs_revision",
        summary="One claim needs correction.",
        unsupported_claims=[
            ReportVerificationIssue(
                issue_id="industrial_claim",
                issue_type="unsupported_claim",
                severity="high",
                claim_text="Validacion industrial completa.",
                reason="La evidencia solo cubre una ejecucion local del TFM.",
                evidence_refs=["report:final_report"],
                suggested_fix="Reformular como validacion local reproducible.",
            )
        ],
        required_corrections=["Reformular la validacion industrial."],
        evidence_refs=["report:final_report"],
    )


def _temporal_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-report-test",
        run_id="run-report-nasa-temporal-001",
    )
    state_dict["project_context"] = ProjectContext(
        dataset="nasa_ims_bearing",
        machine_type="rotating_machinery",
        signal_type="vibration",
        objective="run_to_failure_degradation",
        target_sample_rate_hz=20000,
        main_channel="channel_1",
        label_mode="degradation",
        supervision_profile="run_to_failure_degradation",
        label_granularity="proxy_temporal",
        label_source="temporal_proxy",
    ).model_dump(mode="json")
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/nasa_ims_bearing/evaluation/metrics.json",
        recall=0.42,
        f1_score=0.50,
        false_positive_rate=0.40,
        extra={
            "degradation_available": True,
            "degradation_n_runs": 1,
            "degradation_mean_lead_time_to_failure": 300.0,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.8,
        },
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion run-to-failure aprobada.",
        next_action="continue",
        limitations=["Etiquetas proxy temporales; no oficiales por ventana."],
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _official_v2_temporal_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-report-official-v2-test",
        run_id="run-report-nasa-official-v2-001",
    )
    state_dict["project_context"] = ProjectContext(
        dataset="nasa_ims_bearing",
        machine_type="rotating_machinery",
        signal_type="vibration",
        objective="run_to_failure_degradation",
        target_sample_rate_hz=20000,
        main_channel="channel_1",
        label_mode="degradation",
        supervision_profile="run_to_failure_degradation",
        label_granularity="event",
        label_source="none",
        data_provenance="official",
        provenance_detection_method="official_dataset_provenance",
    ).model_dump(mode="json")
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/nasa_ims_bearing/evaluation/metrics.json",
        extra={
            "degradation_available": True,
            "degradation_n_runs": 1,
            "degradation_confirmed_degradation_before_failure_rate": 1.0,
            "degradation_mean_persistent_lead_time_to_failure": 201600.5632,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.7937,
            "degradation_mean_health_index_drop": 91.1146,
            "degradation_mean_health_monotonicity": 0.5293,
            "degradation_mean_health_robustness": 0.9820,
        },
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Aceptada por controles operativos internos.",
        next_action="continue",
        limitations=[
            "No hay ground truth fisico por snapshot.",
            "El intervalo retrospectivo termina en el final registrado.",
        ],
    ).model_dump(mode="json")
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
