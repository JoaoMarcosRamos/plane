"""Apply the reviewed transfer; preserve source unless target verification passes."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

backup = Path(__file__).resolve().parent
manifest = json.loads((backup / "manifest.json").read_text())
source = Path(manifest["source"])
destination = Path(manifest["destination"])
stage = Path(manifest["stage"])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def verify_source():
    assert git(source, "rev-parse", "HEAD").decode().strip() == manifest["head"]
    assert not git(source, "diff", "--cached", "--name-only")
    for item in manifest["files"]:
        assert digest(source / item["path"]) == item["sha256"], item["path"]
        assert digest(backup / "integration" / item["path"]) == item["sha256"]
        if item["tracked"]:
            assert digest(backup / "baseline" / item["path"]) == item["baseline_sha256"]


verify_source()
assert git(destination, "rev-parse", "HEAD").decode().strip() == manifest["head"]
assert not git(destination, "status", "--porcelain"), "Destination has new local changes"
suite = ET.parse(backup / "pytest.xml").find("testsuite")
assert suite is not None and suite.attrib["tests"] == "93"
assert suite.attrib["errors"] == suite.attrib["failures"] == "0"
items = manifest["files"] + manifest["extra_destination_files"]
for item in items:
    expected = item.get("baseline_sha256", item.get("before_sha256"))
    assert digest(destination / item["path"]) == expected, item["path"]
    assert digest(stage / item["path"]) == item["prepared_sha256"], item["path"]

for item in items:
    target = destination / item["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(stage / item["path"], target)
for item in items:
    assert digest(destination / item["path"]) == item["prepared_sha256"], item["path"]

# Validate imports and behavior in the real destination before restoring source.
environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
command = [str(destination / ".venv/bin/python"), "-m", "pytest",
           "-p", "no:cacheprovider", "tests/unit/test_radar_command_runtime.py",
           "tests/integration/test_radar_approval_flow.py", "tests/unit/test_migrations.py",
           f"--basetemp={stage / 'destination-test-temp'}",
           f"--junitxml={backup / 'destination-pytest.xml'}"]
result = subprocess.run(command, cwd=destination, env=environment,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(backup / "destination-pytest.log").write_bytes(result.stdout)
if result.returncode:
    raise SystemExit("Destination tests failed; original integration preserved. See backup log.")
subprocess.run(["git", "-C", str(destination), "diff", "--check"], check=True)

# Refuse restoration if another process modified either copy during validation.
verify_source()
for item in items:
    assert digest(destination / item["path"]) == item["prepared_sha256"]
for item in manifest["files"]:
    path = source / item["path"]
    if item["tracked"]:
        path.write_bytes((backup / "baseline" / item["path"]).read_bytes())
    else:
        path.unlink()

for item in manifest["files"]:
    assert digest(source / item["path"]) == item["baseline_sha256"]
result = {
    "destination": str(destination),
    "transferred_integration_files": len(manifest["files"]),
    "additional_documentation_files": len(manifest["extra_destination_files"]),
    "source_status": git(source, "status", "--porcelain").decode(),
    "destination_status": git(destination, "status", "--porcelain").decode(),
    "destination_tests": ET.parse(backup / "destination-pytest.xml").find("testsuite").attrib,
}
(backup / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
