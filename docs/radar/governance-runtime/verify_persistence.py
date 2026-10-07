"""Read-only assertions after the documented browser walk; run via manage.py shell."""

import json
from datetime import datetime, timezone

from plane.db.models import Project, Workspace
from plane.radar.commands.governance import GOVERNANCE_OBJECTS, GOVERNANCE_RELATIONS
from plane.radar.models import Object, PropertyValue, Relation

workspace = Workspace.objects.get(slug="radar-governance-zero")
objects = {obj.object_type.key: obj for obj in Object.objects.filter(workspace=workspace).select_related("object_type")}
assert len(objects) == 5
assert Project.objects.filter(workspace=workspace).count() == 0
expected_edits = {
    "objective": {"progress": 25},
    "project": {"description": "Sandbox controlado para validar a Governança de IA"},
    "decision": {"rationale": "Acesso centralizado e licenciamento governado para o Sandbox IA"},
    "action": {"due_date": "2026-11-03"},
    "risk": {"likelihood": 4, "score": 16},
}
values = {}
for key, title, initial in GOVERNANCE_OBJECTS:
    obj = objects[key]
    assert obj.title == title
    assert obj.created_by_id == obj.updated_by_id == workspace.owner_id
    values[key] = {
        item.definition.key: item.value
        for item in PropertyValue.objects.filter(object=obj).select_related("definition")
    }
    for prop, value in {**initial, **expected_edits[key]}.items():
        assert values[key][prop] == value, (key, prop, values[key][prop])
edges = list(Relation.objects.filter(workspace=workspace).select_related("relation_type"))
assert len(edges) == 4
actual = {(edge.source_id, edge.relation_type.key, edge.target_id) for edge in edges}
assert actual == {(objects[source].pk, key, objects[target].pk) for source, key, target in GOVERNANCE_RELATIONS}
assert all(edge.created_by_id == edge.updated_by_id == workspace.owner_id for edge in edges)
probe = Object.objects.get(workspace__slug="radar-audit-generic", object_type__key="audit_probe")
assert PropertyValue.objects.get(object=probe, definition__key="reading").value == 42
print(
    json.dumps(
        {
            "stage": "0.5 / 0.6",
            "result": "PASS WITH CAVEATS",
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "workspace": workspace.slug,
            "actor": str(workspace.owner_id),
            "plane_projects": 0,
            "objects": [
                {
                    "id": str(obj.pk),
                    "type": key,
                    "title": obj.title,
                    "version": obj.version,
                    "created_by": str(obj.created_by_id),
                    "updated_by": str(obj.updated_by_id),
                    "properties": values[key],
                }
                for key, obj in objects.items()
            ],
            "relations": [
                {
                    "id": str(edge.pk),
                    "key": edge.relation_type.key,
                    "source": str(edge.source_id),
                    "target": str(edge.target_id),
                    "created_by": str(edge.created_by_id),
                    "updated_by": str(edge.updated_by_id),
                }
                for edge in edges
            ],
            "generic_type_probe": {
                "workspace": "radar-audit-generic",
                "object": str(probe.pk),
                "type": "audit_probe",
                "reading": 42,
                "schema_setup": "test fixture, no builder",
            },
            "assertions": [
                "five_objects",
                "four_normative_edges",
                "zero_plane_projects",
                "all_five_browser_edits_persisted",
                "derived_risk_score_16",
                "human_authorship_preserved",
                "additional_type_value_persisted",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
)
