"""Opt-in LIVE Docker daemon tests. No mocked execution and no host secrets."""
import json
import os
from pathlib import Path
import shlex
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from sudarshan.execution.base import ExecutionTimeout
from sudarshan.execution.process import run_owned, trusted_executable
from sudarshan.execution.sandbox import SandboxedExecutionBackend

IMAGE = "python:3.12-slim"


class LiveDockerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("SUDARSHAN_DOCKER_INTEGRATION") != "1":
            raise unittest.SkipTest("LIVE Docker not executed: opt-in flag not set")
        cls.client = trusted_executable("docker", Path.cwd())
        if not cls.client:
            raise unittest.SkipTest("LIVE Docker not executed: trusted Docker client unavailable")
        info = run_owned([cls.client, "info", "--format", "{{.OSType}}"], timeout=20)
        if info.returncode:
            raise unittest.SkipTest("LIVE Docker not executed: daemon unavailable")
        if info.stdout.strip() != "linux":
            raise unittest.SkipTest("LIVE Docker not executed: Linux container daemon required")
        # Once daemon availability is established, image/runtime errors FAIL.
        pull = run_owned([cls.client, "pull", IMAGE], timeout=180)
        if pull.returncode:
            raise RuntimeError("Docker available but trusted test image pull failed")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o755)
        self.backend = SandboxedExecutionBackend(self.root, docker_executable=self.client)
        self.names = []
        from sudarshan.execution import sandbox
        actual = sandbox.run_owned
        self.launched = threading.Event()
        def observe(arguments, **kwargs):
            if "--name" in arguments:
                self.names.append(arguments[arguments.index("--name") + 1])
                self.launched.set()
            return actual(arguments, **kwargs)
        # An argv observer only: every Docker call still executes on the daemon.
        observer = patch.object(sandbox, "run_owned", side_effect=observe)
        observer.start()
        self.addCleanup(observer.stop)
        self.addCleanup(self.cleanup_owned)

    def cleanup_owned(self):
        for name in self.names:
            run_owned([self.client, "rm", "-f", name], timeout=20)

    def assert_removed(self):
        for name in self.names:
            result = run_owned([self.client, "ps", "-a", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"], timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "", "test-owned container survived")

    def test_live_nonroot_readonly_network_capabilities_and_success_cleanup(self):
        code = """import json, os, socket
try:
    open('/phase3-root-write-test', 'w').close()
    readonly = False
except OSError:
    readonly = True
caps = next(line.split()[1] for line in open('/proc/self/status') if line.startswith('CapEff:'))
print(json.dumps({'uid':os.getuid(), 'readonly':readonly, 'interfaces':socket.if_nameindex(), 'caps':caps}))
"""
        result = self.backend.execute("python -c " + shlex.quote(code), timeout=30)
        self.assertEqual(result.exit_code, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertNotEqual(values["uid"], 0)
        self.assertTrue(values["readonly"])
        self.assertEqual([name for _, name in values["interfaces"]], ["lo"])
        self.assertEqual(int(values["caps"], 16), 0)
        self.assert_removed()

    def test_live_resource_settings_and_timeout_cleanup(self):
        errors = []
        def work():
            try:
                self.backend.execute("sleep 30", timeout=20)
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=work)
        worker.start()
        try:
            self.assertTrue(self.launched.wait(10), "Docker client not launched")
            deadline = time.monotonic() + 10
            inspect = None
            while time.monotonic() < deadline:
                result = run_owned([self.client, "inspect", self.names[0]], timeout=10)
                if result.returncode == 0:
                    inspect = json.loads(result.stdout)[0]
                    break
                time.sleep(.05)
            self.assertIsNotNone(inspect, "container never became inspectable")
            config = inspect["HostConfig"]
            self.assertTrue(config["ReadonlyRootfs"])
            self.assertFalse(config["Privileged"])
            self.assertEqual(config["NetworkMode"], "none")
            self.assertEqual(config["PidsLimit"], 64)
            self.assertEqual(config["Memory"], 512 * 1024 * 1024)
            self.assertEqual(config["NanoCpus"], 1000000000)
            self.assertIn("ALL", [cap.upper() for cap in config["CapDrop"]])
        finally:
            worker.join(40)
        self.assertFalse(worker.is_alive(), "Docker worker did not finish")
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ExecutionTimeout)
        self.assert_removed()

    def test_live_failure_cleanup(self):
        result = self.backend.execute("exit 7", timeout=30)
        self.assertEqual(result.exit_code, 7)
        self.assert_removed()
