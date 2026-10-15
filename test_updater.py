"""Updater safety checks that run without root or network access."""

import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.code = self.root / "code"
        self.units = self.root / "units"
        self.helper = self.root / "helper" / "updater.py"
        self.private = self.root / "private"
        for directory in (self.source, self.code, self.units, self.private):
            directory.mkdir(parents=True)
        values = {"ROOT": self.private, "REPO": self.private / "repo.git",
                  "STATUS": self.private / "status.json", "INSTALLED": self.private / "installed.sha",
                  "REQUEST": self.root / "update-request.json", "CODE": self.code,
                  "HELPER": self.helper, "UNITS": self.units}
        for name, value in values.items():
            item = patch.object(updater, name, value)
            item.start()
            self.addCleanup(item.stop)

    def fixture(self):
        for directory, value in ((self.source, "new"), (self.code, "old")):
            (directory / "deploy-manifest.json").write_text(json.dumps({"app_files": ["app.py"]}))
            (directory / "app.py").write_text(value)
            web = directory / "web"
            web.mkdir()
            for name in ("index.html", "app.css", "app.js", "sw.js"):
                (web / name).write_text(value)
        (self.source / "updater.py").write_text("new")
        self.helper.parent.mkdir()
        self.helper.write_text("old")
        for name in updater.UNIT_FILES:
            (self.source / name).write_text("new")
            (self.units / name).write_text("old")

    def test_deploy_restores_prior_code_web_and_units_on_failure(self):
        self.fixture()
        with patch.object(updater, "check_health", side_effect=updater.UpdateError("unhealthy")), \
             patch.object(updater, "command", return_value=""):
            with self.assertRaisesRegex(updater.UpdateError, "unhealthy"):
                updater.deploy(self.source, "b" * 40)
        self.assertEqual((self.code / "app.py").read_text(), "old")
        self.assertEqual((self.code / "web" / "index.html").read_text(), "old")
        self.assertEqual(self.helper.read_text(), "old")
        self.assertEqual((self.units / updater.UNIT_FILES[0]).read_text(), "old")
        self.assertFalse(updater.INSTALLED.exists())

    def test_deploy_records_version_after_healthy_restart(self):
        self.fixture()
        with patch.object(updater, "check_health"):
            updater.deploy(self.source, "b" * 40)
        self.assertEqual((self.code / "app.py").read_text(), "new")
        self.assertEqual(self.helper.read_text(), "new")
        self.assertEqual(updater.INSTALLED.read_text().strip(), "b" * 40)

    def test_only_exact_commits_are_accepted_and_request_is_consumed(self):
        updater.REQUEST.write_text(json.dumps({"version": "b" * 40}))
        self.assertEqual(updater.read_request(), "b" * 40)
        self.assertFalse(updater.REQUEST.exists())
        updater.REQUEST.write_text(json.dumps({"version": "main", "command": "reboot"}))
        with self.assertRaises(updater.UpdateError):
            updater.read_request()
        self.assertFalse(updater.REQUEST.exists())
        secret = self.root / "secret"
        secret.write_text("do not follow")
        updater.REQUEST.symlink_to(secret)
        with self.assertRaises(OSError):
            updater.read_request()
        self.assertEqual(secret.read_text(), "do not follow")

    def test_archive_rejects_symlinks(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as files:
            item = tarfile.TarInfo("web/secret")
            item.type = tarfile.SYMTYPE
            item.linkname = "/etc/shadow"
            files.addfile(item)
        result = subprocess.CompletedProcess([], 0, stdout=archive.getvalue())
        with patch.object(updater.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(updater.UpdateError, "Links and special files"):
                updater.extract_commit("b" * 40, self.source)

    def test_apply_rejects_changed_remote_head_before_staging(self):
        updater.REQUEST.write_text(json.dumps({"version": "b" * 40}))
        with patch.object(updater, "remote_head", return_value="c" * 40), \
             patch.object(updater, "extract_commit") as extract:
            with self.assertRaisesRegex(updater.UpdateError, "newer commit"):
                updater.apply()
            extract.assert_not_called()
        self.assertEqual(json.loads(updater.STATUS.read_text())["state"], "error")


if __name__ == "__main__":
    unittest.main()
