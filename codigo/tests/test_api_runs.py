import json
import tempfile
import time
import unittest
import asyncio
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import httpx

from codigo.app.api import create_app
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    HumanApproval,
    MetricsReport,
    StateMessage,
)
from codigo.app.services.run_persistence import save_run_snapshot
from codigo.app.services.llm import LLMProviderStatus


class APIRunsTests(unittest.TestCase):
    def test_health_returns_configured_runs_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            app = create_app(runs_dir=runs_dir)

            response = _get(app, "/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["runs_dir"], str(runs_dir))
        self.assertTrue(response.json()["dataset_uploads_dir"].endswith("uploads"))

    def test_list_dataset_adapters_returns_backend_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(runs_dir=Path(tmp) / "runs")

            response = _get(app, "/datasets/adapters")

        self.assertEqual(response.status_code, 200)
        adapter_ids = {item["adapter_id"] for item in response.json()}
        self.assertIn("cwru_bearing", adapter_ids)
        self.assertIn("nasa_ims_bearing", adapter_ids)

    def test_llm_status_returns_configured_ollama_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(runs_dir=Path(tmp) / "runs")

            with patch(
                "codigo.app.api.routes.get_default_llm_status",
                return_value=_available_llm_status(),
            ):
                response = _get(app, "/llm/status")

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["model"], "qwen3.5:4b")
        self.assertTrue(payload["model_available"])

    def test_describe_dataset_returns_descriptor_for_allowed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/datasets/describe",
                json={
                    "raw_path": raw_dir.as_posix(),
                    "adapter_id": "cwru_bearing",
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["adapter_info"]["adapter_id"], "cwru_bearing")
        self.assertEqual(payload["descriptor"]["dataset_id"], "cwru_bearing")
        self.assertEqual(payload["descriptor"]["source_format"], "directory")

    def test_describe_dataset_rejects_path_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "external" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/datasets/describe",
                json={
                    "raw_path": raw_dir.as_posix(),
                    "adapter_id": "cwru_bearing",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_describe_dataset_rejects_explicit_unsupported_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "unknown"
            raw_dir.mkdir(parents=True)
            (raw_dir / "README.txt").write_text("not a numeric signal\n", encoding="utf-8")
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/datasets/describe",
                json={
                    "raw_path": raw_dir.as_posix(),
                    "adapter_id": "cwru_bearing",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support path", response.json()["detail"])

    def test_list_runs_supports_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state(base, "run-approved", f1_score=0.91), runs_dir)
            save_run_snapshot(
                _state(base, "run-rejected", f1_score=0.70, approved=False),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            all_response = _get(app, "/runs")
            approved_response = _get(app, "/runs", params={"approved": True})

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(approved_response.status_code, 200)
        self.assertEqual(
            {item["run_id"] for item in all_response.json()},
            {"run-approved", "run-rejected"},
        )
        self.assertEqual(
            [item["run_id"] for item in approved_response.json()],
            ["run-approved"],
        )

    def test_get_run_artifacts_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(
                _state(base, "run-api", f1_score=0.94, write_debate=True),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            snapshot_response = _get(app, "/runs/run-api")
            artifacts_response = _get(app, "/runs/run-api/artifacts")
            report_response = _get(app, "/runs/run-api/report")
            audit_response = _get(app, "/runs/run-api/audit-report")
            debate_response = _get(app, "/runs/run-api/report-debate")

        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(snapshot_response.json()["run_id"], "run-api")
        self.assertEqual(artifacts_response.status_code, 200)
        self.assertEqual(artifacts_response.json()[0]["artifact_type"], "metrics")
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("# Report run-api", report_response.text)
        self.assertIn("text/markdown", report_response.headers["content-type"])
        self.assertEqual(audit_response.status_code, 200)
        self.assertIn("# Auditoria de ejecucion run-api", audit_response.text)
        self.assertIn("## Solicitud y plan aplicado", audit_response.text)
        self.assertIn("text/markdown", audit_response.headers["content-type"])
        self.assertEqual(debate_response.status_code, 200)
        self.assertIn("# Debate controlado del informe run-api", debate_response.text)
        self.assertIn("text/markdown", debate_response.headers["content-type"])

    def test_get_run_events_reconstructs_declared_historical_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state(base, "run-historical", f1_score=0.94), runs_dir)
            app = create_app(runs_dir=runs_dir)

            response = _get(app, "/runs/run-historical/events")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["title"], "Traza historica reconstruida")
        self.assertEqual(
            payload[0]["payload"]["trace_origin"],
            "reconstructed_from_decisions",
        )
        decision_events = [
            event for event in payload if event["kind"] == "supervisor_decision"
        ]
        self.assertEqual(len(decision_events), 1)
        self.assertEqual(
            decision_events[0]["decision_id"],
            "run-historical:supervisor:001",
        )

    def test_get_run_events_reconstructs_raw_gate_effective_and_unused_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_id = "run-historical-memory"
            context_id = f"{run_id}:modeler:memory"
            query = {
                "query_id": f"{run_id}:modeler:query",
                "target_agent": "modeler",
                "dataset": "nasa_ims_bearing",
                "top_k": 10,
                "min_similarity": 0.1,
            }
            raw_path = base / "memory" / "retrieved_memory_context_raw.json"
            effective_path = base / "memory" / "retrieved_memory_context.json"
            gate_path = base / "memory" / "memory_quality_gate.json"
            raw_path.parent.mkdir(parents=True)
            raw_items = [
                _memory_context_item("memory-compatible", similarity=0.81),
                _memory_context_item("memory-filtered", similarity=0.74),
            ]
            raw_path.write_text(
                json.dumps({"context_id": context_id, "query": query, "items": raw_items}),
                encoding="utf-8",
            )
            effective_path.write_text(
                json.dumps(
                    {
                        "context_id": context_id,
                        "query": {**query, "top_k": 3},
                        "items": raw_items[:1],
                        "retrieval_backend": "test_backend",
                        "embedding_model": "test_embedding:v1",
                    }
                ),
                encoding="utf-8",
            )
            gate_path.write_text(
                json.dumps(
                    {
                        "pass_count": 1,
                        "caution_count": 0,
                        "exclude_candidate_count": 1,
                        "items": [
                            {
                                "memory_record_id": "memory-filtered",
                                "recommendation": "exclude_candidate",
                                "reason_codes": ["profile_conflict"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            state = _state(base, run_id, f1_score=0.94)
            state_dict = state.to_langgraph_state()
            state_dict["artifacts"].extend(
                [
                    ArtifactRef(
                        name="modeler_retrieved_memory_context_raw",
                        artifact_type="config",
                        path=raw_path.as_posix(),
                        producer="memory_quality_gate",
                    ).model_dump(mode="json"),
                    ArtifactRef(
                        name="modeler_memory_quality_gate",
                        artifact_type="config",
                        path=gate_path.as_posix(),
                        producer="memory_quality_gate",
                    ).model_dump(mode="json"),
                    ArtifactRef(
                        name="modeler_retrieved_memory_context",
                        artifact_type="config",
                        path=effective_path.as_posix(),
                        producer="modeler",
                    ).model_dump(mode="json"),
                ]
            )
            state_dict["messages"].append(
                StateMessage(
                    role="agent",
                    name="modeler",
                    content=json.dumps(
                        {
                            "agent_name": "modeler",
                            "decision_id": f"{run_id}:modeler:001",
                            "rationale": "Observed memory but did not use it.",
                            "memory_context_id": context_id,
                            "used_memory_context": False,
                            "memory_record_ids": [],
                            "memory_record_uses": [],
                        }
                    ),
                ).model_dump(mode="json")
            )
            runs_dir = base / "runs"
            save_run_snapshot(validate_state(state_dict), runs_dir)
            app = create_app(runs_dir=runs_dir)

            response = _get(app, f"/runs/{run_id}/events")

        self.assertEqual(response.status_code, 200)
        memory_events = [
            event
            for event in response.json()
            if event["agent_name"] == "modeler" and event["kind"] == "memory_retrieval"
        ]
        self.assertEqual(
            [event["payload"]["retrieval_event"] for event in memory_events],
            ["retrieval_requested", "retrieval_returned", "retrieval_rejected_by_agent"],
        )
        returned = memory_events[1]
        self.assertEqual(returned["payload"]["raw_count"], 2)
        self.assertEqual(returned["payload"]["effective_count"], 1)
        self.assertEqual(returned["payload"]["filtered_count"], 1)
        self.assertEqual(returned["memory_record_ids"], ["memory-compatible"])
        self.assertEqual(memory_events[2]["payload"]["cited_memory_record_ids"], [])

    def test_compare_runs_returns_metric_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(
                _state(
                    base,
                    "run-baseline",
                    precision=0.90,
                    recall=0.92,
                    f1_score=0.91,
                    false_positive_rate=0.08,
                ),
                runs_dir,
            )
            save_run_snapshot(
                _state(
                    base,
                    "run-candidate",
                    precision=0.95,
                    recall=0.94,
                    f1_score=0.945,
                    false_positive_rate=0.04,
                ),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            response = _get(
                app,
                "/runs/compare",
                params=[
                    ("run_ids", "run-baseline"),
                    ("run_ids", "run-candidate"),
                ],
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        metrics = {item["metric"]: item for item in payload["metrics"]}
        self.assertEqual(payload["run_ids"], ["run-baseline", "run-candidate"])
        self.assertEqual(metrics["f1_score"]["best_run_id"], "run-candidate")
        self.assertEqual(
            metrics["false_positive_rate"]["best_run_id"],
            "run-candidate",
        )

    def test_compare_runs_returns_degradation_summary_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(
                _state(
                    base,
                    "temporal-pca",
                    f1_score=0.62,
                    metric_extra={
                        "metric_families": (
                            "binary_classification, run_to_failure_degradation"
                        ),
                        "degradation_available": True,
                        "degradation_n_runs": 1,
                        "degradation_mean_lead_time_to_failure": 400.0,
                        "degradation_mean_false_alarm_rate_nominal": 0.08,
                        "degradation_mean_score_trend_spearman": 0.81,
                        "degradation_missed_runs": 0,
                    },
                ),
                runs_dir,
            )
            save_run_snapshot(
                _state(
                    base,
                    "temporal-svm",
                    f1_score=0.70,
                    metric_extra={
                        "metric_families": (
                            "binary_classification, run_to_failure_degradation"
                        ),
                        "degradation_available": True,
                        "degradation_n_runs": 1,
                        "degradation_mean_lead_time_to_failure": 250.0,
                        "degradation_mean_false_alarm_rate_nominal": 0.02,
                        "degradation_mean_score_trend_spearman": 0.74,
                        "degradation_missed_runs": 0,
                    },
                ),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            response = _get(
                app,
                "/runs/compare",
                params=[
                    ("run_ids", "temporal-pca"),
                    ("run_ids", "temporal-svm"),
                ],
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        temporal = {
            item["metric"]: item for item in payload["degradation_metrics"]
        }
        self.assertEqual(
            temporal["degradation_mean_lead_time_to_failure"]["best_run_id"],
            "temporal-pca",
        )
        self.assertEqual(
            temporal["degradation_mean_false_alarm_rate_nominal"]["best_run_id"],
            "temporal-svm",
        )
        self.assertTrue(payload["rows"][0]["degradation_available"])

    def test_compare_runs_validation_errors_are_http_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state(base, "run-present", f1_score=0.91), runs_dir)
            app = create_app(runs_dir=runs_dir)

            too_few_runs = _get(
                app,
                "/runs/compare",
                params={"run_ids": "run-present"},
            )
            missing_run = _get(
                app,
                "/runs/compare",
                params=[
                    ("run_ids", "run-present"),
                    ("run_ids", "run-missing"),
                ],
            )

        self.assertEqual(too_few_runs.status_code, 400)
        self.assertEqual(missing_run.status_code, 404)

    def test_missing_run_and_missing_report_return_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(
                _state(base, "run-no-report", f1_score=0.90, write_report=False),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            missing_run = _get(app, "/runs/missing-run")
            missing_report = _get(app, "/runs/run-no-report/report")
            missing_debate = _get(app, "/runs/run-no-report/report-debate")

        self.assertEqual(missing_run.status_code, 404)
        self.assertEqual(missing_report.status_code, 404)
        self.assertEqual(missing_debate.status_code, 404)

    def test_post_runs_dry_run_returns_plan_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-plan-cwru",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["executed"])
        self.assertTrue(payload["plan"]["can_execute_requested_stages"])
        self.assertIsNone(payload["snapshot"])

    def test_post_runs_rejects_raw_path_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "external" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-forbidden-path",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_memory_stage_normalizes_use_memory_in_plan_and_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-plan-memory-normalized",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "requested_stages": ["memory"],
                    "use_memory": False,
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["use_memory"])
        self.assertEqual(payload["plan"]["request"]["use_memory"], True)

    def test_post_runs_execute_blocks_dataset_policy_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = _nasa_raw_dir(base)
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-blocked-nasa",
                    "dataset_id": "nasa_ims_bearing",
                    "adapter_id": "nasa_ims_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "dry_run": False,
                },
            )

        self.assertEqual(response.status_code, 409)

    def test_post_runs_execute_persists_snapshot_when_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=runs_dir, allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(pipeline_request, *, runs_dir, **kwargs):
                state = _state(
                    base,
                    pipeline_request.run_id,
                    f1_score=0.66,
                    approved=False,
                )
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-execute-cwru",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["executed"])
        self.assertEqual(payload["final_stage"], "completed")
        self.assertFalse(payload["approved"])
        self.assertEqual(payload["snapshot"]["run_id"], "api-execute-cwru")

    def test_post_runs_execute_connects_configured_memory_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            memory_dir = base / "memory"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=runs_dir,
                allowed_raw_roots=[base / "raw"],
                memory_dir=memory_dir,
            )
            memory_store = object()
            captured = {}

            def fake_run_dataset_pipeline(pipeline_request, *, runs_dir, **kwargs):
                captured["memory_config"] = kwargs.get("memory_config")
                state = _state(base, pipeline_request.run_id, f1_score=0.88)
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with (
                patch(
                    "codigo.app.api.routes.get_default_vector_memory_store",
                    return_value=memory_store,
                ) as memory_factory,
                patch(
                    "codigo.app.api.routes.run_dataset_pipeline",
                    side_effect=fake_run_dataset_pipeline,
                ),
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-execute-cwru-memory",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "use_memory": True,
                    },
                )

        memory_config = captured["memory_config"]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["use_memory"])
        memory_factory.assert_called_once_with(memory_dir)
        self.assertIs(memory_config.memory_store, memory_store)
        self.assertEqual(Path(memory_config.output_root), Path("codigo/reports"))
        self.assertFalse(memory_config.reusable_as_context)

    def test_post_runs_execute_allows_llm_when_ollama_model_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=runs_dir, allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(pipeline_request, *, runs_dir, **kwargs):
                self.assertTrue(pipeline_request.use_llm)
                state = _state(base, pipeline_request.run_id, f1_score=0.91)
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with (
                patch(
                    "codigo.app.api.routes.get_default_llm_status",
                    return_value=_available_llm_status(),
                ),
                patch(
                    "codigo.app.api.routes.run_dataset_pipeline",
                    side_effect=fake_run_dataset_pipeline,
                ),
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-execute-cwru-llm",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "use_llm": True,
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["use_llm"])
        self.assertEqual(payload["snapshot"]["run_id"], "api-execute-cwru-llm")

    def test_post_runs_execute_rejects_llm_when_ollama_model_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            with (
                patch(
                    "codigo.app.api.routes.get_default_llm_status",
                    return_value=_missing_llm_status(),
                ),
                patch("codigo.app.api.routes.run_dataset_pipeline") as runner,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-execute-cwru-llm-missing",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "use_llm": True,
                    },
                )

        self.assertEqual(response.status_code, 503)
        self.assertIn("model not found", response.json()["detail"])
        runner.assert_not_called()

    def test_post_runs_passive_human_review_returns_non_blocking_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-passive-review",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "human_review": {
                        "mode": "passive",
                        "reviewer": "advisor",
                        "required_decision_points": ["modeling"],
                    },
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["executed"])
        self.assertFalse(payload["human_approval"]["required"])
        self.assertIsNone(payload["human_approval"]["approved"])
        self.assertIn("modeling", payload["human_review_reasons"][0])

    def test_post_runs_required_human_review_blocks_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-required-review-blocked",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "dry_run": False,
                    "human_review": {
                        "mode": "required",
                        "required_decision_points": ["modeling"],
                    },
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("human review", response.json()["detail"])

    def test_post_runs_required_human_review_executes_with_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=runs_dir, allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(
                pipeline_request,
                *,
                runs_dir,
                human_approval=None,
                **kwargs,
            ):
                state = _state(
                    base,
                    pipeline_request.run_id,
                    f1_score=0.91,
                    human_approval=human_approval,
                )
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-required-review-approved",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "human_review": {
                            "mode": "required",
                            "required_decision_points": ["modeling"],
                        },
                        "human_approval": {
                            "required": True,
                            "approved": True,
                            "reviewer": "advisor",
                            "reason": "Small local execution approved.",
                        },
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["executed"])
        self.assertTrue(payload["human_approval"]["approved"])
        self.assertEqual(payload["human_approval"]["reviewer"], "advisor")

    def test_get_run_job_missing_returns_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(runs_dir=Path(tmp) / "runs")

            response = _get(app, "/run-jobs/missing-job")

        self.assertEqual(response.status_code, 404)

    def test_post_runs_background_job_persists_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            memory_dir = base / "memory"
            app = create_app(
                runs_dir=runs_dir,
                allowed_raw_roots=[base / "raw"],
                memory_dir=memory_dir,
            )
            memory_store = object()
            captured = {}

            def fake_run_dataset_pipeline(pipeline_request, *, runs_dir, **kwargs):
                captured["memory_config"] = kwargs.get("memory_config")
                runtime_recorder = kwargs.get("runtime_recorder")
                if runtime_recorder is not None:
                    runtime_recorder.emit(
                        kind="agent_decision",
                        source="agent",
                        title="Modelador simulado",
                        summary="El modelador simulado selecciona Isolation Forest.",
                        stage="modeling",
                        node="modeling_agent",
                        agent_name="modeler",
                        decision_id=f"{pipeline_request.run_id}:modeler:001",
                        rationale="Isolation Forest es suficiente para la prueba API.",
                        confidence=0.8,
                        payload={"model_name": "isolation_forest"},
                    )
                state = _state(base, pipeline_request.run_id, f1_score=0.89)
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with (
                patch(
                    "codigo.app.api.routes.get_default_vector_memory_store",
                    return_value=memory_store,
                ),
                patch(
                    "codigo.app.api.routes.run_dataset_pipeline",
                    side_effect=fake_run_dataset_pipeline,
                ),
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-background-cwru",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "background": True,
                        "use_memory": True,
                    },
                )

            payload = response.json()
            self.assertEqual(response.status_code, 202)
            self.assertFalse(payload["executed"])
            self.assertIsNone(payload["snapshot"])
            self.assertEqual(payload["job"]["run_id"], "api-background-cwru")

            job_response = _get(app, "/run-jobs/api-background-cwru")
            job_payload = _wait_for_job(app, "api-background-cwru", "completed")
            self.assertEqual(job_response.status_code, 200)
            self.assertEqual(job_payload["status"], "completed")
            self.assertEqual(job_payload["snapshot"]["run_id"], "api-background-cwru")
            event_titles = [event["title"] for event in job_payload["events"]]
            self.assertIn("Job en ejecucion", event_titles)
            self.assertIn("Modelador simulado", event_titles)
            self.assertIn("Job completado", event_titles)

            events_response = _get(
                app,
                "/run-jobs/api-background-cwru/events",
                params={"after_sequence": 1},
            )
            self.assertEqual(events_response.status_code, 200)
            self.assertTrue(
                all(event["sequence"] > 1 for event in events_response.json())
            )

            snapshot_response = _get(app, "/runs/api-background-cwru")
            self.assertEqual(snapshot_response.status_code, 200)
            self.assertEqual(snapshot_response.json()["run_id"], "api-background-cwru")
            self.assertTrue(snapshot_response.json()["runtime_events_path"])
            self.assertTrue(
                Path(snapshot_response.json()["runtime_events_path"]).exists()
            )
            persisted_events_response = _get(
                app,
                "/runs/api-background-cwru/events",
            )
            self.assertEqual(persisted_events_response.status_code, 200)
            persisted_events = persisted_events_response.json()
            self.assertIn(
                "Job completado",
                [event["title"] for event in persisted_events],
            )
            self.assertTrue(
                all(
                    event["payload"]["trace_origin"] == "persisted_runtime"
                    for event in persisted_events
                )
            )
            self.assertIs(
                captured["memory_config"].memory_store,
                memory_store,
            )

    def test_post_runs_background_job_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(*args, **kwargs):
                raise RuntimeError("simulated execution error")

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-background-failed",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "background": True,
                    },
                )

            self.assertEqual(response.status_code, 202)
            job_response = _get(app, "/run-jobs/api-background-failed")
            job_payload = _wait_for_job(app, "api-background-failed", "failed")
            self.assertEqual(job_response.status_code, 200)
            self.assertEqual(job_payload["status"], "failed")
            self.assertIn("RuntimeError", job_payload["detail"])


def _get(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, **kwargs)

    return asyncio.run(request())


def _post(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(path, **kwargs)

    return asyncio.run(request())


def _nasa_raw_dir(base: Path) -> Path:
    raw_dir = base / "raw" / "nasa_ims_bearing" / "2nd_test"
    raw_dir.mkdir(parents=True)
    (raw_dir / "2004.02.12.10.32.39").write_text(
        "0.1\t0.2\t0.3\t0.4\n0.2\t0.3\t0.4\t0.5\n",
        encoding="utf-8",
    )
    return raw_dir.parent


def _wait_for_job(app, job_id: str, expected_status: str) -> dict:
    for _ in range(100):
        response = _get(app, f"/run-jobs/{job_id}")
        payload = response.json()
        if payload["status"] == expected_status:
            return payload
        time.sleep(0.01)
    return _get(app, f"/run-jobs/{job_id}").json()


def _available_llm_status() -> LLMProviderStatus:
    return LLMProviderStatus(
        provider="ollama",
        model="qwen3.5:4b",
        host="http://127.0.0.1:11434",
        timeout_seconds=2.0,
        think=False,
        available=True,
        model_available=True,
        models=["qwen3.5:4b"],
    )


def _missing_llm_status() -> LLMProviderStatus:
    return LLMProviderStatus(
        provider="ollama",
        model="qwen3.5:4b",
        host="http://127.0.0.1:11434",
        timeout_seconds=2.0,
        think=False,
        available=True,
        model_available=False,
        models=[],
        detail="model not found in Ollama: qwen3.5:4b",
    )


def _state(
    base: Path,
    run_id: str,
    *,
    precision: float = 0.93,
    recall: float = 0.95,
    f1_score: float,
    false_positive_rate: float = 0.04,
    approved: bool = True,
    write_report: bool = True,
    write_debate: bool = False,
    human_approval: HumanApproval | None = None,
    metric_extra: dict[str, object] | None = None,
):
    report_path = base / "reports" / f"{run_id}.md"
    if write_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"# Report {run_id}\n", encoding="utf-8")

    state_dict = create_initial_cwru_state(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
        raw_path=str(base / "raw"),
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["report_path"] = str(report_path)
    state_dict["metrics"] = MetricsReport(
        metrics_path=str(base / "metrics" / f"{run_id}.json"),
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        false_positive_rate=false_positive_rate,
        extra=metric_extra or {},
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=approved,
        summary="Ejecucion aprobada." if approved else "Ejecucion rechazada.",
        next_action="continue",
        limitations=[],
    ).model_dump(mode="json")
    if human_approval is not None:
        state_dict["human_approval"] = human_approval.model_dump(mode="json")
    artifacts = [
        ArtifactRef(
            name="metrics",
            artifact_type="metrics",
            path=str(base / "metrics" / f"{run_id}.json"),
            producer="evaluator",
        ).model_dump(mode="json")
    ]
    if write_debate:
        debate_dir = base / "reports" / run_id / "evidence"
        debate_dir.mkdir(parents=True, exist_ok=True)
        debate_json = debate_dir / "report_debate.json"
        debate_md = debate_dir / "report_debate.md"
        debate_json.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": "approved_without_revision",
                    "rounds_used": 0,
                    "max_rounds": 1,
                    "final_summary": "Informe aceptado.",
                    "turns": [
                        {
                            "round_index": 0,
                            "speaker_agent": "report_verifier",
                            "human_summary": "Informe verificado.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        debate_md.write_text(
            f"# Debate controlado del informe {run_id}\n\n## Conversacion resumida\n",
            encoding="utf-8",
        )
        artifacts.extend(
            [
                ArtifactRef(
                    name="report_debate",
                    artifact_type="config",
                    path=str(debate_json),
                    producer="report_writer",
                ).model_dump(mode="json"),
                ArtifactRef(
                    name="report_debate_report",
                    artifact_type="report",
                    path=str(debate_md),
                    producer="report_writer",
                ).model_dump(mode="json"),
            ]
        )
    state_dict["artifacts"] = artifacts
    state_dict["messages"] = [
        StateMessage(
            role="supervisor",
            name="supervisor",
            content=json.dumps(
                {
                    "agent_name": "supervisor",
                    "decision_id": f"{run_id}:supervisor:001",
                    "next_stage": "completed",
                }
            ),
        ).model_dump(mode="json")
    ]
    return validate_state(state_dict)


def _memory_context_item(memory_record_id: str, *, similarity: float) -> dict:
    return {
        "rank": 1,
        "similarity": similarity,
        "retrieval_use": "boundary_context",
        "record": {
            "memory_record_id": memory_record_id,
            "collection_name": "modeler_memory",
            "target_agent": "modeler",
            "source_type": "human_review",
            "dataset": "nasa_ims_bearing",
            "memory_role": "boundary_case",
            "human_verdict": "partially_correct",
            "outcome": "partially_supported",
            "summary": f"Summary for {memory_record_id}.",
            "tags": ["boundary_case"],
        },
    }


if __name__ == "__main__":
    unittest.main()
