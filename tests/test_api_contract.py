"""三方契约：前端调用、后端路由、OpenAPI 文档必须对得上。"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/cover_pipeline/server/app.py"
JS = ROOT / "src/cover_pipeline/server/static/app.js"


def backend_routes() -> set[str]:
    text = APP.read_text(encoding="utf-8")
    routes = set(re.findall(r'path == "(/api/[^"]+)"', text))
    routes |= {r.rstrip("/") for r in re.findall(r'path\.startswith\("(/api/[^"]+)"\)', text)}
    return routes


def frontend_calls() -> set[str]:
    text = JS.read_text(encoding="utf-8")
    calls = set(re.findall(r'api\(\s*"(/api/[^"?]+)', text))
    calls |= set(re.findall(r'api\(\s*`(/api/[^`?$]+)', text))
    return {c.rstrip("/") for c in calls}


def documented() -> set[str]:
    text = APP.read_text(encoding="utf-8")
    return set(re.findall(r'"(/api/[^"]+)":\s*\{', text))


class ApiContractTest(unittest.TestCase):
    def test_frontend_calls_have_backend(self):
        routes = backend_routes()
        missing = sorted(c for c in frontend_calls()
                         if not any(c == r or c.startswith(r) for r in routes))
        self.assertEqual(missing, [], f"前端调用了不存在的接口：{missing}")

    def test_routes_are_documented(self):
        routes, docs = backend_routes(), documented()
        missing = sorted(r for r in routes if r not in docs)
        self.assertEqual(missing, [], f"接口没有写进 OpenAPI：{missing}")


if __name__ == "__main__":
    unittest.main()
