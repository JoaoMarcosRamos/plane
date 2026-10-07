from .risk_review_views import RiskReviewsView, RiskReviewResolveView
from .today_views import TodayView
from .operational_views import ObjectOperationsView, ObjectOperationalHistoryView
from django.urls import path
from .agent_views import AgentContextView, AgentRunsView, AgentRunControlView
from .agent_config_views import AgentConfigurationsView, AgentConfigurationDetailView
from .runtime_views import (
    RuntimeCapabilitiesView,
    RuntimeCommandPrepareView,
    RuntimePrepareView,
    RuntimeResolveView,
    RuntimeQueryView,
)
from .schema_views import WorkspaceSchemaView
from .views import ObjectTypesView, ObjectsView, ObjectDetailView
from .command_views import (
    CommandsView,
    CommandPreviewView,
    CommandDetailView,
    CommandReviewView,
    ActorGrantsView,
    PersonIdentitiesView,
    ObjectProvenanceView,
)
from .semantic_views import (
    PropertyDefinitionsView,
    ObjectCapacitiesView,
    ObjectPropertiesView,
    ObjectPropertyView,
    RelationTypesView,
    ObjectRelationsView,
    RelationsView,
    RelationDetailView,
)

from .collaboration_views import ObjectCollaborationView, ObjectAttachmentUploadView, ObjectAttachmentDownloadView

urlpatterns = [
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/operations/", ObjectOperationsView.as_view()),
    path(
        "workspaces/<str:slug>/radar/objects/<uuid:object_id>/operational-history/",
        ObjectOperationalHistoryView.as_view(),
    ),
    path("workspaces/<str:slug>/radar/schema/", WorkspaceSchemaView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/collaboration/", ObjectCollaborationView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/attachments/", ObjectAttachmentUploadView.as_view()),
    path(
        "workspaces/<str:slug>/radar/objects/<uuid:object_id>/attachments/<uuid:attachment_id>/download/",
        ObjectAttachmentDownloadView.as_view(),
    ),
    path("workspaces/<str:slug>/radar/today/", TodayView.as_view()),
    path("workspaces/<str:slug>/radar/risk-reviews/", RiskReviewsView.as_view()),
    path("workspaces/<str:slug>/radar/risk-reviews/<uuid:proposal_id>/resolve/", RiskReviewResolveView.as_view()),
    path("workspaces/<str:slug>/radar/agent-config/", AgentConfigurationsView.as_view()),
    path("workspaces/<str:slug>/radar/agent-config/<uuid:binding_id>/", AgentConfigurationDetailView.as_view()),
    path("workspaces/<str:slug>/radar/agent-runtime/context/", AgentContextView.as_view()),
    path("workspaces/<str:slug>/radar/agent-runtime/runs/", AgentRunsView.as_view()),
    path(
        "workspaces/<str:slug>/radar/agent-runtime/runs/<uuid:run_id>/<str:operation>/", AgentRunControlView.as_view()
    ),
    path("workspaces/<str:slug>/radar/runtime/v1/commands/prepare/", RuntimeCommandPrepareView.as_view()),
    path("workspaces/<str:slug>/radar/runtime/v1/capabilities/", RuntimeCapabilitiesView.as_view()),
    path("workspaces/<str:slug>/radar/runtime/v1/prepare/", RuntimePrepareView.as_view()),
    path("workspaces/<str:slug>/radar/runtime/v1/resolve/", RuntimeResolveView.as_view()),
    path("workspaces/<str:slug>/radar/runtime/v1/query/", RuntimeQueryView.as_view()),
    path("workspaces/<str:slug>/radar/commands/", CommandsView.as_view()),
    path("workspaces/<str:slug>/radar/commands/preview/", CommandPreviewView.as_view()),
    path("workspaces/<str:slug>/radar/commands/<uuid:command_id>/", CommandDetailView.as_view()),
    path("workspaces/<str:slug>/radar/commands/<uuid:command_id>/review/", CommandReviewView.as_view()),
    path("workspaces/<str:slug>/radar/actor-grants/", ActorGrantsView.as_view()),
    path("workspaces/<str:slug>/radar/person-identities/", PersonIdentitiesView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/provenance/", ObjectProvenanceView.as_view()),
    path("workspaces/<str:slug>/radar/object-types/", ObjectTypesView.as_view()),
    path("workspaces/<str:slug>/radar/objects/", ObjectsView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/", ObjectDetailView.as_view()),
    path("workspaces/<str:slug>/radar/property-definitions/", PropertyDefinitionsView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/properties/", ObjectPropertiesView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/capabilities/", ObjectCapacitiesView.as_view()),
    path(
        "workspaces/<str:slug>/radar/objects/<uuid:object_id>/properties/<uuid:definition_id>/",
        ObjectPropertyView.as_view(),
    ),
    path("workspaces/<str:slug>/radar/relation-types/", RelationTypesView.as_view()),
    path("workspaces/<str:slug>/radar/objects/<uuid:object_id>/relations/", ObjectRelationsView.as_view()),
    path("workspaces/<str:slug>/radar/relations/", RelationsView.as_view()),
    path("workspaces/<str:slug>/radar/relations/<uuid:relation_id>/", RelationDetailView.as_view()),
]
