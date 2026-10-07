"""Reproduce the structural seed: python -m plane.radar.ontology.snapshot /path/to/core.yaml."""

import hashlib
import json
from pathlib import Path
import sys
import yaml

SLICE_TYPES = (
    "objective",
    "project",
    "decision",
    "action",
    "risk",
    "person",
    "document",
    "case",
    "management_item",
    "indicator",
    "commitment",
)


def build_snapshot(source: Path) -> dict:
    raw = source.read_bytes()
    document = yaml.safe_load(raw)
    ontology = document["ontology"]
    keys = set(SLICE_TYPES)
    links = {
        key: spec
        for key, spec in ontology["link_types"].items()
        if (keys.intersection(spec["domain"]) or "*" in spec["domain"])
        and (keys.intersection(spec["codomain"]) or "*" in spec["codomain"])
    }
    return {
        "version": ontology["version"],
        "source": "JMR_RADAR_ONTOLOGY/ontology/core.yaml",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "object_types": {key: ontology["object_types"][key] for key in SLICE_TYPES},
        "link_types": links,
        "vocabularies": document["vocabularies"],
        "invariants": [
            spec["check"]
            for spec in document["constraints"]["invariants"].values()
            if "check" in spec and spec["check"]["class"] in keys
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build_snapshot(Path(sys.argv[1])), ensure_ascii=False, indent=2))
