#!/usr/bin/env python3
"""Root-owned, fixed-source Desk Matrix updater invoked by systemd.

The paired web app may create a request for one commit. It cannot choose a
repository, branch, command, or destination. This program is installed outside
the web service's writable directories by the one-time installer.
"""

from __future__ import annotations

import fcntl
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from urllib.request import urlopen

REPO_URL = "https://github.com/Matt-rempel/desk-matrix.git"
BRANCH = "main"
ROOT = Path("/var/lib/desk-matrix-updater")
REPO = ROOT / "source.git"
STATUS = ROOT / "status.json"
INSTALLED = ROOT / "installed.sha"
REQUEST = Path("/var/lib/flightboard/update-request.json")
CODE = Path("/opt/flightboard")
HELPER = Path("/opt/flightboard-updater/updater.py")
UNITS = Path("/etc/systemd/system")
UNIT_FILES = ("flightboard.service", "flightboard-web.service",
              "desk-matrix-update-apply.service", "desk-matrix-update-apply.path")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
FILE_RE = re.compile(r"[a-z][a-z0-9_]*\.py\Z")


class UpdateError(Exception):
    pass


def command(args: list[str], *, timeout: int = 120, env: dict | None = None) -> str:
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True,
                                timeout=timeout, env=env)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise UpdateError(f"{args[0]} failed: {str(detail).strip()[-240:]}") from exc
    return result.stdout.strip()


def git(*args: str, timeout: int = 120) -> str:
    env = os.environ.copy()
    env.update(HOME="/nonexistent", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
               GIT_ALLOW_PROTOCOL="https")
    return command(["git", "--git-dir", str(REPO), *args], timeout=timeout, env=env)


def write_file(path: Path, data: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".update-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def record(state: str, *, target: str = "", message: str = "") -> None:
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o755)
    payload = {"state": state, "current": current_version(), "target": target,
               "message": message[:300], "updated_at": datetime.now(timezone.utc).isoformat()}
    write_file(STATUS, json.dumps(payload) + "\n")


def current_version() -> str:
    try:
        value = INSTALLED.read_text().strip()
    except OSError:
        return ""
    return value if SHA_RE.fullmatch(value) else ""


def ensure_repo() -> None:
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o755)
    ROOT.chmod(0o755)
    if not REPO.exists():
        command(["git", "init", "--bare", str(REPO)])
        REPO.chmod(0o700)
        git("remote", "add", "origin", REPO_URL)
    elif git("remote", "get-url", "origin") != REPO_URL:
        raise UpdateError("Update source changed; a local administrator must inspect it")


def remote_head() -> str:
    ensure_repo()
    git("fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}", timeout=180)
    head = git("rev-parse", "FETCH_HEAD")
    if not SHA_RE.fullmatch(head):
        raise UpdateError("The update source did not return a commit")
    return head


def read_request() -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(REQUEST, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 256:
            raise UpdateError("Invalid update request")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            try:
                data = json.load(stream)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise UpdateError("Invalid update request") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        REQUEST.unlink(missing_ok=True)
    if not isinstance(data, dict) or set(data) != {"version"} or not isinstance(data["version"], str):
        raise UpdateError("Invalid update request")
    version = data["version"]
    if not SHA_RE.fullmatch(version):
        raise UpdateError("Invalid update version")
    return version


def extract_commit(version: str, target: Path) -> None:
    env = os.environ.copy()
    env.update(HOME="/nonexistent", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    try:
        archive = subprocess.run(["git", "--git-dir", str(REPO), "archive", "--format=tar", version],
                                 check=True, capture_output=True, timeout=60, env=env).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UpdateError("Could not stage the selected commit") from exc
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        for member in files:
            parts = PurePosixPath(member.name).parts
            if not parts or any(part in ("", ".", "..") for part in parts) or member.name.startswith("/"):
                raise UpdateError("Unsafe path in update")
            destination = target.joinpath(*parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = files.extractfile(member)
                if source is None:
                    raise UpdateError("Unreadable file in update")
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                destination.chmod(0o644)
            else:
                raise UpdateError("Links and special files are not allowed in updates")


def app_files(source: Path) -> list[str]:
    manifest = json.loads((source / "deploy-manifest.json").read_text())
    names = manifest.get("app_files") if isinstance(manifest, dict) else None
    if not isinstance(names, list) or not names or len(names) > 100:
        raise UpdateError("Invalid deployment manifest")
    if len(names) != len(set(names)) or any(not isinstance(name, str) or not FILE_RE.fullmatch(name)
                                            or name.startswith("test_") for name in names):
        raise UpdateError("Invalid application file in deployment manifest")
    for name in names:
        regular_file(source / name)
    return names


def regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise UpdateError(f"Missing or unsafe update file: {path.name}")


def stage_files(source: Path) -> list[str]:
    names = app_files(source)
    for name in UNIT_FILES:
        regular_file(source / name)
    regular_file(source / "updater.py")
    regular_file(source / "deploy-manifest.json")
    if not (source / "web").is_dir() or (source / "web").is_symlink():
        raise UpdateError("Missing web assets")
    for item in (source / "web").iterdir():
        regular_file(item)
    for required in ("index.html", "app.css", "app.js", "sw.js"):
        regular_file(source / "web" / required)
    return names


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".update-", delete=False) as stream:
        temporary = Path(stream.name)
        with source.open("rb") as input_file:
            shutil.copyfileobj(input_file, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def check_health() -> None:
    command(["runuser", "-u", "flightboard", "--", "env",
             "FLIGHTBOARD_STATE_DIR=/var/lib/flightboard", "/usr/bin/python3", "-c",
             'import sys; sys.path.insert(0,"/opt/flightboard"); import web_server'])
    command(["runuser", "-u", "flightboard", "--", "env",
             "FLIGHTBOARD_STATE_DIR=/var/lib/flightboard", "/opt/flightboard/.venv/bin/python", "-c",
             'import sys; sys.path.insert(0,"/opt/flightboard"); import rgbmatrix, flightboard, player, providers'])
    command(["systemctl", "daemon-reload"])
    command(["systemctl", "restart", "flightboard-web.service", "flightboard.service"], timeout=90)
    command(["systemctl", "is-active", "--quiet", "flightboard-web.service"])
    command(["systemctl", "is-active", "--quiet", "flightboard.service"])
    for attempt in range(10):
        try:
            with urlopen("http://127.0.0.1:8765/", timeout=3) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        if attempt < 9:
            time.sleep(1)
    raise UpdateError("The settings page did not respond after restart")


def deploy(source: Path, version: str) -> None:
    names = stage_files(source)
    previous = []
    if (CODE / "deploy-manifest.json").exists():
        try:
            previous = app_files(CODE)
        except (OSError, ValueError, UpdateError):
            previous = []
    targets = [CODE / name for name in sorted(set(names + previous))]
    targets += [CODE / "deploy-manifest.json", CODE / "web", HELPER]
    targets += [UNITS / name for name in UNIT_FILES]
    with tempfile.TemporaryDirectory(prefix="backup-", dir=ROOT) as backup_name:
        backup = Path(backup_name)
        existed = {}
        for destination in targets:
            saved = backup / destination.relative_to("/")
            existed[destination] = destination.exists()
            if destination.is_dir():
                shutil.copytree(destination, saved)
            elif destination.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, saved)
        try:
            for name in names:
                copy_file(source / name, CODE / name)
            for name in set(previous) - set(names):
                (CODE / name).unlink(missing_ok=True)
            copy_file(source / "deploy-manifest.json", CODE / "deploy-manifest.json")
            web_new = CODE / "web.new"
            if web_new.exists():
                shutil.rmtree(web_new)
            shutil.copytree(source / "web", web_new)
            if (CODE / "web").exists():
                shutil.rmtree(CODE / "web")
            web_new.rename(CODE / "web")
            copy_file(source / "updater.py", HELPER)
            for name in UNIT_FILES:
                copy_file(source / name, UNITS / name)
            check_health()
            write_file(INSTALLED, version + "\n")
        except Exception as failed:
            try:
                for destination in targets:
                    saved = backup / destination.relative_to("/")
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    elif destination.exists():
                        destination.unlink()
                    if existed[destination]:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if saved.is_dir():
                            shutil.copytree(saved, destination)
                        else:
                            shutil.copy2(saved, destination)
                if (CODE / "web.new").exists():
                    shutil.rmtree(CODE / "web.new")
                command(["systemctl", "daemon-reload"])
                command(["systemctl", "restart", "flightboard-web.service", "flightboard.service"], timeout=90)
            except Exception as rollback_failed:
                raise UpdateError(f"Install failed ({failed}); rollback also failed ({rollback_failed})") from rollback_failed
            raise


def apply() -> None:
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o755)
    with (ROOT / "update.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        wanted = ""
        try:
            wanted = read_request()
            record("installing", target=wanted, message="Fetching the selected version")
            latest = remote_head()
            if latest != wanted:
                raise UpdateError("A newer commit was pushed; refresh the page and try again")
            current = current_version()
            if current == latest:
                record("success", target=latest, message="Already up to date")
                return
            if current:
                try:
                    git("merge-base", "--is-ancestor", current, latest)
                except UpdateError as exc:
                    raise UpdateError("The main branch was rewritten; update manually") from exc
            record("installing", target=wanted, message="Checking and installing files")
            with tempfile.TemporaryDirectory(prefix="stage-", dir=ROOT) as stage_name:
                stage = Path(stage_name)
                extract_commit(latest, stage)
                deploy(stage, latest)
            record("success", target=latest, message="Update installed")
        except (UpdateError, OSError, ValueError, json.JSONDecodeError) as exc:
            record("error", target=wanted, message=str(exc))
            raise


def bootstrap(version: str) -> None:
    if not SHA_RE.fullmatch(version):
        raise UpdateError("Install from a Git checkout to enable phone updates")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o755)
    ROOT.chmod(0o755)
    write_file(INSTALLED, version + "\n")
    record("ready", message="Checking for updates")


def main() -> int:
    if os.geteuid() != 0:
        print("The updater must run as root through its systemd unit", file=sys.stderr)
        return 1
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "bootstrap":
            bootstrap(sys.argv[2])
        elif sys.argv[1:] == ["apply"]:
            apply()
        else:
            print("Usage: updater.py bootstrap COMMIT | apply", file=sys.stderr)
            return 2
    except (UpdateError, OSError) as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
