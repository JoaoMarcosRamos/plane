import subprocess
import sys

files = [
    "plane/radar/commands/capabilities.py",
    "plane/radar/commands/descriptors.py",
    "plane/radar/commands/rules.py",
    "plane/radar/commands/handlers.py",
    "plane/radar/commands/inputs.py",
    "plane/radar/commands/operations.py",
    "plane/radar/commands/primitives_semantic.py",
    "plane/radar/commands/execution.py",
    "plane/radar/commands/legacy_replay.py",
    "plane/radar/commands/schema.py",
    "plane/radar/commands/objects.py",
    "plane/radar/models/core.py",
    "plane/radar/mutation.py",
    "plane/radar/ontology/package.py",
    "plane/radar/migrations/0013_type_descriptors.py",
    "plane/radar/api/schema_views.py",
    "plane/radar/api/serializers.py",
    "plane/radar/api/views.py",
    "plane/radar/tests/test_core_u1_phase03bc.py",
    "plane/radar/tests/test_core_u0.py",
    "plane/radar/tests/test_commands.py",
]
mode = sys.argv[1] if len(sys.argv) > 1 else "fix"
if mode == "check":
    subprocess.run(["ruff", "format", "--check", *files], check=True)
    subprocess.run(["ruff", "check", *files], check=True)
else:
    subprocess.run(["ruff", "format", *files], check=True)
    subprocess.run(["ruff", "check", "--fix", *files], check=True)
