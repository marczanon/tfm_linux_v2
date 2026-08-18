import unittest

from codigo.app.agents.report_verifier import (
    MAX_VERIFIER_USER_PROMPT_CHARS,
    decide_report_verification_action,
)
from codigo.app.graph.state import create_initial_cwru_state, validate_state
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


class ReportVerifierAgentTests(unittest.TestCase):
    def test_deterministic_verifier_approves_supported_report(self):
        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La ejecucion queda aprobada por el evaluador como baseline local "
                "del TFM. Recall=0.9500 y F1=0.9400. Las limitaciones indican "
                "validacion limitada a CWRU."
            ),
        )

        self.assertEqual(decision.agent_name, "report_verifier")
        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.unsupported_claims, [])
        self.assertIn("report:final_report", decision.evidence_refs)
        self.assertEqual(decision.generation_trace.origin, "deterministic")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertEqual(decision.hypothesis.kind, "report_fidelity")
        self.assertTrue(decision.hypothesis.falsification_criterion)
        self.assertIn("puede aprobarse", decision.hypothesis.statement)
        self.assertNotIn("incidencia critica", decision.hypothesis.statement)

    def test_deterministic_verifier_flags_unsupported_industrial_claim(self):
        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "El sistema queda listo para produccion y cuenta con validacion "
                "industrial completa."
            ),
        )

        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(len(decision.unsupported_claims), 1)
        self.assertEqual(decision.unsupported_claims[0].severity, "critical")
        self.assertIn("validacion industrial", decision.unsupported_claims[0].claim_text)
        self.assertTrue(decision.required_corrections)
        self.assertIn("debe bloquearse", decision.hypothesis.statement)
        self.assertIn("incidencia critica", decision.hypothesis.statement)

    def test_deterministic_verifier_accepts_industrial_disclaimer(self):
        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La ejecucion queda como resultado local auditable del TFM. "
                "Las metricas se usan como baseline local, no como validacion "
                "industrial final. La generalizacion industrial requiere validar "
                "otros datasets y condiciones de carga. Las limitaciones se "
                "declaran de forma explicita."
            ),
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.unsupported_claims, [])

    def test_deterministic_verifier_blocks_official_label_claim_for_proxy_source(self):
        decision = decide_report_verification_action(
            _temporal_proxy_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "El dataset usa etiquetas oficiales por ventana y ground truth oficial "
                "para evaluar la degradacion."
            ),
        )

        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(len(decision.misleading_claims), 1)
        issue = decision.misleading_claims[0]
        self.assertEqual(issue.issue_type, "policy_violation")
        self.assertEqual(issue.severity, "critical")
        self.assertIn("label_source:temporal_proxy", issue.evidence_refs)

    def test_deterministic_verifier_accepts_negated_official_label_guardrail(self):
        decision = decide_report_verification_action(
            _temporal_proxy_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La evaluacion usa etiquetas temporales proxy. Las etiquetas por "
                "ventana no son oficiales y no deben tratarse como ground truth "
                "oficial. Las metricas binarias quedan como apoyo, no como "
                "validacion oficial. Las limitaciones se declaran de forma "
                "explicita."
            ),
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.misleading_claims, [])

    def test_official_v2_verifier_flags_physical_claims(self):
        decision = decide_report_verification_action(
            _official_v2_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La ejecucion queda aprobada: onset_confirmado=1.0, fallo detectado "
                "y lead_time_persistente=201600. Las limitaciones se declaran."
            ),
        )

        self.assertEqual(decision.verification_status, "needs_revision")
        issue = next(
            item
            for item in decision.misleading_claims
            if item.issue_id == "official_v2_physical_claim"
        )
        self.assertEqual(issue.issue_type, "policy_violation")
        self.assertIn("label_source:none", issue.evidence_refs)
        self.assertIn("controles internos", issue.suggested_fix)

    def test_official_v2_verifier_accepts_scoped_algorithmic_report(self):
        decision = decide_report_verification_action(
            _official_v2_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La ejecucion queda aceptada por controles operativos internos. "
                "Se comunica la primera alerta algoritmica persistente, el tiempo "
                "retrospectivo hasta el final registrado y la tasa de alertas "
                "pre-monitorizacion. No hay ground truth fisico por snapshot y "
                "las metricas no validan deteccion, diagnostico, inicio fisico ni "
                "RUL. Las limitaciones se declaran de forma explicita."
            ),
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertFalse(
            any(
                issue.issue_id == "official_v2_physical_claim"
                for issue in decision.misleading_claims
            )
        )

    def test_deterministic_verifier_blocks_official_nasa_data_claim_for_synthetic(self):
        decision = decide_report_verification_action(
            _synthetic_provenance_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La procedencia declarada es synthetic, pero las senales proceden "
                "del dataset oficial NASA IMS. Las limitaciones se declaran."
            ),
        )

        self.assertEqual(decision.verification_status, "blocked")
        issue = next(
            item
            for item in decision.misleading_claims
            if item.issue_id == "non_official_data_provenance_claim"
        )
        self.assertEqual(issue.severity, "critical")
        self.assertIn("data_provenance:synthetic", issue.evidence_refs)

    def test_deterministic_verifier_requires_synthetic_provenance_disclosure(self):
        decision = decide_report_verification_action(
            _synthetic_provenance_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "El pipeline procesa vibraciones y declara sus limitaciones."
            ),
        )

        self.assertEqual(decision.verification_status, "needs_revision")
        self.assertIn("requiere revision", decision.hypothesis.statement)
        self.assertIn("incidencia material corregible", decision.hypothesis.statement)
        self.assertTrue(
            any(
                issue.issue_id == "missing_data_provenance_disclosure"
                for issue in decision.missing_limitations
            )
        )

    def test_deterministic_verifier_accepts_explicit_synthetic_disclaimer(self):
        decision = decide_report_verification_action(
            _synthetic_provenance_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "Procedencia de datos: synthetic. Las senales son sinteticas tipo "
                "NASA IMS y no son mediciones oficiales de NASA. Las limitaciones "
                "se declaran de forma explicita."
            ),
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.misleading_claims, [])
        self.assertEqual(decision.missing_limitations, [])

    def test_llm_cannot_approve_official_nasa_data_claim_for_synthetic(self):
        client = FakeLLMClient(
            _approved_synthetic_verification_payload()
        )

        decision = decide_report_verification_action(
            _synthetic_provenance_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "Procedencia de datos: synthetic. Se han usado senales oficiales "
                "de NASA IMS. Las limitaciones se declaran."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(decision.verification_status, "blocked")
        self.assertTrue(
            any(
                issue.issue_id == "non_official_data_provenance_claim"
                for issue in decision.misleading_claims
            )
        )
        self.assertIn("Deterministic policy guardrails", decision.rationale)
        self.assertTrue(decision.policy_overlay_applied)
        # La hipotesis conserva la propuesta LLM; el estado efectivo y los IDs
        # del overlay registran por separado la correccion determinista.
        self.assertEqual(
            decision.hypothesis.statement,
            "El LLM considera el informe correcto.",
        )
        self.assertIn(
            "id:non_official_data_provenance_claim",
            decision.policy_overlay_issue_ids,
        )

    def test_llm_matching_critical_issue_cannot_downgrade_status(self):
        payload = _approved_synthetic_verification_payload()
        payload.update(
            {
                "verification_status": "needs_revision",
                "summary": "El LLM propone solo revision.",
                "misleading_claims": [
                    {
                        "issue_id": "non_official_data_provenance_claim",
                        "issue_type": "policy_violation",
                        "severity": "critical",
                        "claim_text": "El informe atribuye datos oficiales NASA.",
                        "reason": "Contradice la procedencia synthetic.",
                        "evidence_refs": [
                            "report:final_report",
                            "data_provenance:synthetic",
                        ],
                        "suggested_fix": "Eliminar la atribucion oficial.",
                    }
                ],
            }
        )
        client = FakeLLMClient(payload)

        decision = decide_report_verification_action(
            _synthetic_provenance_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "Procedencia de datos: synthetic. Las senales oficiales de NASA "
                "IMS se usan en el estudio. Las limitaciones se declaran."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(decision.verification_status, "blocked")

    def test_llm_verification_decision_is_used_when_valid(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_verifier",
                "decision_id": "run-report-001:report_verifier:001",
                "rationale": "The report is factual and mentions local scope.",
                "confidence": 0.88,
                "generation_trace": {"forged": True},
                "report_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                "verification_status": "approved",
                "summary": "No unsupported claims detected.",
                "unsupported_claims": [],
                "misleading_claims": [],
                "missing_limitations": [],
                "required_corrections": [],
                "acceptable_style_notes": ["Style differs but remains factual."],
                "evidence_refs": ["report:final_report", "metric:recall"],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local con recall persistido. Limitaciones: validacion "
                "limitada a CWRU y sin validacion industrial final."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertFalse(decision.policy_overlay_applied)
        self.assertEqual(decision.policy_overlay_issue_ids, [])

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.88)
        self.assertIn("ReportVerificationDecision", str(client.json_schema))
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn("Una limitacion no", client.messages[1].content)
        self.assertIn("apruebalo cuando no exista otra", client.messages[1].content)
        self.assertIn(
            "binary_fault_classification",
            client.messages[1].content,
        )
        self.assertIn(
            "evaluation.approved significa aprobacion del protocolo local",
            client.messages[1].content,
        )
        self.assertIn(
            "evidence_refs y hypothesis.risk_notes deben contener",
            client.messages[1].content,
        )

    def test_long_report_prompt_prioritizes_evidence_limits_and_conclusions(self):
        state = _state()
        report_markdown = "\n\n".join(
            [
                "# Introduccion\n" + ("Contexto general repetido. " * 700),
                (
                    "## Evidencias\nMARCADOR_EVIDENCIA: recall=0.95 con "
                    "evidence_ref metric:recall."
                ),
                "## Desarrollo\n" + ("Detalle secundario. " * 700),
                (
                    "## Limitaciones\nMARCADOR_LIMITACIONES: validacion "
                    "limitada a CWRU."
                ),
                (
                    "## Conclusiones\nMARCADOR_CONCLUSIONES: resultado local "
                    "auditable, sin extrapolacion industrial."
                ),
            ]
        )
        payload = decide_report_verification_action(
            state,
            report_markdown=report_markdown,
        ).model_dump(mode="json")
        client = FakeLLMClient(payload)

        decision = decide_report_verification_action(
            state,
            report_markdown=report_markdown,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        prompt = client.messages[1].content
        self.assertLessEqual(len(prompt), MAX_VERIFIER_USER_PROMPT_CHARS)
        self.assertIn("MARCADOR_EVIDENCIA", prompt)
        self.assertIn("MARCADOR_LIMITACIONES", prompt)
        self.assertIn("MARCADOR_CONCLUSIONES", prompt)
        self.assertIn("metric:recall", prompt)
        self.assertIn("EXTRACTO SEMANTICO", prompt)
        self.assertIn("missing_persisted_limitations", prompt)

    def test_llm_empty_needs_revision_falls_back_to_clean_approval(self):
        payload = {
            "agent_name": "report_verifier",
            "decision_id": "run-report-001:report_verifier:001",
            "rationale": "The report may need review.",
            "confidence": 0.81,
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
            "verification_status": "needs_revision",
            "summary": "Review suggested without a concrete issue.",
            "unsupported_claims": [],
            "misleading_claims": [],
            "missing_limitations": [],
            "required_corrections": [],
            "acceptable_style_notes": [],
            "evidence_refs": ["report:final_report"],
        }
        client = FakeLLMClient(payload)

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local factual con recall persistido. Las limitaciones "
                "se declaran como validacion limitada a CWRU."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.unsupported_claims, [])
        self.assertEqual(decision.misleading_claims, [])
        self.assertEqual(decision.missing_limitations, [])
        self.assertEqual(decision.required_corrections, [])
        self.assertIn("Guardrail correction", decision.rationale)
        self.assertIn("listas", client.messages[-1].content)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        self.assertEqual(
            decision.generation_trace.fallback_from_attempt_id,
            "run-report-001:report_verifier:001:attempt:002",
        )

    def test_llm_verification_repair_records_second_attempt(self):
        report_markdown = (
            "Informe local factual con recall persistido. Las limitaciones "
            "se declaran como validacion limitada a CWRU."
        )
        valid_payload = decide_report_verification_action(
            _state(),
            report_markdown=report_markdown,
        ).model_dump(mode="json")
        valid_payload["rationale"] = "Corrected after contract feedback."
        valid_payload["confidence"] = 0.84
        valid_payload["generation_trace"] = {"forged": True}
        invalid_payload = dict(valid_payload)
        invalid_payload["verification_status"] = "needs_revision"
        client = FakeLLMClient([invalid_payload, valid_payload])

        decision = decide_report_verification_action(
            _state(),
            report_markdown=report_markdown,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.confidence, 0.84)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")

    def test_empty_llm_revision_does_not_hide_deterministic_issue(self):
        payload = {
            "agent_name": "report_verifier",
            "decision_id": "run-report-001:report_verifier:001",
            "rationale": "The report may need review.",
            "confidence": 0.81,
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
            "verification_status": "needs_revision",
            "summary": "Review suggested without a concrete issue.",
            "unsupported_claims": [],
            "misleading_claims": [],
            "missing_limitations": [],
            "required_corrections": [],
            "acceptable_style_notes": [],
            "evidence_refs": ["report:final_report"],
        }
        client = FakeLLMClient(payload)

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.verification_status, "blocked")
        self.assertTrue(decision.unsupported_claims)
        self.assertTrue(decision.required_corrections)
        self.assertIn("Guardrail correction", decision.rationale)

    def test_llm_verification_alias_payload_is_normalized(self):
        client = FakeLLMClient(
            {
                "decision": "approved",
                "run_id": "run-report-001",
                "dataset": "cwru_bearing",
                "notes": "El informe es factual y no requiere revisiones.",
                "evidence_references": ["report:final_report", "metric:recall"],
                "issues": [],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown="Informe local con limitaciones.",
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.summary, "El informe es factual y no requiere revisiones.")
        self.assertIn("metric:recall", decision.evidence_refs)

    def test_llm_compact_issue_alias_preserves_semantics_without_fallback(self):
        client = FakeLLMClient(
            {
                "classification": "needs_revision",
                "summary": "La metrica requiere una acotacion adicional.",
                "issues": [
                    {
                        "issue_id": "metric-scope",
                        "severity": "non_critical",
                        "description": "El alcance de recall debe quedar acotado.",
                        "evidence_ref": "metric:recall",
                        "required_correction": "Acotar recall al benchmark local.",
                    }
                ],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local sobre CWRU con limitaciones explicitas y sin "
                "extrapolacion industrial."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.verification_status, "needs_revision")
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.unsupported_claims[0].issue_id, "metric-scope")
        self.assertEqual(decision.unsupported_claims[0].severity, "medium")
        self.assertEqual(
            decision.unsupported_claims[0].evidence_refs,
            ["metric:recall"],
        )
        self.assertIn("Acotar recall", decision.required_corrections[0])
        self.assertFalse(decision.policy_overlay_applied)

    def test_llm_live_statement_issue_dialect_preserves_semantics(self):
        client = FakeLLMClient(
            {
                "verification_status": "blocked",
                "issues": [
                    {
                        "issue_id": "critical_generalization_claim",
                        "issue_type": "critical",
                        "statement": (
                            "El informe afirma validacion industrial completa "
                            "y generalizacion garantizada."
                        ),
                        "falsification_criterion": (
                            "El catalogo limita la validacion al benchmark local."
                        ),
                        "expected_observation": (
                            "Eliminar la afirmacion industrial y acotar el "
                            "resultado al benchmark local."
                        ),
                        "evidence_refs": ["limitation:1"],
                        "risk_notes": [
                            "La afirmacion excede la evidencia disponible."
                        ],
                    },
                    {
                        "issue_id": "missing_limitation",
                        "issue_type": "missing_persisted_limitations",
                        "statement": (
                            "El informe no incluye la limitacion persistida "
                            "del benchmark local."
                        ),
                        "falsification_criterion": (
                            "La limitacion aparece de forma explicita."
                        ),
                        "expected_observation": (
                            "Incluir la limitacion persistida en el informe."
                        ),
                        "evidence_refs": ["limitation:1"],
                        "risk_notes": [
                            "La omision induce una lectura no acotada."
                        ],
                    },
                ],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. Los resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(len(decision.unsupported_claims), 1)
        self.assertEqual(len(decision.missing_limitations), 1)
        self.assertIn(
            "Eliminar la afirmacion industrial",
            decision.unsupported_claims[0].suggested_fix,
        )
        self.assertFalse(decision.policy_overlay_applied)

    def test_repair_prompt_requires_exact_issue_contract(self):
        initial_payload = {
            "classification": "blocked",
            "issues": [
                {
                    "issue_id": "critical_generalization_claim",
                    "issue_type": "critical",
                    "statement": (
                        "El informe afirma validacion industrial completa."
                    ),
                    "risk_notes": [
                        "La afirmacion contradice la limitacion persistida."
                    ],
                    "evidence_refs": ["limitation:1"],
                }
            ],
        }
        repaired_payload = {
            "verification_status": "blocked",
            "issues": [
                {
                    "issue_id": "critical_generalization_claim",
                    "issue_type": "unsupported_claim",
                    "severity": "critical",
                    "claim_text": (
                        "El informe afirma validacion industrial completa."
                    ),
                    "reason": (
                        "La afirmacion contradice la limitacion persistida."
                    ),
                    "evidence_refs": ["limitation:1"],
                    "suggested_fix": (
                        "Eliminar la afirmacion industrial y acotar el alcance."
                    ),
                }
            ],
        }
        client = FakeLLMClient([initial_payload, repaired_payload])

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. La limitacion local se declara."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(decision.verification_status, "blocked")
        repair_prompt = client.messages[-1].content
        self.assertIn("claim_text, reason, evidence_refs", repair_prompt)
        self.assertIn("No uses statement", repair_prompt)

    def test_llm_compact_alias_replaces_unknown_refs_with_missing_evidence(self):
        client = FakeLLMClient(
            {
                "classification": "needs_revision",
                "summary": "Existe una afirmacion sin referencia valida.",
                "issues": [
                    {
                        "issue_id": "unknown-ref",
                        "severity": "non_critical",
                        "description": "Una afirmacion cuantitativa carece de soporte.",
                        "evidence_ref": "metric:invented",
                        "required_correction": "Retirar la cifra no soportada.",
                    }
                ],
                "evidence_references": ["artifact:not-real"],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown="Informe local con limitaciones explicitas.",
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.evidence_refs, ["missing:evidence"])
        self.assertEqual(
            decision.unsupported_claims[0].evidence_refs,
            ["missing:evidence"],
        )
        self.assertEqual(decision.generation_trace.origin, "llm")

    def test_llm_reasoning_alias_builds_blocking_issue_without_overlay(self):
        client = FakeLLMClient(
            {
                "classification": "blocked",
                "summary": "El informe excede de forma critica la evidencia.",
                "reasoning": [
                    "Afirma validacion industrial completa y generalizacion "
                    "garantizada sin evidencia.",
                    "El informe omite las limitaciones persistidas del benchmark.",
                ],
                "required_corrections": [
                    "Eliminar la validacion industrial y limitar el alcance al benchmark.",
                    "Incluir las limitaciones de la evaluacion.",
                ],
                "evidence_references": ["report:final_report"],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. Los resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(len(decision.unsupported_claims), 1)
        self.assertEqual(len(decision.missing_limitations), 1)
        self.assertEqual(
            decision.unsupported_claims[0].issue_id,
            "unsupported_industrial_validation",
        )
        self.assertEqual(decision.unsupported_claims[0].severity, "critical")
        self.assertFalse(decision.policy_overlay_applied)
        self.assertEqual(decision.policy_overlay_issue_ids, [])

    def test_llm_free_issue_ids_are_canonicalized_without_overlay(self):
        client = FakeLLMClient(
            {
                "classification": "blocked",
                "summary": "Las afirmaciones exceden el alcance local.",
                "issues": [
                    {
                        "issue_id": "critical_validation_claim",
                        "type": "factual_error",
                        "severity": "critical",
                        "description": (
                            "El informe afirma validacion industrial completa y "
                            "generalizacion garantizada."
                        ),
                        "evidence_ref": "limitations",
                        "required_correction": "Eliminar la afirmacion industrial.",
                    },
                    {
                        "issue_id": "MISSING_LIMITATION",
                        "type": "missing_documentation",
                        "severity": "critical",
                        "description": (
                            "El informe no incluye una limitacion clara sobre el "
                            "alcance local persistido."
                        ),
                        "evidence_ref": "limitations",
                        "required_correction": "Incluir la limitacion del benchmark.",
                    },
                ],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. Los resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(
            decision.unsupported_claims[0].issue_id,
            "unsupported_industrial_validation",
        )
        self.assertEqual(
            decision.missing_limitations[0].issue_id,
            "missing_persisted_limitations",
        )
        self.assertFalse(decision.policy_overlay_applied)
        self.assertEqual(decision.policy_overlay_issue_ids, [])

    def test_llm_issue_accepts_correction_required_alias_without_fallback(self):
        client = FakeLLMClient(
            {
                "classification": "blocked",
                "issues": [
                    {
                        "issue_id": "critical_validation_claims",
                        "type": "factual_error",
                        "severity": "critical",
                        "description": (
                            "El informe afirma validacion industrial completa y "
                            "que el sistema esta listo para produccion."
                        ),
                        "evidence_refs": ["limitation:1"],
                        "correction_required": (
                            "Eliminar la afirmacion industrial y limitar el "
                            "alcance al benchmark local."
                        ),
                    },
                    {
                        "issue_id": "missing_limitation",
                        "type": "missing_evidence",
                        "severity": "critical",
                        "description": (
                            "El informe no incluye una limitacion clara sobre "
                            "el alcance local."
                        ),
                        "evidence_refs": ["limitation:1"],
                        "correction_required": (
                            "Incluir la limitacion persistida del benchmark."
                        ),
                    },
                ],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(len(decision.unsupported_claims), 1)
        self.assertEqual(len(decision.missing_limitations), 1)
        self.assertFalse(decision.policy_overlay_applied)

    def test_llm_issue_accepts_required_corrections_list_after_repair(self):
        client = FakeLLMClient(
            {
                "verification_status": "blocked",
                "issues": [
                    {
                        "issue_id": "critical_validation_claims",
                        "type": "factual_error",
                        "severity": "critical",
                        "description": (
                            "El informe afirma que dispone de validacion "
                            "industrial completa."
                        ),
                        "evidence_refs": ["limitation:1"],
                        "required_corrections": [
                            "Eliminar la afirmacion de validacion industrial."
                        ],
                    },
                    {
                        "issue_id": "missing_limitation",
                        "type": "missing_evidence",
                        "severity": "critical",
                        "description": (
                            "El informe no incluye una limitacion clara del "
                            "benchmark local."
                        ),
                        "evidence_refs": ["limitation:1"],
                        "required_corrections": [
                            "Incluir la limitacion persistida del benchmark."
                        ],
                    },
                ],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(len(decision.required_corrections), 2)
        self.assertFalse(decision.policy_overlay_applied)

    def test_missing_documentation_type_wins_over_industrial_words_in_description(self):
        client = FakeLLMClient(
            {
                "decision_id": "run-report-001:report_verifier:001",
                "verification_status": "blocked",
                "issues": [
                    {
                        "description": (
                            "El informe afirma que el sistema 'dispone de "
                            "validacion industrial completa' y que los resultados "
                            "'garantizan su generalizacion'."
                        ),
                        "evidence_ref": "limitations",
                        "issue_id": "critical_validation_claim",
                        "required_correction": (
                            "Eliminar afirmaciones de validacion industrial "
                            "completa y generalizacion garantizada."
                        ),
                        "severity": "critical",
                        "type": "factual_error",
                    },
                    {
                        "description": (
                            "El informe no incluye una limitacion clara y "
                            "explicita sobre la falta de validacion industrial o "
                            "la imposibilidad de generalizacion, a pesar de que "
                            "el catalogo contiene una limitacion persistida."
                        ),
                        "evidence_ref": "missing:evidence",
                        "issue_id": "missing_limitation",
                        "required_correction": (
                            "Incluir una declaracion explicita que refleje las "
                            "limitaciones documentadas."
                        ),
                        "severity": "critical",
                        "type": "missing_documentation",
                    },
                ],
                "report_path": (
                    "codigo/reports/cwru_bearing/run-report-001/final_report.md"
                ),
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. Los resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(
            [issue.issue_id for issue in decision.unsupported_claims],
            ["unsupported_industrial_validation"],
        )
        self.assertEqual(
            [issue.issue_id for issue in decision.missing_limitations],
            ["missing_persisted_limitations"],
        )
        self.assertFalse(decision.policy_overlay_applied)
        self.assertEqual(decision.policy_overlay_issue_ids, [])

    def test_repair_uses_exact_positional_top_level_corrections_from_fix5(self):
        issues = [
            {
                "description": (
                    "El informe afirma que el sistema esta listo para produccion "
                    "y dispone de validacion industrial completa. Esto contradice "
                    "directamente la evidencia del catalogo que indica una "
                    "validacion limitada al benchmark local CWRU y la ausencia "
                    "de evidencia temporal o de trayectoria de predicciones."
                ),
                "evidence_content": "Validacion limitada al benchmark local CWRU.",
                "evidence_ref": "limitations:1",
                "issue_id": "pre_production_claim",
                "severity": "critical",
                "type": "factual_error",
            },
            {
                "description": (
                    "El informe afirma que los resultados garantizan su "
                    "generalizacion. La evidencia disponible solo respalda el "
                    "rendimiento en un dataset local especifico sin demostrar "
                    "capacidad de generalizacion."
                ),
                "evidence_content": "Validacion limitada al benchmark local CWRU.",
                "evidence_ref": "limitations:1",
                "issue_id": "generalization_claim",
                "severity": "critical",
                "type": "factual_error",
            },
            {
                "description": (
                    "El informe no incluye una limitacion clara en su texto "
                    "narrativo, a pesar de que el catalogo de evidencias contiene "
                    "una limitacion persistida sobre la validacion local."
                ),
                "evidence_content": "Validacion limitada al benchmark local CWRU.",
                "evidence_ref": "limitations:1",
                "issue_id": "missing_limitation",
                "severity": "critical",
                "type": "missing_limitation",
            },
        ]
        first_payload = {
            "classification": "blocked",
            "decision_id": "run-report-001:report_verifier:001",
            "issues": issues,
            "reasoning": (
                "Las afirmaciones industriales y de generalizacion contradicen "
                "la limitacion persistida del benchmark local."
            ),
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
        }
        corrections = [
            (
                "Eliminar afirmaciones de 'listo para produccion' y 'validacion "
                "industrial completa' hasta obtener evidencia suficiente."
            ),
            (
                "Eliminar afirmaciones de 'generalizacion garantizada' hasta "
                "presentar pruebas en datasets externos."
            ),
            (
                "Incluir explicitamente la limitacion de que la validacion es "
                "solo local al benchmark CWRU."
            ),
        ]
        repaired_payload = {
            "decision_id": "run-report-001:report_verifier:001",
            "issues": issues,
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
            "required_corrections": corrections,
            "verification_status": "blocked",
        }
        client = FakeLLMClient([first_payload, repaired_payload])

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. Los resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(decision.required_corrections, corrections)
        self.assertEqual(len(decision.unsupported_claims), 2)
        self.assertEqual(len(decision.missing_limitations), 1)
        self.assertTrue(
            all(
                issue.evidence_refs == ["limitation:1"]
                for issue in [
                    *decision.unsupported_claims,
                    *decision.missing_limitations,
                ]
            )
        )
        self.assertFalse(decision.policy_overlay_applied)
        self.assertEqual(decision.policy_overlay_issue_ids, [])

    def test_fix6_unreflected_persisted_limitations_need_no_overlay(self):
        first_issues = [
            {
                "description": (
                    "El informe afirma que el sistema esta listo para produccion "
                    "y dispone de validacion industrial completa. Esto contradice "
                    "la evidencia que limita la validacion al benchmark local."
                ),
                "evidence_ref": (
                    "limitations: Validacion limitada al benchmark local CWRU."
                ),
                "issue_id": "pre_production_claim",
                "severity": "critical",
            },
            {
                "description": (
                    "El informe afirma que los resultados garantizan su "
                    "generalizacion, sin evidencia mas alla del dataset local."
                ),
                "evidence_ref": (
                    "limitations: Validacion limitada al benchmark local CWRU."
                ),
                "issue_id": "generalization_claim",
                "severity": "critical",
            },
            {
                "description": (
                    "El catalogo de evidencias contiene limitaciones persistidas "
                    "(ausencia de evidencia temporal, predicciones incompletas) "
                    "que no se reflejan como advertencias claras en el texto del "
                    "informe."
                ),
                "evidence_ref": (
                    "limitations: Validacion limitada al benchmark local CWRU."
                ),
                "issue_id": "missing_limitation",
                "severity": "critical",
            },
        ]
        repaired_issues = [
            {
                **first_issues[0],
                "required_correction": (
                    "Eliminar afirmaciones sobre produccion y validacion industrial."
                ),
            },
            {
                **first_issues[1],
                "required_correction": (
                    "Eliminar afirmaciones de generalizacion garantizada."
                ),
            },
            {
                **first_issues[2],
                "required_correction": (
                    "Incluir una seccion que detalle las limitaciones persistidas."
                ),
            },
        ]
        base_payload = {
            "decision_id": "run-report-001:report_verifier:001",
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
        }
        client = FakeLLMClient(
            [
                {
                    **base_payload,
                    "classification": "blocked",
                    "issues": first_issues,
                },
                {
                    **base_payload,
                    "verification_status": "blocked",
                    "issues": repaired_issues,
                },
            ]
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa. Los resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(
            [issue.issue_id for issue in decision.missing_limitations],
            ["missing_persisted_limitations"],
        )
        self.assertFalse(decision.policy_overlay_applied)
        self.assertEqual(decision.policy_overlay_issue_ids, [])

    def test_policy_overlay_ids_only_report_added_issues(self):
        client = FakeLLMClient(
            {
                "classification": "blocked",
                "issues": [
                    {
                        "description": (
                            "El informe afirma validacion industrial completa y "
                            "que el sistema esta listo para produccion."
                        ),
                        "evidence_ref": "limitation:1",
                        "required_correction": (
                            "Eliminar las afirmaciones de validacion industrial."
                        ),
                        "severity": "critical",
                        "type": "factual_error",
                    }
                ],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema esta listo para produccion y dispone de validacion "
                "industrial completa."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertTrue(decision.policy_overlay_applied)
        self.assertEqual(
            decision.policy_overlay_issue_ids,
            ["id:missing_persisted_limitations"],
        )
        self.assertEqual(len(decision.unsupported_claims), 1)
        self.assertEqual(len(decision.missing_limitations), 1)

    def test_compact_hypothesis_aliases_validate_first_pass_when_complete(self):
        client = FakeLLMClient(
            {
                "decision": "approved",
                "decision_id": "run-report-001:report_verifier:001",
                "issues": [],
                "report_path": (
                    "codigo/reports/cwru_bearing/run-report-001/final_report.md"
                ),
                "hypothesis": {
                    "kind": "report_fidelity",
                    "hypothesis_id": "compact-hypothesis-001",
                    "fidelity_claim": (
                        "El informe limita correctamente su resultado al "
                        "benchmark local CWRU."
                    ),
                    "scope": "Fidelidad factual del informe local CWRU.",
                    "evidence_cutoff": (
                        "Informe y catalogo cerrados antes de la auditoria."
                    ),
                    "expected_observations": [
                        "No aparecen claims industriales no soportados."
                    ],
                    "refutation_criteria": [
                        "Aparece una afirmacion industrial no respaldada.",
                        "Se omite una limitacion material.",
                    ],
                    "evidence": "report:final_report",
                    "risk_notes": "Una omision material invalidaria el veredicto.",
                    "assumptions": "El catalogo entregado esta cerrado.",
                },
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local con recall persistido. La validacion esta "
                "limitada al benchmark CWRU y no es validacion industrial."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertEqual(
            decision.hypothesis.statement,
            "El informe limita correctamente su resultado al benchmark local CWRU.",
        )
        self.assertEqual(
            decision.hypothesis.risk_notes,
            ["Una omision material invalidaria el veredicto."],
        )
        self.assertEqual(
            decision.hypothesis.assumptions,
            ["El catalogo entregado esta cerrado."],
        )
        self.assertEqual(decision.hypothesis.evidence_refs, ["report:final_report"])
        self.assertNotIn("hypothesis_id", decision.hypothesis.model_dump())

    def test_live_hypothesis_kind_alias_validates_first_pass(self):
        client = FakeLLMClient(
            {
                "decision": "approved",
                "issues": [],
                "hypothesis": {
                    "kind": "fidelity_claim",
                    "statement": (
                        "El informe limita sus resultados al benchmark local."
                    ),
                    "scope": "Fidelidad factual del informe CWRU.",
                    "evidence_cutoff": (
                        "Informe y catalogo cerrados antes de verificar."
                    ),
                    "expected_observation": (
                        "No aparecen afirmaciones industriales positivas."
                    ),
                    "falsification_criterion": (
                        "Aparece una extrapolacion industrial no respaldada."
                    ),
                    "evidence_refs": ["report:final_report"],
                    "risk_notes": ["Una omision material cambiaria el veredicto."],
                    "assumptions": [],
                },
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local con validacion limitada a CWRU y sin "
                "generalizacion industrial."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.hypothesis.kind, "report_fidelity")
        self.assertEqual(decision.generation_trace.validation_status, "validated")

    def test_generalization_limitation_kind_alias_is_report_fidelity(self):
        report = (
            "Informe local con validacion limitada a CWRU y sin "
            "generalizacion industrial."
        )
        payload = decide_report_verification_action(
            _state(),
            report_markdown=report,
        ).model_dump(mode="json")
        payload["hypothesis"]["kind"] = "generalization_limitation"
        client = FakeLLMClient(payload)

        decision = decide_report_verification_action(
            _state(),
            report_markdown=report,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.hypothesis.kind, "report_fidelity")
        self.assertEqual(decision.generation_trace.validation_status, "validated")

    def test_repair_can_reuse_complete_hypothesis_from_first_attempt(self):
        hypothesis = {
            "kind": "report_fidelity",
            "statement": "El informe esta acotado al benchmark local.",
            "scope": "Fidelidad factual del informe CWRU.",
            "evidence_cutoff": "Informe y catalogo cerrados antes de verificar.",
            "expected_observation": "No aparecen claims industriales positivos.",
            "falsification_criterion": "Aparece un claim industrial no soportado.",
            "evidence_refs": ["report:final_report"],
            "risk_notes": ["Una omision material cambiaria el veredicto."],
            "assumptions": [],
        }
        client = FakeLLMClient(
            [
                {
                    "verification_status": "needs_revision",
                    "issues": [],
                    "hypothesis": hypothesis,
                },
                {
                    "verification_status": "approved",
                    "issues": [],
                    "hypothesis": None,
                },
            ]
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local con validacion limitada a CWRU y sin "
                "generalizacion industrial."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(decision.hypothesis.statement, hypothesis["statement"])

    def test_incomplete_issue_is_repaired_instead_of_silently_discarded(self):
        client = FakeLLMClient(
            [
                {
                    "verification_status": "approved",
                    "issues": [
                        {
                            "statement": "Una cifra no tiene soporte suficiente.",
                            "evidence_refs": ["metric:recall"],
                        }
                    ],
                },
                {
                    "verification_status": "needs_revision",
                    "issues": [
                        {
                            "issue_id": "metric-scope",
                            "issue_type": "unsupported_claim",
                            "severity": "medium",
                            "claim_text": "Una cifra no tiene soporte suficiente.",
                            "reason": "El alcance de la metrica no esta declarado.",
                            "evidence_refs": ["metric:recall"],
                            "suggested_fix": "Acotar la cifra al benchmark local.",
                        }
                    ],
                },
            ]
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local con validacion limitada a CWRU y sin "
                "generalizacion industrial."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(decision.verification_status, "needs_revision")
        self.assertEqual(len(decision.unsupported_claims), 1)

    def test_live_safe_hypothesis_repair_reuses_emitted_scope(self):
        initial_payload = {
            "decision": "approved",
            "decision_id": "run-report-001:report_verifier:001",
            "issues": [],
            "notes": "El informe limita correctamente su alcance al benchmark local.",
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
            "hypothesis": {
                "evidence": [
                    "limitation:1",
                    "data_provenance:official",
                    "dataset:cwru_bearing",
                ],
                "fidelity_claim": (
                    "El informe presenta metricas locales sin demostrar "
                    "generalizacion ni preparacion industrial."
                ),
                "refutation_criteria": [
                    "El informe contiene una afirmacion industrial positiva."
                ],
                "scope": (
                    "Validacion de metricas en CWRU bajo clasificacion binaria."
                ),
            },
        }
        repaired_payload = {
            "decision_id": "run-report-001:report_verifier:001",
            "issues": [],
            "report_path": (
                "codigo/reports/cwru_bearing/run-report-001/final_report.md"
            ),
            "verification_status": "approved",
            "hypothesis": {
                "kind": "report_fidelity",
                "statement": (
                    "El informe presenta metricas locales sin afirmar "
                    "generalizacion ni preparacion industrial."
                ),
                "evidence_cutoff": (
                    "Informe y catalogo persistidos antes de la verificacion."
                ),
                "expected_observation": (
                    "No se observan claims positivos fuera del alcance local."
                ),
                "falsification_criterion": (
                    "Aparece una afirmacion industrial no respaldada."
                ),
                "evidence_refs": ["report:final_report", "limitation:1"],
                "risk_notes": (
                    "La ausencia de evidencia externa limita la generalizacion."
                ),
            },
        }
        client = FakeLLMClient([initial_payload, repaired_payload])

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "Informe local con recall persistido. La validacion esta "
                "limitada al benchmark CWRU y no es validacion industrial."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(
            decision.hypothesis.scope,
            "Validacion de metricas en CWRU bajo clasificacion binaria.",
        )
        self.assertEqual(
            decision.hypothesis.risk_notes,
            ["La ausencia de evidencia externa limita la generalizacion."],
        )
        repair_prompt = client.messages[-1].content
        self.assertIn("scope es obligatorio", repair_prompt)
        self.assertIn("deben ser arrays JSON", repair_prompt)
        self.assertIn("No incluyas hypothesis_id", repair_prompt)

    def test_live_unsafe_hypothesis_repair_drops_metadata_without_fallback(self):
        initial_payload = {
            "classification": "blocked",
            "decision_id": "run-report-001:report_verifier:001",
            "issues": [
                {
                    "description": (
                        "El informe afirma validacion industrial completa y "
                        "generalizacion garantizada."
                    ),
                    "evidence_ref": "limitations",
                    "required_correction": (
                        "Eliminar las afirmaciones industriales no soportadas."
                    ),
                    "severity": "critical",
                    "type": "factual_error",
                },
                {
                    "description": (
                        "El informe no menciona la limitacion persistida del "
                        "benchmark local."
                    ),
                    "evidence_ref": "limitations",
                    "required_correction": (
                        "Incluir explicitamente la limitacion local."
                    ),
                    "severity": "critical",
                    "type": "missing_evidence",
                },
            ],
            "hypothesis": {
                "evidence": (
                    "El catalogo limita la validacion al benchmark local CWRU."
                ),
                "hypothesis_id": "hypothesis_001",
                "refutation_criteria": (
                    "Las afirmaciones industriales disponen de evidencia externa."
                ),
                "scope": "Consistencia entre informe y catalogo cerrado.",
                "statement": (
                    "El informe excede la evidencia al afirmar validacion industrial."
                ),
            },
        }
        repaired_payload = {
            **initial_payload,
            "verification_status": "blocked",
            "hypothesis": {
                "kind": "report_fidelity",
                "hypothesis_id": "run-report-001:report_verifier:001:hf_001",
                "statement": (
                    "El informe excede la evidencia al afirmar validacion industrial."
                ),
                "scope": "Consistencia entre informe y catalogo cerrado.",
                "evidence_cutoff": (
                    "Informe y catalogo persistidos antes de la verificacion."
                ),
                "expected_observation": (
                    "Se identifican como criticos los claims industriales."
                ),
                "falsification_criterion": (
                    "Existe evidencia externa que respalda esos claims."
                ),
                "evidence_refs": ["limitations"],
                "risk_notes": (
                    "Aceptar el claim induciria una extrapolacion no respaldada."
                ),
            },
        }
        client = FakeLLMClient([initial_payload, repaired_payload])

        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "El sistema dispone de validacion industrial completa y los "
                "resultados garantizan su generalizacion."
            ),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(
            decision.hypothesis.risk_notes,
            ["Aceptar el claim induciria una extrapolacion no respaldada."],
        )
        self.assertEqual(decision.hypothesis.evidence_refs, ["missing:evidence"])
        self.assertNotIn("hypothesis_id", decision.hypothesis.model_dump())

    def test_invalid_llm_verification_uses_guardrail_correction(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_verifier",
                "decision_id": "run-report-001:report_verifier:001",
                "rationale": "Invalid path.",
                "confidence": 0.9,
                "report_path": "/tmp/final_report.md",
                "verification_status": "approved",
                "summary": "Invalid.",
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown="Informe local con limitaciones.",
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(
            decision.report_path,
            "codigo/reports/cwru_bearing/run-report-001/final_report.md",
        )
        self.assertLessEqual(decision.confidence, 0.72)
        self.assertIn("Guardrail correction", decision.rationale)
        self.assertNotIn("validation errors", decision.rationale)
        self.assertNotIn("errors.pydantic.dev", decision.rationale)


def _state():
    state_dict = create_initial_cwru_state(
        thread_id="cwru-report-verifier-test",
        run_id="run-report-001",
    )
    state_dict["report_path"] = "codigo/reports/cwru_bearing/run-report-001/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        precision=0.93,
        recall=0.95,
        f1_score=0.94,
        false_positive_rate=0.04,
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


def _temporal_proxy_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-report-verifier-test",
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
        data_provenance="official",
        provenance_detection_method="trusted_adapter",
    ).model_dump(mode="json")
    state_dict["report_path"] = "codigo/reports/nasa_ims_bearing/run-report-nasa-temporal-001/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/nasa_ims_bearing/evaluation/metrics.json",
        extra={
            "degradation_available": True,
            "degradation_mean_lead_time_to_failure": 300.0,
        },
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Temporal degradation metrics accepted.",
        next_action="continue",
        limitations=["Etiquetas proxy temporales; no oficiales por ventana."],
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _synthetic_provenance_state():
    state = _temporal_proxy_state()
    payload = state.model_dump(mode="json")
    payload["project_context"] = state.project_context.model_copy(
        update={
            "data_provenance": "synthetic",
            "provenance_detection_method": "synthetic_dataset_spec",
            "provenance_evidence_path": (
                "codigo/data/raw/nasa_ims_bearing/synthetic_dataset_spec.json"
            ),
            "provenance_evidence_sha256": "b" * 64,
        }
    ).model_dump(mode="json")
    return validate_state(payload)


def _official_v2_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-report-verifier-official-v2-test",
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
    state_dict["report_path"] = (
        "codigo/reports/nasa_ims_bearing/"
        "run-report-nasa-official-v2-001/final_report.md"
    )
    state_dict["metrics"] = MetricsReport(
        extra={
            "degradation_available": True,
            "degradation_confirmed_degradation_before_failure_rate": 1.0,
            "degradation_mean_persistent_lead_time_to_failure": 201600.5632,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.7937,
        },
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Aceptada por controles operativos internos.",
        next_action="continue",
        limitations=["No hay ground truth fisico por snapshot."],
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _approved_synthetic_verification_payload():
    return {
        "agent_name": "report_verifier",
        "decision_id": "run-report-nasa-temporal-001:report_verifier:001",
        "rationale": "El LLM considera el informe correcto.",
        "confidence": 0.9,
        "report_path": (
            "codigo/reports/nasa_ims_bearing/"
            "run-report-nasa-temporal-001/final_report.md"
        ),
        "verification_status": "approved",
        "summary": "Sin incidencias segun el LLM.",
        "unsupported_claims": [],
        "misleading_claims": [],
        "missing_limitations": [],
        "required_corrections": [],
        "acceptable_style_notes": [],
        "evidence_refs": ["report:final_report"],
    }


if __name__ == "__main__":
    unittest.main()
