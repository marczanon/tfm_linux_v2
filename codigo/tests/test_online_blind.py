import unittest

from codigo.app.services.online_blind import (
    assert_online_blind_payload,
    online_blind_forbidden_paths,
    sanitize_online_blind_payload,
    unsupported_official_v2_claims,
)


class OnlineBlindGuardTests(unittest.TestCase):
    def test_sanitizer_removes_nested_retrospective_fields(self):
        payload = {
            "observed": {"timestamp": "2004-02-12T10:32:39", "score": 0.2},
            "relative_life": 0.9,
            "nested": {
                "time_to_failure_seconds": 600.0,
                "failure_mode": "outer_race",
                "mean_lead_time_to_failure": 300.0,
                "target": 1,
            },
        }

        sanitized = sanitize_online_blind_payload(payload)

        self.assertEqual(
            sanitized,
            {"observed": {"timestamp": "2004-02-12T10:32:39", "score": 0.2}, "nested": {}},
        )
        self.assertEqual(online_blind_forbidden_paths(sanitized), [])
        assert_online_blind_payload(sanitized)

    def test_guard_reports_forbidden_paths(self):
        payload = {
            "runs": [
                {
                    "current": {"time_to_failure_seconds": 42.0},
                    "failure": {"time": "future"},
                }
            ]
        }

        self.assertEqual(
            online_blind_forbidden_paths(payload),
            [
                "runs[0].current.time_to_failure_seconds",
                "runs[0].failure",
            ],
        )
        with self.assertRaisesRegex(ValueError, "retrospective keys"):
            assert_online_blind_payload(payload)

    def test_official_claim_guard_accepts_explicitly_negated_diagnosis(self):
        unsupported = unsupported_official_v2_claims(
            [
                "El resultado es local y no es un diagnostico validado. "
                "La generalizacion queda fuera del alcance."
            ]
        )

        self.assertNotIn("validated_diagnosis", unsupported)

    def test_official_claim_guard_accepts_negated_coordinated_diagnosis(self):
        unsupported = unsupported_official_v2_claims(
            ["No se afirma onset fisico ni diagnostico validado."]
        )

        self.assertNotIn("validated_diagnosis", unsupported)

    def test_official_claim_guard_keeps_positive_diagnosis_blocked(self):
        unsupported = unsupported_official_v2_claims(
            ["El sistema proporciona un diagnostico validado confirmado."]
        )

        self.assertIn("validated_diagnosis", unsupported)

    def test_official_claim_guard_blocks_physical_degradation_and_lead_time_aliases(self):
        unsupported = unsupported_official_v2_claims(
            [
                "Degradacion confirmada antes del fallo al 100%.",
                "Lead time medio hasta fallo: 201600.56 segundos.",
            ]
        )

        self.assertIn("confirmed_physical_degradation", unsupported)
        self.assertIn("lead_time_to_failure", unsupported)

    def test_official_claim_guard_accepts_explicitly_negated_aliases(self):
        unsupported = unsupported_official_v2_claims(
            [
                "No se afirma una degradacion confirmada antes del fallo.",
                "No se reporta lead time medio hasta fallo; se informa del "
                "tiempo retrospectivo hasta el final registrado.",
            ]
        )

        self.assertNotIn("confirmed_physical_degradation", unsupported)
        self.assertNotIn("lead_time_to_failure", unsupported)

    def test_official_claim_guard_accepts_raw_invalid_label_limitations(self):
        unsupported = unsupported_official_v2_claims(
            [
                "Las afirmaciones de 'degradacion confirmada' o 'lead time' "
                "son invalidas. Solo se observan tendencias algoritmicas.",
                "Las afirmaciones de degradacion confirmada no son validas "
                "sin evidencia fisica externa.",
                "Correccion narrativa para eliminar afirmaciones fisicas no "
                "validadas (degradacion confirmada, lead time) y sustituirlas "
                "por magnitudes observables.",
            ]
        )

        self.assertNotIn("confirmed_physical_degradation", unsupported)
        self.assertNotIn("lead_time_to_failure", unsupported)

    def test_internal_controls_scope_accepts_operational_word_as_optional(self):
        unsupported = unsupported_official_v2_claims(
            [
                "Evaluacion aprobada por controles internos.",
                "Evaluacion aprobada por controles operativos internos.",
            ]
        )

        self.assertNotIn("approval_overclaim", unsupported)

    def test_positive_predicates_remain_blocked_after_scope_handling(self):
        physical = unsupported_official_v2_claims(
            ["Las afirmaciones de degradacion confirmada son validas con estos datos."]
        )
        retrospective_alias = unsupported_official_v2_claims(
            ["Lead time retrospectivo medio de 201600.56 segundos."]
        )
        approval = unsupported_official_v2_claims(
            ["Evaluacion aprobada para detectar el fallo fisico."]
        )

        self.assertIn("confirmed_physical_degradation", physical)
        self.assertIn("lead_time_to_failure", retrospective_alias)
        self.assertIn("approval_overclaim", approval)

    def test_negation_in_one_field_does_not_scope_a_later_positive_field(self):
        unsupported = unsupported_official_v2_claims(
            [
                "No se afirma una degradacion confirmada.",
                "Degradacion confirmada antes del fallo.",
            ]
        )

        self.assertIn("confirmed_physical_degradation", unsupported)

    def test_official_claim_guard_accepts_only_internal_approval_scope(self):
        scoped = unsupported_official_v2_claims(
            ["La ejecucion queda aprobada por controles operativos internos."]
        )
        positive = unsupported_official_v2_claims(
            ["La ejecucion queda aprobada para detectar el fallo fisico."]
        )

        self.assertNotIn("approval_overclaim", scoped)
        self.assertIn("approval_overclaim", positive)


if __name__ == "__main__":
    unittest.main()
