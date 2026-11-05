"""回归：`POST /api/jobs/{id}/retry` 曾经必然 500。

原因：`JobManager.get()` 返回的是 `as_dict()`（dict，而且不含 payload），
`server/services/jobs.py::retry_job` 却按对象用（`job.kind`、`getattr(job, "payload", None)`）→ AttributeError。
这个 bug 是第 6 轮拆包前就有的，第 7 轮顺手补上测试。
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cover_pipeline import config as config_mod
from cover_pipeline.jobs.manager import JobManager
from cover_pipeline.server.services import jobs as jobs_service


class RetryJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # submit() 会往 config.ROOT/logs 写日志，测试里指到临时目录，别弄脏仓库
        self._root_patch = mock.patch.object(config_mod, "ROOT", self.root)
        self._root_patch.start()
        self.manager = JobManager(self.root / "jobs")
        self.state = SimpleNamespace(jobs=self.manager)

    def tearDown(self):
        self._root_patch.stop()
        self.tmp.cleanup()

    def _job(self, kind: str, payload: dict):
        return self.manager.submit(kind, "测试任务", lambda job: {"ok": True}, payload=payload)

    def test_get_obj_exposes_payload_but_get_does_not(self):
        job = self._job("sing", {"song": "东南苦行山", "voice": "yuzhou"})
        obj = self.manager.get_obj(job.id)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.kind, "sing")
        self.assertEqual(obj.payload["song"], "东南苦行山")
        # as_dict() 不带 payload —— 这正是当初按对象用会炸的原因
        self.assertNotIn("payload", self.manager.get(job.id))

    def test_retry_replays_original_payload(self):
        payload = {"song": "东南苦行山", "voice": "yuzhou", "clip": 45}
        job = self._job("sing", payload)
        with mock.patch.object(jobs_service, "submit_sing", return_value={"job": {"id": "new"}}) as patched:
            result = jobs_service.retry_job(self.state, job.id)
        self.assertEqual(result, {"job": {"id": "new"}})
        patched.assert_called_once()
        self.assertEqual(patched.call_args.args[1], payload)

    def test_retry_unknown_job_raises(self):
        with self.assertRaises(ValueError):
            jobs_service.retry_job(self.state, "不存在的任务")

    def test_retry_unsupported_kind_raises(self):
        job = self._job("backup", {})
        with self.assertRaises(ValueError):
            jobs_service.retry_job(self.state, job.id)


if __name__ == "__main__":
    unittest.main()
