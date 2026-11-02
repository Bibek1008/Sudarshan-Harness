"""Atomic reports, schema rejection, retention and concurrent saves."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from unittest.mock import patch
from sudarshan.evaluation.reporting import ResultStore, render, validate
from tests.benchmark_examples import example
from tests.test_harness_security import WorkspaceCase


class BenchmarkReportingTests(WorkspaceCase):
    def setUp(self): super().setUp(); self.store=ResultStore(self.root)

    def test_atomic_roundtrip_and_human_report(self):
        run=example(); self.store.save(run)
        self.assertEqual(self.store.load(run["run_id"]),run)
        self.assertIn("Task success rate: 1.0",render(run))
        with self.assertRaises(FileExistsError): self.store.save(run)

    def test_corrupt_file_detected_and_preserved(self):
        run=example(); self.store.save(run)
        path=self.store.path(f"runs/{run['run_id']}.json")
        path.write_bytes(b'PRIVATE_BROKEN_JSON')
        with self.assertRaises(ValueError): self.store.load(run["run_id"])
        self.assertEqual(path.read_bytes(),b'PRIVATE_BROKEN_JSON')

    def test_unknown_payload_fields_rejected_at_all_boundaries(self):
        for where in ("root","trial","metrics","verification"):
            run=example()
            node=run if where=="root" else run["trials"][0] if where=="trial" else run["trials"][0][where]
            node["private_payload"]="PRIVATE_SECRET"
            with self.subTest(where=where),self.assertRaises(ValueError): validate(run)

    def test_summary_tampering_and_false_pass_rejected(self):
        run=example(); run["summary"]["passed"]=99
        with self.assertRaises(ValueError): validate(run)
        run=example(); run["trials"][0]["verification"]["checks"][0]["passed"]=False
        with self.assertRaises(ValueError): validate(run)

    def test_retention_removes_only_generated_result_files(self):
        store=ResultStore(self.root,retention=2)
        runs=[example() for _ in range(3)]
        for run in runs: store.save(run)
        self.assertEqual(len(list(store.path("runs").glob("*.json"))),2)
        self.assertEqual(len(list(store.path("reports").glob("*.json"))),2)

    def test_concurrent_unique_run_saves(self):
        runs=[example() for _ in range(4)]
        with self.store.locked(): pass
        with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(self.store.save,runs))
        for run in runs: self.assertEqual(self.store.load(run["run_id"])["run_id"],run["run_id"])

    def test_invalid_ids_cannot_read_other_files(self):
        for value in ("../.env","C:/secret","not-a-uuid"):
            with self.subTest(value=value),self.assertRaises(ValueError): self.store.load(value)

    def test_result_write_failure_cleans_temporary(self):
        run=example()
        with patch("sudarshan.telemetry.os.replace",side_effect=OSError("PRIVATE_SECRET")):
            with self.assertRaises(OSError): self.store.save(run)
        self.assertFalse(list(self.store.root.rglob(".telemetry-*")))
