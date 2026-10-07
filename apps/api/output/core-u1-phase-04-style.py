import subprocess
import sys

files = [
    "plane/radar/capacities.py",
    "plane/radar/commands/capabilities.py",
    "plane/radar/commands/descriptors.py",
    "plane/radar/commands/handlers.py",
    "plane/radar/commands/inputs.py",
    "plane/radar/commands/rules.py",
    "plane/radar/commands/schema.py",
    "plane/radar/ontology/package.py",
    "plane/radar/migrations/0014_type_presentation.py",
    "plane/radar/api/semantic_views.py",
    "plane/radar/api/urls.py",
    "plane/radar/tests/test_core_u1_phase04.py",
]
if (sys.argv[1:] or ["fix"])[0] == "check":
    subprocess.run(["ruff", "format", "--check", *files], check=True)
    subprocess.run(["ruff", "check", *files], check=True)
else:
    subprocess.run(["ruff", "format", *files], check=True)
    subprocess.run(["ruff", "check", "--fix", *files], check=True)
