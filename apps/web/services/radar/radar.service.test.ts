import { beforeEach, describe, expect, it, vi } from "vitest";
import { RadarApprovalPendingError, RadarService } from "./radar.service";

const context = { expected_versions: { "object/a": 1 }, idempotency_key: "stable-intention" };
const config = {
  headers: {
    "X-Radar-Expected-Versions": JSON.stringify(context.expected_versions),
    "Idempotency-Key": context.idempotency_key,
  },
};

const transport = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}));
vi.mock("@plane/constants", () => ({ API_BASE_URL: "https://api.example.com" }));
vi.mock("@/services/api.service", () => ({
  APIService: class {
    get = transport.get;
    post = transport.post;
    put = transport.put;
    delete = transport.delete;
    patch = transport.patch;
  },
}));

beforeEach(() => {
  vi.resetAllMocks();
  Object.values(transport).forEach((method) => method.mockResolvedValue({ data: { persisted: true } }));
});

describe("RADAR semantic session API service", () => {
  it("returns the server effect plan and preserves its complete dependencies for review", async () => {
    const payload = {
      command_name: "RegisterRisk",
      command_version: 1 as const,
      input: { title: "Delivery", description: "Delay", threatens_object_ids: ["objective"] },
      reason: "Review risk",
      expected_schema_revision: 3,
    };
    const plan = { schema_revision: 3, expected_versions: { objective: 7 }, requires_review: false, effect_plan: {} };
    transport.post.mockResolvedValueOnce({ data: plan });
    expect(await new RadarService().previewCommand("team/a", payload)).toEqual(plan);
    expect(transport.post).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/commands/preview/", payload);
  });

  it("reads Today and focused suggestions without issuing mutations", async () => {
    const service = new RadarService();
    await service.getToday("team/a", "America/Bahia");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/today/", {
      params: { timezone: "America/Bahia" },
    });
    await service.listRiskReviews("team/a", "proposal-id");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/risk-reviews/", {
      params: { proposal: "proposal-id" },
    });
    expect(transport.post).not.toHaveBeenCalled();
  });
  it("reads and saves agent config using session scope and the reviewed version", async () => {
    const service = new RadarService();
    await service.listAgentConfigurations("team/a");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/agent-config/");
    await service.getAgentConfiguration("team/a", "binding/a");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/agent-config/binding%2Fa/");
    const payload = {
      expected_version: 3,
      identity: { name: "Copilot", soul: "" },
      role: { name: "Analyst", purpose: "" },
      policies: { guidelines: [], read_only: true as const, require_human_approval: true as const },
      permissions: { commands: [], object_types: ["risk"], fields: ["title"], object_ids: null },
    };
    await service.updateAgentConfiguration("team/a", "binding/a", payload);
    expect(transport.put).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/agent-config/binding%2Fa/", payload);
  });
  it("encodes identifiers and sends typed property writes to their object", async () => {
    const service = new RadarService();
    expect(await service.setProperty("team/a", "object/a", "definition/a", false, context)).toEqual({
      persisted: true,
    });
    expect(transport.put).toHaveBeenCalledWith(
      "/api/workspaces/team%2Fa/radar/objects/object%2Fa/properties/definition%2Fa/",
      { value: false },
      config
    );
    await service.removeProperty("team/a", "object/a", "definition/a", context);
    expect(transport.delete).toHaveBeenCalledWith(
      "/api/workspaces/team%2Fa/radar/objects/object%2Fa/properties/definition%2Fa/",
      undefined,
      config
    );
    await service.initializeProperties("team/a", "object/a", context);
    expect(transport.post).toHaveBeenCalledWith(
      "/api/workspaces/team%2Fa/radar/objects/object%2Fa/properties/",
      {},
      config
    );
  });
  it("fetches scoped schema, values and both relation directions", async () => {
    const service = new RadarService();
    await service.listPropertyDefinitions("team", "type");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team/radar/property-definitions/", {
      params: { object_type: "type" },
    });
    await service.listRelationTypes("team");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team/radar/relation-types/");
    await service.getProperties("team", "object");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team/radar/objects/object/properties/");
    await service.getRelations("team", "object");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team/radar/objects/object/relations/");
  });
  it("sends relation mutations and propagates backend rejection", async () => {
    const service = new RadarService();
    const payload = { relation_type: "kind", source: "source", target: "target" };
    await service.createRelation("team", payload, context);
    expect(transport.post).toHaveBeenCalledWith("/api/workspaces/team/radar/relations/", payload, config);
    await service.removeRelation("team", "edge/a", context);
    expect(transport.delete).toHaveBeenCalledWith("/api/workspaces/team/radar/relations/edge%2Fa/", undefined, config);
    transport.post.mockRejectedValue(new Error("cardinality"));
    await expect(service.createRelation("team", payload, context)).rejects.toThrow("cardinality");
  });
  it("keeps pending approvals separate from successful object writes", async () => {
    transport.post.mockResolvedValue({
      data: { status: "pending_approval", command_id: "command", approval_id: "approval" },
    });
    await expect(
      new RadarService().createObject("team", { object_type: "type", title: "Draft" }, context)
    ).rejects.toBeInstanceOf(RadarApprovalPendingError);
  });
  it("preserves the caller's intention key and exact versions across retries", async () => {
    const service = new RadarService();
    transport.patch.mockRejectedValueOnce(new Error("Response lost"));
    await expect(service.updateObject("team", "object/a", { title: "Edit" }, context)).rejects.toThrow("Response lost");
    await service.updateObject("team", "object/a", { title: "Edit" }, context);
    expect(transport.patch.mock.calls[0]).toEqual(transport.patch.mock.calls[1]);
  });
});

describe("RADAR collaboration transport", () => {
  it("uses only Object RADAR endpoints with exact command scope and stable retry keys", async () => {
    const service = new RadarService();
    await service.getCollaboration("team/a", "object/a");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/objects/object%2Fa/collaboration/");
    await service.getCollaboration("team/a", "object/a", "cursor");
    expect(transport.get).toHaveBeenLastCalledWith("/api/workspaces/team%2Fa/radar/objects/object%2Fa/collaboration/", {
      params: { activity_before: "cursor" },
    });
    await service.collaborationCommand("team/a", "AddComment", { object_id: "object/a", body: "Discussion" }, context);
    expect(transport.post).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/commands/", {
      command_name: "AddComment",
      command_version: 1,
      input: { object_id: "object/a", body: "Discussion" },
      expected_versions: context.expected_versions,
      idempotency_key: context.idempotency_key,
      reason: "Object collaboration",
      assertion: { kind: "asserted" },
    });
  });
  it("sends private multipart bytes and downloads authenticated blobs", async () => {
    const service = new RadarService();
    await service.uploadObjectAttachment("team", "object/a", new File(["evidence"], "source.txt"), context);
    expect(transport.post.mock.calls[0][0]).toBe("/api/workspaces/team/radar/objects/object%2Fa/attachments/");
    expect(transport.post.mock.calls[0][1].get("file").name).toBe("source.txt");
    expect(transport.post.mock.calls[0][2]).toEqual(config);
    await service.downloadObjectAttachment("team", "object/a", "attachment/a");
    expect(transport.get).toHaveBeenCalledWith(
      "/api/workspaces/team/radar/objects/object%2Fa/attachments/attachment%2Fa/download/",
      { responseType: "blob" }
    );
  });
});

describe("C20 capacities and governed command transport", () => {
  it("reads actor capacities without mutating", async () => {
    await new RadarService().getCapacities("team/a", "object/1");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/objects/object%2F1/capabilities/");
    expect(transport.post).not.toHaveBeenCalled();
  });

  it("sends the complete reviewed envelope and surfaces pending approval without a change", async () => {
    const service = new RadarService();
    transport.post.mockResolvedValueOnce({ data: { command_id: "c", status: "executed", data: {} } });
    await service.executeCommand(
      "team/a",
      "CompleteAction",
      { action_id: "a" },
      { ...context, expected_schema_revision: 4, approval_id: "approval" }
    );
    expect(transport.post).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/commands/", {
      command_name: "CompleteAction",
      command_version: 1,
      input: { action_id: "a" },
      expected_versions: context.expected_versions,
      expected_schema_revision: 4,
      approval_id: "approval",
      idempotency_key: "stable-intention",
      reason: "CompleteAction",
      assertion: { kind: "asserted" },
    });
    transport.post.mockResolvedValueOnce({ data: { status: "pending_approval", command_id: "c", approval_id: "a" } });
    await expect(service.executeCommand("team/a", "ApproveDecision", {}, context)).rejects.toBeInstanceOf(
      RadarApprovalPendingError
    );
  });
});

describe("C18 scoped operational reads", () => {
  it("encodes identifiers and passes only explicit bounded history parameters", async () => {
    const service = new RadarService();
    await service.getOperations("team/a", "object/a", "America/Bahia");
    expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/objects/object%2Fa/operations/", {
      params: { timezone: "America/Bahia" },
    });
    await service.getOperationalHistory("team/a", "object/a", { kind: "review", cursor: "opaque", limit: 20 });
    expect(transport.get).toHaveBeenCalledWith(
      "/api/workspaces/team%2Fa/radar/objects/object%2Fa/operational-history/",
      { params: { kind: "review", cursor: "opaque", limit: 20 } }
    );
    expect(transport.post).not.toHaveBeenCalled();
  });
});

it("transports bounded search filters and exposed page cursors", async () => {
  const data = [{ id: "remote", title: "Remote", version: 4 }];
  transport.get.mockResolvedValueOnce({
    data,
    headers: { "x-radar-schema-revision": "7", "x-radar-next-cursor": "signed" },
  });
  const query = {
    relation_type: "kind",
    object_id: "object",
    direction: "incoming" as const,
    q: "Remote",
    limit: 5,
    cursor: "before",
  };
  const result = await new RadarService().listObjects("team/a", query);
  expect(transport.get).toHaveBeenCalledWith("/api/workspaces/team%2Fa/radar/objects/", { params: query });
  expect(result.schema_revision).toBe(7);
  expect(result.next_cursor).toBe("signed");
  expect(result[0].schema_revision).toBe(7);
  transport.get.mockResolvedValueOnce({ data: { relations: [], next_cursor: null } });
  await new RadarService().getRelations("team/a", "object/a", "signed");
  expect(transport.get).toHaveBeenLastCalledWith("/api/workspaces/team%2Fa/radar/objects/object%2Fa/relations/", {
    params: { cursor: "signed" },
  });
});
