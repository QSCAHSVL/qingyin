"""回归：`POST /api/jobs/{id}/retry` 曾经必然 500。

原因：`JobManager.get()` 返回的是 `as_dict()`（dict，而且不含 payload），
`server/services/jobs.py::retry_job` 却按对象用（`job.kind`、`getattr(job, "payload", None)`）→ AttributeError。
这个 bug 是第 6 轮拆包前就有的，第 7 轮顺手补上测试。

注意：这里**直接往 JobManager 里塞 Job 对象**，不走 submit()——submit 会起后台线程写状态 JSON，
跟临时目录清理抢时序（Windows 上偶发「目录不是空的」），测试里不该有这种不确定性。
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cover_pipeline.jobs.manager import Job, JobManager
from cover_pipeline.server.services import jobs as jobs_service


class RetryJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = JobManager(self.root / "jobs")
        self.state = SimpleNamespace(jobs=self.manager)
        self._seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def _job(self, kind: str, payload: dict) -> Job:
        """直接注册一个已完成的 Job（不起线程、不落盘）。"""
        self._seq += 1
        job = Job(id=f"test{self._seq}", kind=kind, label="测试任务", payload=payload)
        job.status = "succeeded"
        with self.manager._lock:
            self.manager._jobs[job.id] = job
        return job

    def test_get_obj_exposes_payload_but_get_does_not(self):
        job = self._job("sing", {"song": "东南苦行山", "voice": "yuzhou"})
        obj = self.manager.get_obj(job.id)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.kind, "sing")
        self.assertEqual(obj.payload["song"], "东南苦行山")
        # as_dict() 不带 payload —— 这正是当初按对象用会炸的原因
        self.assertNotIn("payload", self.manager.get(job.id))

    def test_get_obj_unknown_returns_none(self):
        self.assertIsNone(self.manager.get_obj("不存在"))

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
