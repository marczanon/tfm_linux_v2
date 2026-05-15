import json
import unittest

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    CleaningDecision,
    ReportDecision,
    ReportSection,
    SupervisorDecision,
)
from codigo.app.schemas.state import CleaningConfig


class AgentDecisionSchemaTests(unittest.TestCase):
    def test_supervisor_decision_requires_next_node_when_not_terminal(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                decision_id="d-001",
                rationale="Continue with manifest generation.",
                confidence=0.9,
                current_stage="initialized",
                next_stage="dataset_manifest",
                next_node=None,
                requires_human_review=False,
                stop_reason=None,
            )

    def test_supervisor_terminal_decision_requires_stop_reason(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                decision_id="d-002",
                rationale="Stop after completion.",
                confidence=0.9,
                current_stage="reporting",
                next_stage="completed",
                next_node=None,
                requires_human_review=False,
                stop_reason=None,
            )

    def test_cleaning_decision_is_json_serializable(self):
        decision = CleaningDecision(
            decision_id="clean-001",
            rationale="Remove non-finite values and keep raw scale.",
            confidence=0.8,
            cleaning_config=CleaningConfig(
                strategy_id="cwru_cleaning_v1",
                remove_non_finite=True,
                resample_to_hz=12000,
                normalization="none",
                audit_log_path=None,
            ),
            expected_artifact_path="codigo/data/processed/cwru_bearing/clean_signals",
        )

        payload = decision.model_dump(mode="json")

        self.assertEqual(payload["agent_name"], "cleaner")
        json.dumps(payload)

    def test_agent_decision_rejects_extra_fields(self):
        with self.assertRaises(ValidationError):
            CleaningDecision(
                decision_id="clean-002",
                rationale="No extras allowed.",
                confidence=0.8,
                cleaning_config=CleaningConfig(),
                expected_artifact_path="codigo/data/processed/cwru_bearing/clean_signals",
                arbitrary_text="surprise",
            )

    def test_report_decision_requires_at_least_one_section(self):
        with self.assertRaises(ValidationError):
            ReportDecision(
                decision_id="report-001",
                rationale="Create report.",
                confidence=0.7,
                output_path="codigo/reports/cwru_bearing/report.md",
                output_format="markdown",
                sections=[],
            )

    def test_report_decision_accepts_structured_sections(self):
        decision = ReportDecision(
            decision_id="report-002",
            rationale="Create report with metrics.",
            confidence=0.7,
            output_path="codigo/reports/cwru_bearing/report.md",
            output_format="markdown",
            sections=[
                ReportSection(
                    title="Metricas",
                    include_metrics=True,
                    include_artifacts=True,
                    source_paths=["codigo/data/tensors/cwru_bearing/windows_features.csv"],
                )
            ],
        )

        self.assertEqual(decision.sections[0].title, "Metricas")


if __name__ == "__main__":
    unittest.main()
