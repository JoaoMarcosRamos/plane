"""Opt-in Phase 0.5 fixture, using the same commands as human API writes."""

from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError

from plane.db.models import Workspace
from plane.radar.models import Object, ObjectType, PropertyDefinition, RelationType
from .actor import Actor
from .objects import _authorize, create_object
from .semantic import initialize_semantic_model, set_property_value, create_relation
from .execution import run_internal


GOVERNANCE_OBJECTS = (
    (
        "objective",
        "Implantar Governança de IA",
        {
            "status": "active",
            "outcome": "Uso de IA governado, com decisões e riscos rastreáveis",
            "start_date": "2026-10-03",
            "due_date": "2026-12-31",
            "progress": 10,
        },
    ),
    ("project", "Sandbox IA", {"status": "active", "description": "Validar IA em ambiente controlado"}),
    (
        "decision",
        "Adotar GitHub Enterprise",
        {
            "status": "proposed",
            "context": "Governar o acesso às ferramentas do Sandbox IA",
            "decision": "Adotar GitHub Enterprise para o sandbox",
            "rationale": "Centralizar acesso e administração de licenças",
            "consequences": ["Negociar licenças", "Revisar prazo de contratação"],
        },
    ),
    (
        "action",
        "Negociar licenças",
        {"status": "todo", "description": "Negociar condições e prazo com o fornecedor", "due_date": "2026-10-30"},
    ),
    (
        "risk",
        "Licenciamento pode atrasar",
        {"status": "monitoring", "description": "Contratação pode atrasar o sandbox", "likelihood": 3, "impact": 4},
    ),
)

GOVERNANCE_RELATIONS = (
    ("project", "advances", "objective"),
    ("project", "contains", "decision"),
    ("project", "contains", "action"),
    ("risk", "threatens", "objective"),
)


@transaction.atomic
def create_governance_scenario(*, actor: Actor, workspace: Workspace) -> dict[str, UUID]:
    return run_internal(
        actor=actor,
        workspace=workspace,
        name="CreateGovernanceScenario",
        operation=lambda: _create_scenario(actor=actor, workspace=workspace),
    )


def _create_scenario(*, actor: Actor, workspace: Workspace) -> dict[str, UUID]:
    """Create once in a workspace without RADAR objects; never resolve identity by title.

    The workspace lock serializes concurrent fixture runs. Existing objects, including
    tombstones, cause rejection; a rerun must use a new dedicated workspace.
    """
    _authorize(actor, workspace)
    Workspace.objects.select_for_update().get(pk=workspace.pk)
    if Object.all_objects.filter(workspace=workspace).exists():
        raise ValidationError("The governance scenario requires a workspace without RADAR objects.")
    initialize_semantic_model(actor=actor, workspace=workspace)
    ids: dict[str, UUID] = {}
    for key, title, properties in GOVERNANCE_OBJECTS:
        selected = ObjectType.objects.get(workspace=workspace, key=key, is_active=True)
        obj = create_object(
            actor=actor,
            workspace=workspace,
            object_type=selected.pk,
            title=title,
            content=f"<p>Cenário demonstrativo de Governança de IA: {title}.</p>",
            properties={
                prop: value
                for prop, value in properties.items()
                if prop in {"description", "context", "decision", "rationale"}
            },
        )
        ids[key] = obj.pk
        for prop_key, value in properties.items():
            definition = PropertyDefinition.objects.get(workspace=workspace, object_type=selected, key=prop_key)
            set_property_value(
                actor=actor, workspace=workspace, object_id=obj.pk, definition_id=definition.pk, value=value
            )
    for source, key, target in GOVERNANCE_RELATIONS:
        relation_type = RelationType.objects.get(workspace=workspace, key=key, is_active=True)
        create_relation(
            actor=actor,
            workspace=workspace,
            relation_type_id=relation_type.pk,
            source_id=ids[source],
            target_id=ids[target],
        )
    return ids
