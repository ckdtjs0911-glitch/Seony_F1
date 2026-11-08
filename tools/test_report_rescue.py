import difflib
import subprocess
import tempfile
import unittest
from pathlib import Path

import report_rescue as rescue


class ReportRescueTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "repo"
        self.output = Path(self.folder.name) / "output"
        self.root.mkdir()
        (self.root / "tools").mkdir()
        data = self.root / "reports/weekend-1/data"
        data.mkdir(parents=True)
        (data / "1.json").write_text('{"raw":1}\n')
        self.source = (
            "LABEL = 'before'\n"
            "def load_offline(directory):\n    return []\n"
            "def render(data, output):\n    output.write_text(LABEL)\n"
        )
        (self.root / "tools/weekend_report.py").write_text(self.source)
        (self.root / "tools/build_archive.py").write_text(
            "import weekend_report as r\n"
            "def build(root):\n"
            "    (root/'index.html').write_text(r.LABEL)\n"
            "    (root/'current-year.html').write_text(r.LABEL)\n"
        )
        (self.root / "tools/test_fixture.py").write_text(
            "import unittest\nimport weekend_report as r\n"
            "class Check(unittest.TestCase):\n"
            "    def test_label(self):\n        self.assertNotEqual(r.LABEL, 'broken')\n"
        )
        for path in (
            "reports/index.html",
            "reports/current-year.html",
            "reports/weekend-1/weekend-report.html",
        ):
            (self.root / path).write_text("before")
        (self.root / ".gitignore").write_text("__pycache__/\n")
        self.git("init", "-q")
        self.git("branch", "-M", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", "--all")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True)

    def patch(self, label="after", mutate_data=False):
        new = self.source.replace("'before'", repr(label))
        if mutate_data:
            new += "    (output.parent/'data/1.json').write_text('corrupted')\n"
        return "".join(
            difflib.unified_diff(
                self.source.splitlines(True),
                new.splitlines(True),
                fromfile="a/tools/weekend_report.py",
                tofile="b/tools/weekend_report.py",
            )
        )

    def prepare(self, **kwargs):
        return rescue.prepare(self.root, self.patch(**kwargs), self.output)

    def remote(self):
        bare = Path(self.folder.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        self.git("remote", "add", "origin", str(bare))
        self.git("push", "-q", "origin", "HEAD:main")
        return bare

    def test_valid_repair_regenerates_reports_but_preserves_original_checkout(self):
        result = self.prepare()
        self.assertEqual(result["status"], "validated")
        patch = (self.output / "validated-rescue.patch").read_text()
        self.assertIn("reports/current-year.html", patch)
        self.assertIn("reports/weekend-1/weekend-report.html", patch)
        self.assertEqual(result["base_sha"], self.base)
        self.assertEqual(
            (self.root / "tools/weekend_report.py").read_text(), self.source
        )
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_failed_tests_reject_repair_without_overwriting_original(self):
        self.assertEqual(self.prepare(label="broken")["status"], "rejected")
        self.assertFalse((self.output / "validated-rescue.patch").exists())
        self.assertEqual((self.root / "reports/index.html").read_text(), "before")

    def test_raw_data_modification_during_render_is_rejected(self):
        result = self.prepare(mutate_data=True)
        self.assertEqual(result["reason"], "raw_data_or_unrelated_files_changed")
        self.assertEqual(
            (self.root / "reports/weekend-1/data/1.json").read_text(), '{"raw":1}\n'
        )

    def test_patch_cannot_change_workflow_or_raw_snapshot(self):
        patch = self.patch().replace(
            "tools/weekend_report.py", "reports/weekend-1/data/1.json"
        )
        result = rescue.prepare(self.root, patch, self.output)
        self.assertEqual(result["reason"], "outside_report_generator_scope")

    def test_empty_patch_does_not_regenerate_or_publish(self):
        self.assertEqual(
            rescue.prepare(self.root, "", self.output)["status"], "no_changes"
        )

    def test_validated_patch_is_applied_and_pushed_to_exact_base(self):
        remote = self.remote()
        self.assertEqual(self.prepare()["status"], "validated")
        result = rescue.publish(self.root, self.output, self.base)
        self.assertEqual(result["status"], "applied")
        remote_sha = subprocess.check_output(
            ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"], text=True
        ).strip()
        self.assertEqual(remote_sha, result["commit"])
        self.assertEqual((self.root / "reports/index.html").read_text(), "after")

    def test_newer_remote_commit_is_never_overwritten(self):
        self.remote()
        self.assertEqual(self.prepare()["status"], "validated")
        self.git("commit", "--allow-empty", "-qm", "newer report")
        self.git("push", "-q", "origin", "HEAD:main")
        self.git("checkout", "-q", "--detach", self.base)
        result = rescue.publish(self.root, self.output, self.base)
        self.assertEqual(
            result, {"status": "skipped", "reason": "newer_reports_already_published"}
        )
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)
        self.assertEqual((self.root / "reports/index.html").read_text(), "before")

    def test_changed_patch_fails_checksum_before_publication(self):
        self.assertEqual(self.prepare()["status"], "validated")
        (self.output / "validated-rescue.patch").write_text("tampered")
        result = rescue.publish(self.root, self.output, self.base)
        self.assertEqual(result["reason"], "patch_checksum_mismatch")


if __name__ == "__main__":
    unittest.main()
