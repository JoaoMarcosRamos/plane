import type {
  RadarCollaborationSnapshot,
  RadarCollaborationCommand,
  RadarCollaborationInput,
  RadarCollaborationResult,
} from "./collaboration.types";
import type { RiskQueue, RiskRunStatus, RiskResolution, RiskProposal } from "./risk-review.types";
import { API_BASE_URL } from "@plane/constants";
import { v4 as uuidv4 } from "uuid";
import { APIService } from "@/services/api.service";
import type { RadarTodayQueue } from "./today.types";
import type { RadarOperationalSnapshot, RadarOperationalHistory, RadarOperationalKind } from "./operational.types";
import type { RadarAgentConfigEntry, UpdateRadarAgentConfiguration } from "./agent-config.types";
import type {
  RadarSchemaCatalog,
  RadarCommandPreviewInput,
  RadarCommandPreview,
  CreateRadarObject,
  RadarObject,
  RadarObjectCollection,
  RadarObjectType,
  UpdateRadarObject,
  RadarPropertyDefinition,
  RadarPropertyData,
  RadarPropertySnapshot,
  RadarRelationType,
  RadarRelationSnapshot,
  CreateRadarRelation,
  RadarRelationMutation,
  RadarMutationContext,
  RadarPendingCommand,
  RadarObjectCapacities,
  RadarCommandResult,
} from "./types";

export class RadarApprovalPendingError extends Error {
  constructor(readonly command: RadarPendingCommand) {
    super("This change is awaiting human approval. Nothing has been changed yet.");
  }
}

function mutationData<T>(data: T | RadarPendingCommand): T {
  if (typeof data === "object" && data !== null && "status" in data && data.status === "pending_approval")
    throw new RadarApprovalPendingError(data as RadarPendingCommand);
  return data as T;
}

function mutationConfig(context: RadarMutationContext) {
  return {
    headers: {
      ...(context.expected_schema_revision !== undefined
        ? { "X-Radar-Expected-Schema-Revision": String(context.expected_schema_revision) }
        : {}),
      "X-Radar-Expected-Versions": JSON.stringify(context.expected_versions),
      "Idempotency-Key": context.idempotency_key ?? uuidv4(),
      ...(context.reason ? { "X-Radar-Reason": context.reason } : {}),
      ...(context.approval_id ? { "X-Radar-Approval-Id": context.approval_id } : {}),
    },
  };
}

export class RadarService extends APIService {
  async getOperations(slug: string, objectId: string, timezone: string): Promise<RadarOperationalSnapshot> {
    return (
      await this.get(`${this.path(slug)}/objects/${encodeURIComponent(objectId)}/operations/`, { params: { timezone } })
    ).data;
  }
  async getOperationalHistory(
    slug: string,
    objectId: string,
    options: { kind?: RadarOperationalKind; cursor?: string; limit?: number } = {}
  ): Promise<RadarOperationalHistory> {
    return (
      await this.get(`${this.path(slug)}/objects/${encodeURIComponent(objectId)}/operational-history/`, {
        params: options,
      })
    ).data;
  }
  async previewCommand(slug: string, input: RadarCommandPreviewInput): Promise<RadarCommandPreview> {
    return (await this.post(`${this.path(slug)}/commands/preview/`, input)).data;
  }

  /** Governed command through the shared envelope; review-required intents raise a pending error. */
  async executeCommand(
    slug: string,
    name: string,
    input: Record<string, unknown>,
    context: RadarMutationContext
  ): Promise<RadarCommandResult> {
    return mutationData(
      (
        await this.post(`${this.path(slug)}/commands/`, {
          command_name: name,
          command_version: 1,
          input,
          expected_versions: context.expected_versions,
          ...(context.expected_schema_revision !== undefined
            ? { expected_schema_revision: context.expected_schema_revision }
            : {}),
          ...(context.approval_id ? { approval_id: context.approval_id } : {}),
          idempotency_key: context.idempotency_key ?? uuidv4(),
          reason: context.reason ?? name,
          assertion: { kind: "asserted" },
        })
      ).data
    );
  }
  async getCapacities(slug: string, id: string): Promise<RadarObjectCapacities> {
    return (await this.get(`${this.path(slug)}/objects/${encodeURIComponent(id)}/capabilities/`)).data;
  }

  async getSchema(slug: string): Promise<RadarSchemaCatalog> {
    return (await this.get(`${this.path(slug)}/schema/`)).data;
  }
  async getCollaboration(slug: string, id: string, before?: string): Promise<RadarCollaborationSnapshot> {
    const path = `${this.path(slug)}/objects/${encodeURIComponent(id)}/collaboration/`;
    return (await (before ? this.get(path, { params: { activity_before: before } }) : this.get(path))).data;
  }
  async collaborationCommand(
    slug: string,
    name: RadarCollaborationCommand,
    input: RadarCollaborationInput,
    context: RadarMutationContext
  ): Promise<RadarCollaborationResult> {
    return mutationData(
      (
        await this.post(`${this.path(slug)}/commands/`, {
          command_name: name,
          command_version: 1,
          input,
          expected_versions: context.expected_versions,
          idempotency_key: context.idempotency_key ?? uuidv4(),
          reason: context.reason ?? "Object collaboration",
          assertion: { kind: "asserted" },
        })
      ).data
    );
  }
  async uploadObjectAttachment(
    slug: string,
    id: string,
    file: File,
    context: RadarMutationContext
  ): Promise<RadarCollaborationResult> {
    const form = new FormData();
    form.append("file", file);
    return mutationData(
      (
        await this.post(
          `${this.path(slug)}/objects/${encodeURIComponent(id)}/attachments/`,
          form,
          mutationConfig(context)
        )
      ).data
    );
  }
  async downloadObjectAttachment(slug: string, id: string, attachmentId: string): Promise<Blob> {
    return (
      await this.get(
        `${this.path(slug)}/objects/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/download/`,
        { responseType: "blob" }
      )
    ).data;
  }

  async getToday(slug: string, timezone: string): Promise<RadarTodayQueue> {
    return (await this.get(`${this.path(slug)}/today/`, { params: { timezone } })).data;
  }
  async listRiskReviews(slug: string, proposal?: string): Promise<RiskQueue> {
    const path = `${this.path(slug)}/risk-reviews/`;
    return (await (proposal ? this.get(path, { params: { proposal } }) : this.get(path))).data;
  }
  async startRiskReview(slug: string, bindingId: string, rootIds: string[], key: string): Promise<RiskRunStatus> {
    return (
      await this.post(
        `${this.path(slug)}/agent-runtime/runs/`,
        {
          binding_id: bindingId,
          root_ids: rootIds,
          skill: "risk_review",
          prompt: "Review Risks that may threaten the supplied Objectives or Projects.",
        },
        { headers: { "Idempotency-Key": key } }
      )
    ).data;
  }
  async prepareRiskReview(slug: string, runId: string): Promise<RiskRunStatus> {
    return (await this.post(`${this.path(slug)}/risk-reviews/`, { run_id: runId })).data;
  }
  async resolveRiskProposal(slug: string, proposalId: string, payload: RiskResolution): Promise<RiskProposal> {
    return (await this.post(`${this.path(slug)}/risk-reviews/${encodeURIComponent(proposalId)}/resolve/`, payload))
      .data;
  }

  async listAgentConfigurations(slug: string): Promise<RadarAgentConfigEntry[]> {
    return (await this.get(`${this.path(slug)}/agent-config/`)).data;
  }
  async getAgentConfiguration(slug: string, bindingId: string): Promise<RadarAgentConfigEntry> {
    return (await this.get(`${this.path(slug)}/agent-config/${encodeURIComponent(bindingId)}/`)).data;
  }
  async updateAgentConfiguration(
    slug: string,
    bindingId: string,
    payload: UpdateRadarAgentConfiguration
  ): Promise<RadarAgentConfigEntry> {
    return (await this.put(`${this.path(slug)}/agent-config/${encodeURIComponent(bindingId)}/`, payload)).data;
  }
  constructor() {
    super(API_BASE_URL);
  }
  private path(slug: string) {
    return `/api/workspaces/${encodeURIComponent(slug)}/radar`;
  }
  async listObjectTypes(slug: string): Promise<RadarObjectType[]> {
    return (await this.get(`${this.path(slug)}/object-types/`)).data;
  }
  async listObjects(slug: string): Promise<RadarObjectCollection> {
    const response = await this.get(`${this.path(slug)}/objects/`);
    const schema_revision = Number(response.headers?.["x-radar-schema-revision"] ?? 0);
    for (const object of response.data as RadarObject[]) object.schema_revision = schema_revision;
    const objects: RadarObjectCollection = response.data;
    objects.schema_revision = schema_revision;
    return objects;
  }
  async getObject(slug: string, id: string): Promise<RadarObject> {
    const response = await this.get(`${this.path(slug)}/objects/${encodeURIComponent(id)}/`);
    return { ...response.data, schema_revision: Number(response.headers?.["x-radar-schema-revision"] ?? 0) };
  }
  async createObject(slug: string, payload: CreateRadarObject, context: RadarMutationContext): Promise<RadarObject> {
    const response = await this.post(`${this.path(slug)}/objects/`, payload, mutationConfig(context));
    const object = mutationData<RadarObject>(response.data);
    return {
      ...object,
      schema_revision: Number(response.headers?.["x-radar-schema-revision"] ?? context.expected_schema_revision ?? 0),
    };
  }
  async updateObject(
    slug: string,
    id: string,
    payload: UpdateRadarObject,
    context: RadarMutationContext
  ): Promise<RadarObject> {
    const response = await this.patch(
      `${this.path(slug)}/objects/${encodeURIComponent(id)}/`,
      payload,
      mutationConfig(context)
    );
    const object = mutationData<RadarObject>(response.data);
    return {
      ...object,
      schema_revision: Number(response.headers?.["x-radar-schema-revision"] ?? context.expected_schema_revision ?? 0),
    };
  }
  async listPropertyDefinitions(slug: string, objectType?: string): Promise<RadarPropertyDefinition[]> {
    return (
      await this.get(
        `${this.path(slug)}/property-definitions/`,
        objectType ? { params: { object_type: objectType } } : {}
      )
    ).data;
  }
  async getProperties(slug: string, id: string): Promise<RadarPropertySnapshot> {
    return (await this.get(`${this.path(slug)}/objects/${encodeURIComponent(id)}/properties/`)).data;
  }
  async initializeProperties(slug: string, id: string, context: RadarMutationContext): Promise<RadarPropertySnapshot> {
    return mutationData(
      (await this.post(`${this.path(slug)}/objects/${encodeURIComponent(id)}/properties/`, {}, mutationConfig(context)))
        .data
    );
  }
  async setProperty(
    slug: string,
    id: string,
    definition: string,
    value: RadarPropertyData,
    context: RadarMutationContext
  ): Promise<RadarPropertySnapshot> {
    return mutationData(
      (
        await this.put(
          `${this.path(slug)}/objects/${encodeURIComponent(id)}/properties/${encodeURIComponent(definition)}/`,
          { value },
          mutationConfig(context)
        )
      ).data
    );
  }
  async removeProperty(
    slug: string,
    id: string,
    definition: string,
    context: RadarMutationContext
  ): Promise<RadarPropertySnapshot> {
    return mutationData(
      (
        await this.delete(
          `${this.path(slug)}/objects/${encodeURIComponent(id)}/properties/${encodeURIComponent(definition)}/`,
          undefined,
          mutationConfig(context)
        )
      ).data
    );
  }
  async listRelationTypes(slug: string): Promise<RadarRelationType[]> {
    return (await this.get(`${this.path(slug)}/relation-types/`)).data;
  }
  async getRelations(slug: string, id: string): Promise<RadarRelationSnapshot> {
    return (await this.get(`${this.path(slug)}/objects/${encodeURIComponent(id)}/relations/`)).data;
  }
  async createRelation(
    slug: string,
    payload: CreateRadarRelation,
    context: RadarMutationContext
  ): Promise<RadarRelationMutation> {
    return mutationData((await this.post(`${this.path(slug)}/relations/`, payload, mutationConfig(context))).data);
  }
  async removeRelation(slug: string, id: string, context: RadarMutationContext): Promise<{ objects: RadarObject[] }> {
    return mutationData(
      (await this.delete(`${this.path(slug)}/relations/${encodeURIComponent(id)}/`, undefined, mutationConfig(context)))
        .data
    );
  }
}
