import unittest

from pydantic import ValidationError

from codigo.app.agents.monitoring_reviewer import decide_monitoring_review_action
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_ROLES,
    MonitoringPolicyProposal,
    MonitoringReviewDecision,
)
from codigo.app.services.llm import LLMCallError
from codigo.app.services.monitoring_policy_proposal import (
    build_monitoring_policy_proposal,
    validate_monitoring_policy_proposal,
)
from codigo.tests.test_monitoring_reviewer import (
    FakeJSONLLMClient,
    _catalog,
    _causal_view,
    _evidence_records,
    _llm_payload,
    _request,
)


def _payload_for_action(action: str) -> dict:
    alternative = (
        "intensify_observation"
        if action == "maintain_policy"
        else "maintain_policy"
    )
    return _llm_payload(
        recommended_action=action,
        alternatives=[alternative],
        requires_human_review=action == "request_human_review",
    )


def _decisions(
    actions: tuple[str, ...],
    *,
    fallback_index: int | None = None,
) -> tuple[MonitoringReviewDecision, ...]:
    view = _causal_view()
    request = _request(view)
    catalog = _catalog(view)
    decisions = []
    for index, (role, action) in enumerate(
        zip(MONITORING_REVIEW_ROLES, actions, strict=True)
    ):
        response = (
            LLMCallError("simulated policy-proposal fallback")
            if index == fallback_index
            else _payload_for_action(action)
        )
        decisions.append(
            decide_monitoring_review_action(
                agent_name=role,
                request=request,
                causal_view=view,
                evidence_records=_evidence_records(),
                evidence_catalog=catalog,
                llm_client=FakeJSONLLMClient([response]),
            )
        )
    return tuple(decisions)


class MonitoringPolicyProposalTests(unittest.TestCase):
    def setUp(self):
        self.view = _causal_view()
        self.request = _request(self.view)
        self.catalog = _catalog(self.view)

    def build(self, decisions):
        return build_monitoring_policy_proposal(
            request=self.request,
            decisions=decisions,
            evidence_catalog=self.catalog,
        )

    def test_unanimous_review_builds_one_hashed_non_applicable_proposal(self):
        decisions = _decisions(("maintain_policy",) * 7)

        proposal = self.build(decisions)

        self.assertEqual(proposal.agreement_status, "unanimous")
        self.assertEqual(proposal.aggregate_action, "maintain_policy")
        self.assertEqual(proposal.aggregate_kind, "no_change")
        self.assertEqual(proposal.status, "advisory_not_applied")
        self.assertEqual(proposal.application_status, "not_applied")
        self.assertEqual(proposal.proposal_origin, "deterministic_server")
        self.assertFalse(proposal.policy_validation_eligible)
        self.assertFalse(proposal.human_review_recommended)
        self.assertEqual(
            tuple(item.agent_name for item in proposal.contributions),
            MONITORING_REVIEW_ROLES,
        )
        self.assertTrue(
            all(item.evidence_handles == ("E02",) for item in proposal.contributions)
        )
        self.assertTrue(
            all(
                item.evidence_support_refs == decision.evidence_refs
                for item, decision in zip(
                    proposal.contributions,
                    decisions,
                    strict=True,
                )
            )
        )
        self.assertEqual(
            proposal.proposal_sha256,
            MonitoringPolicyProposal.canonical_sha256(proposal),
        )
        self.assertEqual(proposal, self.build(decisions))
        validate_monitoring_policy_proposal(
            proposal,
            request=self.request,
            decisions=decisions,
            evidence_catalog=self.catalog,
        )

        payload = proposal.model_dump(mode="json")
        serialized_keys = set(payload)
        self.assertFalse(
            serialized_keys
            & {"target_policy_kind", "parameter", "current_value", "proposed_value"}
        )

    def test_disagreement_does_not_fabricate_majority_or_aggregate_action(self):
        actions = (
            "maintain_policy",
            "intensify_observation",
            "request_human_review",
            "pause_replay",
            "insufficient_evidence",
            "maintain_policy",
            "maintain_policy",
        )
        proposal = self.build(_decisions(actions))

        self.assertEqual(proposal.agreement_status, "disagreement")
        self.assertIsNone(proposal.aggregate_action)
        self.assertIsNone(proposal.aggregate_kind)
        self.assertTrue(proposal.human_review_recommended)
        self.assertEqual(
            tuple(item.proposal_kind for item in proposal.contributions),
            (
                "no_change",
                "observation",
                "workflow",
                "workflow",
                "abstain",
                "no_change",
                "no_change",
            ),
        )
        human = proposal.contributions[2]
        self.assertEqual(
            (human.advisory_subject, human.current_state, human.proposed_state),
            ("human_review", "not_requested", "requested"),
        )

    def test_one_fallback_invalidates_aggregate_without_hiding_contributions(self):
        decisions = _decisions(("maintain_policy",) * 7, fallback_index=3)

        proposal = self.build(decisions)

        self.assertEqual(proposal.agreement_status, "invalid_review")
        self.assertIsNone(proposal.aggregate_action)
        self.assertIsNone(proposal.aggregate_kind)
        self.assertEqual(len(proposal.contributions), 7)
        self.assertEqual(
            proposal.contributions[3].generation_origin,
            "guardrail_fallback",
        )
        self.assertFalse(proposal.policy_validation_eligible)

    def test_recomputed_binding_tamper_is_rejected_by_source_validation(self):
        decisions = _decisions(("maintain_policy",) * 7)
        proposal = self.build(decisions)
        payload = proposal.model_dump(
            mode="python",
            exclude={"proposal_sha256"},
        )
        payload["session_id"] = "foreign-session"
        payload["proposal_sha256"] = MonitoringPolicyProposal.canonical_sha256(
            payload
        )
        tampered = MonitoringPolicyProposal.model_validate(payload)

        with self.assertRaisesRegex(ValueError, "deterministic projection"):
            validate_monitoring_policy_proposal(
                tampered,
                request=self.request,
                decisions=decisions,
                evidence_catalog=self.catalog,
            )

        unhashed = proposal.model_dump(mode="python")
        unhashed["human_review_recommended"] = True
        with self.assertRaisesRegex(ValidationError, "canonical payload"):
            MonitoringPolicyProposal.model_validate(unhashed)

    def test_foreign_decision_binding_and_evidence_are_rejected(self):
        decisions = list(_decisions(("maintain_policy",) * 7))
        original = decisions[0]

        foreign_payload = original.model_dump(
            mode="python",
            exclude={"decision_sha256"},
        )
        foreign_payload["child_run_id"] = "foreign-child"
        foreign_payload["decision_sha256"] = (
            MonitoringReviewDecision.canonical_sha256(foreign_payload)
        )
        decisions[0] = MonitoringReviewDecision.model_validate(foreign_payload)
        with self.assertRaisesRegex(ValueError, "proposal request"):
            self.build(tuple(decisions))

        decisions[0] = original
        evidence_payload = original.model_dump(
            mode="python",
            exclude={"decision_sha256"},
        )
        evidence_payload["evidence_refs"] = ("causal-record:foreign",)
        evidence_payload["hypothesis"] = original.hypothesis.model_copy(
            update={"evidence_refs": ["causal-record:foreign"]}
        )
        evidence_payload["decision_sha256"] = (
            MonitoringReviewDecision.canonical_sha256(evidence_payload)
        )
        decisions[0] = MonitoringReviewDecision.model_validate(evidence_payload)
        with self.assertRaisesRegex(ValueError, "outside the catalog"):
            self.build(tuple(decisions))

    def test_action_effect_tamper_is_rejected_even_with_recomputed_hash(self):
        proposal = self.build(_decisions(("maintain_policy",) * 7))
        payload = proposal.model_dump(
            mode="python",
            exclude={"proposal_sha256"},
        )
        contribution = dict(payload["contributions"][0])
        contribution["proposed_state"] = "withheld"
        payload["contributions"] = (
            contribution,
            *payload["contributions"][1:],
        )
        payload["proposal_sha256"] = MonitoringPolicyProposal.canonical_sha256(
            payload
        )

        with self.assertRaisesRegex(ValidationError, "closed action map"):
            MonitoringPolicyProposal.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
