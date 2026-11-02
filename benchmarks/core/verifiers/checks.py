"""Independent checks; invoked only AFTER the agent process has stopped.

Keep this file outside trial workspaces. It is not a hostile-code sandbox.
"""
import ast
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


def raises_value(operation):
    try: operation()
    except ValueError: return True
    return False


def verify(task, root):
    sys.path.insert(0, str(root))
    module = importlib.import_module({"config": "settings", "orders": "orders", "csv": "parse", "ledger": "storage"}.get(task, "solution"))
    checks = []
    def check(name, operation):
        try: passed = bool(operation())
        except Exception: passed = False
        checks.append({"id": name, "passed": passed})
    if task == "slug":
        check("ordinary", lambda: module.slugify("Hello World") == "hello-world")
        check("whitespace", lambda: module.slugify(" A  B\tC ") == "a-b-c")
        check("empty", lambda: module.slugify("  ") == "")
    elif task == "ledger":
        path = root / "check-ledger.json"
        def roundtrip():
            module.save(path, [2, 5]); return module.load(path) == [2, 5] and module.load(path) == [2, 5]
        check("roundtrip", roundtrip)
        check("missing", lambda: module.load(root / "not-present.json") == [])
        check("application", lambda: importlib.import_module("app").total(path) == 7)
    elif task == "median":
        check("even", lambda: module.median([8, 2, 4, 6]) == 5)
        def original():
            values = [9, 1, 3]; result = module.median(values); return result == 3 and values == [9, 1, 3]
        check("odd_unchanged", original)
        check("empty", lambda: raises_value(lambda: module.median([])))
    elif task == "tests":
        tests = importlib.import_module("test_solution")
        original = module.clamp
        def run(replacement):
            module.clamp = replacement
            # Reload allows both `from solution import clamp` and module references.
            importlib.reload(tests)
            suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            return result.testsRun >= 3 and result.wasSuccessful()
        check("tests_pass", lambda: run(original))
        def mutant(replacement):
            module.clamp = replacement
            importlib.reload(tests)
            result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
            # Syntax/import errors do not qualify as detecting a behavioral mutant.
            return result.testsRun >= 3 and bool(result.failures) and not result.errors
        check("reject_low_mutant", lambda: mutant(lambda value, low, high: min(high, value)))
        check("reject_reversed_mutant", lambda: mutant(lambda value, low, high: max(low, min(high, value))))
        module.clamp = original
    elif task == "ranges":
        check("inclusive", lambda: module.parse_range("2:5") == [2, 3, 4, 5])
        check("negative", lambda: module.parse_range("-2:0") == [-2, -1, 0])
        check("invalid", lambda: all(raises_value(lambda value=value: module.parse_range(value)) for value in ("4:1", "a:3", "1:2:3")))
    elif task == "port":
        check("valid", lambda: module.parse_port("443") == 443 and module.parse_port(65535) == 65535)
        check("range", lambda: all(raises_value(lambda value=value: module.parse_port(value)) for value in (0, 65536, "-1")))
        check("types", lambda: all(raises_value(lambda value=value: module.parse_port(value)) for value in (True, 4.2, " 80", "+80", "８０")))
    elif task == "config":
        check("default", lambda: module.load_config('{"name":"app"}') == {"name": "app", "retries": 3})
        check("configured", lambda: module.load_config('{"name":"app","retries":0}')["retries"] == 0)
        check("regression", lambda: all(raises_value(lambda value=value: module.load_config(value)) for value in ('{}', '{"name":" "}', '{"name":"app","retries":true}', '{"name":"app","retries":6}')))
    elif task == "orders":
        check("normal", lambda: module.total([(4, 2), (3, 1)]) == 11)
        check("discount_empty", lambda: abs(module.total([(10, 2)], True) - 18) < 1e-9 and module.total([], True) == 0)
        check("single_loop", lambda: sum(isinstance(n, (ast.For, ast.ListComp, ast.GeneratorExp)) for n in ast.walk(ast.parse((root / "orders.py").read_text()))) == 1)
    elif task == "unique":
        check("stable", lambda: module.unique([3, 1, 3, 2, 1]) == [3, 1, 2])
        check("unhashable", lambda: module.unique([[1], [2], [1]]) == [[1], [2]])
        def original():
            values = [2, 1, 2]; module.unique(values); return values == [2, 1, 2]
        check("unchanged", original)
    elif task == "csv":
        stats = importlib.import_module("stats")
        check("parse", lambda: module.parse_csv(" 1, -2,3 ") == [1, -2, 3])
        check("summary", lambda: stats.summarize("2,4,6") == {"count": 3, "sum": 12, "mean": 4})
        check("errors_empty", lambda: stats.summarize(" ") == {"count": 0, "sum": 0, "mean": None} and raises_value(lambda: module.parse_csv("1,x")))
    else: raise ValueError("unknown trusted verifier")
    return checks


if __name__ == "__main__":
    try:
        checks = verify(sys.argv[1], Path(sys.argv[2]).resolve())
        print(json.dumps({"schema_version": 1, "checks": checks}))
    except (ImportError, AttributeError, SyntaxError):
        print(json.dumps({"schema_version": 1, "candidate_error": True}))
    except BaseException:
        # Never serialize exceptions, source, actual values or assertion output.
        print(json.dumps({"schema_version": 1, "infrastructure_error": True}))
