"""Explicit denominators, missing measurements and conservative comparisons."""
from copy import deepcopy
import unittest
from sudarshan.evaluation.scoring import summarize
from sudarshan.evaluation.comparison import compare
from tests.benchmark_examples import example


class BenchmarkScoringTests(unittest.TestCase):
    def test_task_weighting_not_raw_assertion_weighting(self):
        passed=example()["trials"][0]
        failed=example("failed")["trials"][0]; failed["task_id"]="other"
        failed["verification"]["checks"] *= 10
        result=summarize([passed,failed])
        self.assertEqual(result["task_success_rate"],.5)
        self.assertEqual(result["verification_pass_rate"],.5)
        self.assertEqual(result["first_attempt_denominator"],2)

    def test_first_attempt_and_repetitions(self):
        first=example("failed")["trials"][0]
        second=example(number=2)["trials"][0]
        result=summarize([first,second])
        self.assertEqual(result["task_success_rate"],.5)
        self.assertEqual(result["first_attempt_success_rate"],0)
        self.assertEqual(result["median_duration_ms"],1000)

    def test_unavailable_metrics_not_zero(self):
        trial=example()["trials"][0]; trial["metrics"]=None
        result=summarize([trial])
        self.assertIsNone(result["average_turns"])
        self.assertIsNone(result["measured_tokens"]["input"])
        self.assertIsNone(result["estimated_total_cost"])
        self.assertEqual(result["telemetry_coverage"]["measured_trials"],0)

    def test_matching_model_comparison_and_variability(self):
        first=example(); second=example("failed")
        second["configuration"]["model"]="other-model"
        result=compare(first,second)
        self.assertTrue(result["comparable"])
        self.assertEqual(result["success_rate_delta"],-1)
        self.assertEqual(result["statistical_significance"],"not_established")

    def test_partial_telemetry_never_becomes_complete_average(self):
        first=example()["trials"][0]
        second=deepcopy(first); second["metrics"]["partial"]=True
        second["metrics"]["tokens"]["input"]=None
        second["metrics"]["token_coverage"]["input"]["measured_requests"]=0
        result=summarize([first,second])
        self.assertIsNone(result["average_turns"])
        self.assertIsNone(result["metric_averages"]["model_requests"])
        self.assertEqual(result["measured_tokens"]["input"],100)
        self.assertEqual(result["telemetry_coverage"]["tokens"]["input"],
                         {"measured_requests":1,"successful_requests_with_telemetry":2})
        self.assertEqual(result["telemetry_coverage"]["complete_trials"],1)

    def test_mismatched_limits_policy_or_fixture_flagged(self):
        first=example()
        for field,value in (("runs",2),("fingerprint","0"*64),("approval_policy","safe-deny-effects"),("engine_fingerprint","0"*64)):
            second=deepcopy(first); second["configuration"][field]=value
            result=compare(first,second)
            self.assertFalse(result["comparable"])
            self.assertIn(field,result["configuration_differences"])
            self.assertIsNone(result["success_rate_delta"])
