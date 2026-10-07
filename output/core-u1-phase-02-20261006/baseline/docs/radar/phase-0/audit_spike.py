"""Read-only, reproducible fork inventory. Run from any directory; JSON on stdout."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCOPES = (
    "apps/api/plane/radar",
    "apps/web/components/radar",
    "apps/web/services/radar",
    "apps/web/store/radar",
    "apps/web/app/(all)/[workspaceSlug]/(radar)",
    "apps/web/app/routes/radar.ts",
    "apps/web/vitest.radar.config.ts",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def inventory() -> dict:
    baseline = git("rev-parse", "radar-baseline")
    files = sorted(
        p
        for p in git("ls-files", "--cached", "--others", "--exclude-standard", "--", *SCOPES).splitlines()
        if Path(p).suffix in {".py", ".ts", ".tsx", ".json"}
    )
    upstream = []
    radar_tracked = []
    for line in git("diff", "radar-baseline", "--numstat").splitlines():
        added, removed, path = line.split("\t")
        row = {"path": path, "added": int(added), "removed": int(removed)}
        (radar_tracked if path == "docker-compose.radar.yml" else upstream).append(row)
    imports: dict[str, list[str]] = {}
    for path in files:
        if Path(path).suffix not in {".tsx", ".ts"} or ".test." in path or "/spike/" in path:
            continue
        for module in re.findall(r'from\s+["\']([^"\']+)["\']', (ROOT / path).read_text()):
            if module.startswith(("@makeplane/propel", "@plane/blocks", "@plane/editor", "@/components/")):
                if "/radar/" not in module:
                    imports.setdefault(module, []).append(path)
    snapshot_path = ROOT / "apps/api/plane/radar/ontology/core-3.2.0.json"
    snapshot = json.loads(snapshot_path.read_text())
    return {
        "baseline": baseline,
        "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "upstream_touch_points": upstream,
        "upstream_totals": {
            "files": len(upstream),
            "added": sum(row["added"] for row in upstream),
            "removed": sum(row["removed"] for row in upstream),
        },
        "radar_tracked_delta": radar_tracked,
        "radar_files": files,
        "radar_totals": {
            "files": len(files),
            "lines": sum(len((ROOT / path).read_text().splitlines()) for path in files),
            "test_files": sum("/tests/test_" in path or ".test." in path for path in files),
            "migrations": sum("/migrations/" in path and Path(path).name != "__init__.py" for path in files),
        },
        "reused_imports_in_real_ui": dict(sorted(imports.items())),
        "ontology": {
            "version": snapshot["version"],
            "source_sha256": snapshot["sha256"],
            "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        },
        "scope": "Working tree vs radar-baseline; code includes tests/config/seed, excludes docs/screenshots/mock data artifacts",
        "delivery": "Local uncommitted implementation; no merge or deployment",
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))
