"""Risk Review never writes domain until a human accepts a saved command."""

from copy import deepcopy
from uuid import uuid4

import pytest

from plane.radar.ontology.schema import load_schema
from plane.radar.commands.runtime_control import bind_runtime_object
from plane.radar.models import (
    ActorGrant,
    AgentConfiguration,
    Object,
    Relation,
    Provenance,
    RiskReview,
    RiskReviewProposal,
    CommandExecution,
)
from plane.radar.api import agent_views, risk_review_views
from .test_agent_runtime import product, endpoint as runtime_endpoint  # noqa: F401
from .test_runtime_contract import runtime  # noqa: F401
from .test_commands import create
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def scenario(product, monkeypatch):  # noqa: F811
    ctx = product[0][0]
    grant = ActorGrant.objects.get(actor_id=product[1].actor_id)
    grant.commands = [*grant.commands, "CreateAction"]
    fixture_write(lambda: grant.save())
    risk = create(ctx, "risk", description="Licenciamento pode atrasar a governança de IA e o Sandbox IA")
    objective = create(ctx, "objective", description="Implantar Governança de IA depende do licenciamento")
    project = create(ctx, "project", description="Sandbox IA depende do licenciamento")
    fixture_write(lambda: Object.objects.filter(pk=risk.pk).update(title="Licenciamento pode atrasar"))
    fixture_write(lambda: Object.objects.filter(pk=objective.pk).update(title="Implantar Governança de IA"))
    fixture_write(lambda: Object.objects.filter(pk=project.pk).update(title="Sandbox IA"))
    for obj in [risk, objective, project]:
        bind_runtime_object(
            actor=ctx[5],
            workspace=ctx[3],
            object_id=obj.pk,
            external_id=f"{load_schema()['object_types'][obj.object_type.key]['prefix']}-20261005-{uuid4().hex[:6].upper()}",
            context=product[1].context,
        )
    sent = []
    monkeypatch.setattr(
        agent_views,
        "runtime_request",
        lambda path, data, **kw: (
            sent.append(data) or {"contract_version": "1.0", "run_id": data["run_id"], "status": "queued"}
        ),
    )
    response = product[2].post(
        runtime_endpoint(product, "runs"),
        {
            "binding_id": str(product[1].pk),
            "root_ids": [str(risk.pk), str(objective.pk), str(project.pk)],
            "prompt": "Risk Review",
            "skill": "risk_review",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="risk-review",
    )
    assert response.status_code == 202, response.data
    snapshot = sent[0]["context"]

    def evidence(obj):
        source = next(o for o in snapshot["objects"] if o["id"] == str(obj.pk))
        return {"object_id": source["id"], "version": source["version"], "field": "title", "quote": source["title"]}

    output = {
        "summary": "Licenciamento pode afetar a entrega; inferência sujeita à revisão humana.",
        "suggestions": [
            {
                "explanation": "A dependência de licenciamento pode ameaçar a implantação.",
                "suggested_relation": {
                    "source_id": str(risk.pk),
                    "target_id": str(objective.pk),
                    "relation": "threatens",
                },
                "suggested_action": {
                    "title": "Validar o licenciamento",
                    "description": "Identificar prazo e alternativas para evitar atraso",
                    "next_step": "Consultar a equipe de licenciamento",
                    "mitigates_risk_id": str(risk.pk),
                },
                "confidence": 0.8,
                "evidence": [evidence(risk), evidence(objective)],
                "context_used": [],
            }
        ],
    }
    remote = {
        "contract_version": "1.0",
        "run_id": sent[0]["run_id"],
        "status": "completed",
        "result": {
            "risk_review": output,
            "text": output["summary"],
            "sources": [{"id": o["id"], "version": o["version"]} for o in snapshot["objects"]],
            "truncated": snapshot["truncated"],
        },
    }
    monkeypatch.setattr(risk_review_views, "runtime_request", lambda *a, **kw: remote)
    return product, response.data["run_id"], output, snapshot, risk, objective, project, remote


def url(scenario, suffix=""):
    return f"/api/workspaces/{scenario[0][0][0][3].slug}/radar/risk-reviews/{suffix}"


def prepare(scenario):
    return scenario[0][2].post(url(scenario), {"run_id": scenario[1]}, format="json")


def resolve(scenario, proposal, decision, **extra):
    return scenario[0][2].post(
        url(scenario, f"{proposal['id']}/resolve/"),
        {
            "decision": decision,
            "rationale": "Human reviewed the evidence",
            "intent_hash": proposal["intent_hash"],
            **extra,
        },
        format="json",
    )


def test_prepare_preview_no_domain_writes_and_refresh_persists(scenario, monkeypatch):
    count, relations = Object.objects.count(), Relation.objects.count()
    first = prepare(scenario)
    assert first.status_code == 200, first.data
    assert Object.objects.count() == count and Relation.objects.count() == relations
    assert {p["command_name"] for p in first.data["proposals"]} == {"LinkObjects", "CreateAction"}
    assert all(p["preview"]["preview_only"] and p["status"] == "pending_approval" for p in first.data["proposals"])
    monkeypatch.setattr(risk_review_views, "runtime_request", lambda *a, **kw: pytest.fail("Repeated model retrieval"))
    second = prepare(scenario)
    assert second.data == first.data
    listed = scenario[0][2].get(url(scenario))
    assert listed.status_code == 200 and len(listed.data["proposals"]) == 2
    assert RiskReview.objects.count() == 1


def test_accept_relation_command_provenance_and_replay(scenario):
    proposals = prepare(scenario).data["proposals"]
    relation = next(p for p in proposals if p["component"] == "relation")
    accepted = resolve(scenario, relation, "accept")
    assert accepted.status_code == 200, accepted.data
    assert accepted.data["status"] == "executed"
    assert Relation.objects.filter(source=scenario[4], target=scenario[5], relation_type__key="threatens").count() == 1
    trace = Provenance.objects.get(pk=accepted.data["result"]["provenance_id"])
    assert trace.actor_type == "agent" and str(trace.run_id) == scenario[1] and trace.confidence == 0.8
    assert trace.context["assertion"]["kind"] == "inferred" and trace.context["approver_id"] == str(
        scenario[0][0][0][0].pk
    )
    assert resolve(scenario, relation, "accept").data["result"] == accepted.data["result"]
    # Existing Object Page relation endpoint exposes the persisted outcome.
    page = scenario[0][2].get(f"/api/workspaces/{scenario[0][0][0][3].slug}/radar/objects/{scenario[4].pk}/relations/")
    assert page.status_code == 200 and "threatens" in str(page.data)


def test_action_separate_stale_then_edit_preview_then_accept(scenario):
    proposals = prepare(scenario).data["proposals"]
    relation, action = [next(p for p in proposals if p["component"] == kind) for kind in ["relation", "action"]]
    assert resolve(scenario, relation, "accept").status_code == 200
    assert resolve(scenario, action, "accept").status_code == 409
    count = Object.objects.count()
    edited = resolve(
        scenario, action, "edit", edited_input={**action["input"], "title": "Confirmar prazo de licenciamento"}
    )
    assert edited.status_code == 200, edited.data
    assert edited.data["revision"] == 2 and edited.data["previous_id"] == action["id"]
    assert Object.objects.count() == count
    assert resolve(scenario, action, "edit", edited_input=edited.data["input"]).data["id"] == edited.data["id"]
    result = resolve(scenario, edited.data, "accept")
    assert result.status_code == 200, result.data
    assert Object.objects.count() == count + 1
    assert (
        Relation.objects.filter(
            target=scenario[4], source__title="Confirmar prazo de licenciamento", relation_type__key="mitigates"
        ).count()
        == 1
    )
    assert resolve(scenario, edited.data, "accept").data["result"] == result.data["result"]
    assert resolve(scenario, action, "accept").status_code == 409


def test_reject_feedback_preserves_domain_and_original_intention(scenario):
    proposal = prepare(scenario).data["proposals"][0]
    count, relation_count = Object.objects.count(), Relation.objects.count()
    response = resolve(scenario, proposal, "reject")
    assert response.status_code == 200 and response.data["status"] == "rejected", response.data
    assert Object.objects.count() == count and Relation.objects.count() == relation_count
    feedback = Provenance.objects.filter(command_name="ReviewCommand", run_id=scenario[1]).latest("timestamp")
    assert feedback.actor_type == "human" and feedback.reason == "Human reviewed the evidence"
    assert feedback.context["actor"]["metadata"]["decision"] == "reject"
    assert resolve(scenario, proposal, "reject").data["status"] == "rejected"
    assert resolve(scenario, proposal, "accept").status_code == 409


@pytest.mark.parametrize(
    "invalid",
    [
        "quote",
        "evidence_id",
        "version",
        "relation_id",
        "target",
        "risk",
        "mitigation",
        "confidence",
        "extra",
        "duplicate",
    ],
)
def test_invalid_generation_never_becomes_a_proposal(scenario, invalid):
    output = deepcopy(scenario[2])
    item = output["suggestions"][0]
    if invalid == "quote":
        item["evidence"][0]["quote"] = "fabricated"
    elif invalid == "evidence_id":
        item["evidence"][0]["object_id"] = str(uuid4())
    elif invalid == "version":
        item["evidence"][0]["version"] += 1
    elif invalid == "relation_id":
        item["context_used"] = [str(uuid4())]
    elif invalid == "target":
        item["suggested_relation"]["target_id"] = str(scenario[4].pk)
    elif invalid == "risk":
        item["suggested_relation"]["source_id"] = str(scenario[5].pk)
    elif invalid == "mitigation":
        item["suggested_action"]["mitigates_risk_id"] = str(scenario[6].pk)
    elif invalid == "confidence":
        item["confidence"] = True
    elif invalid == "extra":
        item["execute"] = True
    else:
        output["suggestions"].append(deepcopy(item))
    scenario[7]["result"]["risk_review"] = output
    assert prepare(scenario).status_code == 400
    assert RiskReviewProposal.objects.count() == RiskReview.objects.count() == 0


@pytest.mark.parametrize("change", ["grant", "config", "binding", "version", "intent", "user", "membership"])
def test_accept_checks_current_authority_and_versions(scenario, change):
    proposal = prepare(scenario).data["proposals"][0]
    ctx = scenario[0][0][0]
    if change == "grant":
        fixture_write(lambda: ActorGrant.objects.filter(actor_id=scenario[0][1].actor_id).update(is_active=False))
    elif change == "config":
        from plane.radar.agent_config import configuration_snapshot

        data = configuration_snapshot(scenario[0][1], ActorGrant.objects.get(actor_id=scenario[0][1].actor_id))
        fixture_write(
            lambda: AgentConfiguration.objects.create(
                workspace=ctx[3],
                binding=scenario[0][1],
                version=1,
                **{k: data[k] for k in ["identity", "role", "policies", "permissions"]},
            )
        )
    elif change == "binding":
        fixture_write(lambda: type(scenario[0][1]).objects.filter(pk=scenario[0][1].pk).update(is_active=False))
    elif change == "version":
        fixture_write(lambda: Object.objects.filter(pk=scenario[4].pk).update(version=100))
    elif change == "intent":
        proposal["intent_hash"] = "a" * 64
    elif change == "user":
        scenario[0][2].force_authenticate(user=ctx[1])
    else:
        from plane.db.models import WorkspaceMember

        WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(is_active=False)
    response = resolve(scenario, proposal, "accept")
    assert response.status_code in {403, 404, 409}, response.data
    assert not Relation.objects.filter(relation_type__key="threatens").exists()


def test_missing_create_action_grant_rolls_back_all_preparation(scenario):
    # Preserve original run identity while testing the effective authority at the command seam.
    from plane.radar import risk_review

    original = risk_review.access_run

    def limited(*args):
        binding, effective, objects = original(*args)
        effective.commands = ["LinkObjects"]
        return binding, effective, objects

    from unittest.mock import patch

    before = CommandExecution.objects.count()
    with patch.object(risk_review, "access_run", limited):
        response = prepare(scenario)
    assert response.status_code == 403, response.data
    assert RiskReview.objects.count() == 0 and CommandExecution.objects.count() == before


def test_edit_validation_is_atomic_and_target_edit_remains_in_snapshot(scenario):
    proposals = prepare(scenario).data["proposals"]
    relation = next(p for p in proposals if p["component"] == "relation")
    malformed = resolve(scenario, relation, "edit", edited_input={**relation["input"], "target_id": str(uuid4())})
    assert malformed.status_code in {400, 403, 404}
    assert RiskReviewProposal.objects.get(pk=relation["id"]).execution.status == "pending_approval"
    edited = resolve(scenario, relation, "edit", edited_input={**relation["input"], "target_id": str(scenario[6].pk)})
    assert edited.status_code == 200, edited.data
    assert resolve(scenario, edited.data, "accept").status_code == 200
    assert Relation.objects.filter(source=scenario[4], target=scenario[6], relation_type__key="threatens").exists()


def test_empty_result_and_noncompleted_run(scenario):
    scenario[7]["status"] = "running"
    assert prepare(scenario).status_code == 202 and RiskReview.objects.count() == 0
    scenario[7]["status"] = "completed"
    scenario[7]["result"]["risk_review"]["suggestions"] = []
    response = prepare(scenario)
    assert response.status_code == 200 and response.data["proposals"] == []


def test_real_http_skill_and_commands(scenario, monkeypatch):
    import os
    from django.conf import settings
    from plane.radar.agent_runtime import runtime_request
    from plane.radar.models import AgentRuntimeRun
    import time

    base = os.environ.get("RADAR_AGENT_TEST_URL")
    if not base:
        pytest.skip("Set RADAR_AGENT_TEST_URL to the isolated scripted CoS HTTP server")
    monkeypatch.setattr(settings, "RADAR_AGENT_RUNTIME_URL", base)
    monkeypatch.setattr(settings, "RADAR_AGENT_RUNTIME_TOKEN", "radar-local-integration-test-key-0001")
    monkeypatch.setattr(risk_review_views, "runtime_request", runtime_request)
    run = AgentRuntimeRun.objects.get(pk=scenario[1])
    started = runtime_request("runs", run.request_data)
    assert started["status"] in {"queued", "completed"}
    response = prepare(scenario)
    for _ in range(80):
        if response.status_code != 202:
            break
        time.sleep(0.1)
        response = prepare(scenario)
    assert response.status_code == 200, response.data
    assert response.data["result"]["suggestions"][0]["confidence"] == 0.8
    relation, action = [
        next(p for p in response.data["proposals"] if p["component"] == component)
        for component in ["relation", "action"]
    ]
    assert resolve(scenario, relation, "accept").status_code == 200
    updated = resolve(
        scenario, action, "edit", edited_input={**action["input"], "title": "Mitigar atraso do licenciamento"}
    )
    assert updated.status_code == 200, updated.data
    accepted = resolve(scenario, updated.data, "accept")
    assert accepted.status_code == 200, accepted.data
    assert Relation.objects.filter(source=scenario[4], relation_type__key="threatens").exists()
    assert Object.objects.filter(title="Mitigar atraso do licenciamento", object_type__key="action").exists()
    assert resolve(scenario, updated.data, "accept").data["result"] == accepted.data["result"]


def test_filtered_fields_never_leak_through_command_preview(scenario):
    # Both session result transport and rollback previews are projected before reaching UI.
    secret = "private-hidden-content"
    fixture_write(lambda: Object.objects.filter(pk=scenario[4].pk).update(content=secret))
    response = prepare(scenario)
    assert response.status_code == 200, response.data
    assert secret not in str(response.data)
    assert all(p["preview"]["changes"] for p in response.data["proposals"])


def test_deleted_context_blocks_queue_and_accept(scenario):
    from django.utils import timezone

    proposal = prepare(scenario).data["proposals"][0]
    fixture_write(lambda: Object.all_objects.filter(pk=scenario[4].pk).update(deleted_at=timezone.now()))
    assert scenario[0][2].get(url(scenario)).data == {"runs": [], "proposals": []}
    assert resolve(scenario, proposal, "accept").status_code == 409
