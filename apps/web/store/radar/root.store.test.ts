import { describe, expect, it, vi } from "vitest";
import { RadarRootStore } from "./root.store";
import type { RadarClient } from "./root.store";
import type {
  RadarCommandPreview,
  RadarObject,
  RadarObjectCapacities,
  RadarObjectType,
  RadarRelation,
} from "../../services/radar/types";

const type: RadarObjectType = {
  id: "type",
  workspace: "workspace",
  key: "objective",
  name: "Objective",
  description: "",
  icon: "",
  is_active: true,
  is_system: true,
};
const object: RadarObject = {
  id: "object",
  workspace: "workspace",
  object_type: type.id,
  object_type_detail: type,
  title: "Implantar Governança de IA",
  content: "<p>Context</p>",
  version: 1,
  created_by: "human-one",
  updated_by: "human-one",
  created_at: "2026-10-03",
  updated_at: "2026-10-03",
};
const relation: RadarRelation = {
  id: "edge",
  workspace: "workspace",
  relation_type: "kind",
  source: object.id,
  target: "target",
  relation_type_detail: {
    id: "kind",
    workspace: "workspace",
    key: "advances",
    forward_label: "advances",
    reverse_label: "advanced_by",
    description: "",
    source_types: ["action"],
    target_types: ["objective"],
    allowed_pairs: [],
    cardinality: "0..n",
    allow_self: false,
    is_system: true,
    is_active: true,
  },
  created_by: "human-one",
  updated_by: "human-one",
  created_at: "2026-10-03",
  updated_at: "2026-10-03",
};
const client = (): RadarClient => ({
  listPropertyDefinitions: vi.fn().mockResolvedValue([]),
  getProperties: vi.fn().mockResolvedValue({ object, properties: [] }),
  initializeProperties: vi.fn().mockResolvedValue({ object: { ...object, version: 2 }, properties: [] }),
  setProperty: vi.fn().mockResolvedValue({ object: { ...object, version: 2 }, properties: [] }),
  removeProperty: vi.fn().mockResolvedValue({ object: { ...object, version: 3 }, properties: [] }),
  listRelationTypes: vi.fn().mockResolvedValue([]),
  getRelations: vi.fn().mockResolvedValue({ object, relations: [] }),
  createRelation: vi.fn().mockResolvedValue({ relation, objects: [{ ...object, version: 2 }] }),
  removeRelation: vi.fn().mockResolvedValue({ objects: [{ ...object, version: 3 }] }),
  listObjectTypes: vi.fn().mockResolvedValue([type]),
  listObjects: vi.fn().mockResolvedValue([object]),
  getObject: vi.fn().mockResolvedValue(object),
  createObject: vi.fn().mockResolvedValue(object),
  updateObject: vi
    .fn()
    .mockResolvedValue({ ...object, title: "Implantar Governança de IA na C3", version: 2, updated_by: "human-two" }),
});

describe("RADAR isolated store", () => {
  it("loads types and objects from its workspace service", async () => {
    const service = client();
    const store = new RadarRootStore("zero-projects", service);
    await Promise.all([store.loadTypes(), store.loadList()]);
    expect(service.listObjects).toHaveBeenCalledWith("zero-projects");
    expect(store.objectTypes).toEqual([type]);
    expect(store.listedObjects).toEqual([object]);
  });
  it("creates, caches, updates and retrieves persisted audit data", async () => {
    const service = client();
    const store = new RadarRootStore("zero-projects", service);
    await store.createObject({ object_type: type.id, title: object.title });
    expect(store.listedObjects).toHaveLength(1);
    const updated = await store.updateObject(object.id, { title: "Implantar Governança de IA na C3" });
    expect(updated.version).toBe(2);
    expect(updated.created_by).toBe("human-one");
    expect(store.objects.get(object.id)?.updated_by).toBe("human-two");
    await store.getObject(object.id); // Late version 1 response must not overwrite version 2.
    expect(store.objects.get(object.id)?.version).toBe(2);
  });
  it("never shares data between workspace provider instances", async () => {
    const first = new RadarRootStore("first", client());
    const second = new RadarRootStore("second", client());
    await first.loadList();
    expect(second.objects.size).toBe(0);
    expect(second.objectTypes).toEqual([]);
  });
  it("propagates failures without inventing a successful write", async () => {
    const service = client();
    vi.mocked(service.createObject).mockRejectedValue(new Error("403"));
    const store = new RadarRootStore("zero-projects", service);
    await expect(store.createObject({ object_type: type.id, title: object.title })).rejects.toThrow("403");
    expect(store.listedObjects).toEqual([]);
  });
  it("keeps a saved version when a stale list arrives", async () => {
    const store = new RadarRootStore("zero-projects", client());
    await store.getObject(object.id);
    await store.updateObject(object.id, { title: "Updated" });
    await store.loadList();
    expect(store.listedObjects[0].version).toBe(2);
  });
});

describe("RADAR semantic store", () => {
  it("loads schema and independent snapshots scoped to the provider", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await Promise.all([store.loadSemanticTypes(), store.loadProperties(object.id), store.loadRelations(object.id)]);
    expect(service.getProperties).toHaveBeenCalledWith("tenant", object.id);
    expect(service.getRelations).toHaveBeenCalledWith("tenant", object.id);
    expect(store.propertiesFor(object.id)).toEqual([]);
    expect(store.relationsFor(object.id)).toEqual([]);
    expect(new RadarRootStore("other", client()).propertiesFor(object.id)).toBeUndefined();
  });
  it("rejects late property and relation snapshots after a semantic write", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await store.loadProperties(object.id);
    await store.setProperty(object.id, "definition", "active");
    await store.loadProperties(object.id);
    await store.loadRelations(object.id);
    expect(store.objects.get(object.id)?.version).toBe(2);
    expect(store.propertySnapshots.get(object.id)?.object.version).toBe(2);
    expect(store.relationsFor(object.id)).toBeUndefined();
    expect(service.setProperty).toHaveBeenCalledWith(
      "tenant",
      object.id,
      "definition",
      "active",
      expect.objectContaining({
        expected_versions: { object: 1 },
        idempotency_key: expect.any(String),
      })
    );
  });
  it("invalidates both endpoint snapshots when a relation changes", async () => {
    const service = client();
    vi.mocked(service.createRelation).mockResolvedValue({
      relation,
      objects: [
        { ...object, version: 2 },
        { ...object, id: "target", version: 2 },
      ],
    });
    const store = new RadarRootStore("tenant", service);
    vi.mocked(service.listObjects).mockResolvedValue([object, { ...object, id: "target" }]);
    await store.loadList();
    await store.loadProperties(object.id);
    await store.loadRelations(object.id);
    await store.createRelation({ relation_type: "kind", source: object.id, target: "target" });
    expect(store.objects.get("target")?.version).toBe(2);
    expect(store.propertiesFor(object.id)).toBeUndefined();
    expect(store.relationsFor(object.id)).toBeUndefined();
    await store.removeRelation("edge");
    expect(service.removeRelation).toHaveBeenCalledWith(
      "tenant",
      "edge",
      expect.objectContaining({
        expected_versions: { object: 2, target: 2 },
        idempotency_key: expect.any(String),
      })
    );
    expect(store.objects.get(object.id)?.version).toBe(3);
  });
  it("preserves cache on failed semantic mutations", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await store.loadProperties(object.id);
    vi.mocked(service.setProperty).mockRejectedValue(new Error("invalid enum"));
    await expect(store.setProperty(object.id, "definition", "bad")).rejects.toThrow("invalid enum");
    expect(store.objects.get(object.id)?.version).toBe(1);
    expect(store.propertiesFor(object.id)).toEqual([]);
  });
  it("materializes defaults and accepts a removal snapshot", async () => {
    const store = new RadarRootStore("tenant", client());
    await store.getObject(object.id);
    await store.initializeProperties(object.id);
    expect(store.objects.get(object.id)?.version).toBe(2);
    await store.removeProperty(object.id, "definition");
    expect(store.objects.get(object.id)?.version).toBe(3);
  });
  it("does not write when the store has no read snapshot", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await expect(store.updateObject(object.id, { title: "Blind edit" })).rejects.toThrow("Load the object");
    expect(service.updateObject).not.toHaveBeenCalled();
  });
});

describe("RADAR page aggregate snapshots", () => {
  it("loads schema, related objects and consistent property/relation versions", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await store.loadObjectPage(object.id);
    expect(store.propertiesFor(object.id)).toEqual([]);
    expect(store.relationsFor(object.id)).toEqual([]);
    expect(store.listedObjects).toHaveLength(1);
  });
  it("recovers when a concurrent write crosses property and relation reads", async () => {
    const service = client();
    vi.mocked(service.getProperties)
      .mockResolvedValueOnce({ object, properties: [] })
      .mockResolvedValue({ object: { ...object, version: 2 }, properties: [] });
    vi.mocked(service.getRelations).mockResolvedValue({ object: { ...object, version: 2 }, relations: [] });
    const store = new RadarRootStore("tenant", service);
    await store.loadObjectSemantics(object.id);
    expect(service.getProperties).toHaveBeenCalledTimes(2);
    expect(store.propertiesFor(object.id)).toEqual([]);
    expect(store.relationsFor(object.id)).toEqual([]);
  });
  it("stops retries if concurrent changes keep snapshots inconsistent", async () => {
    const service = client();
    vi.mocked(service.getRelations).mockResolvedValue({ object: { ...object, version: 2 }, relations: [] });
    const store = new RadarRootStore("tenant", service);
    await expect(store.loadObjectSemantics(object.id)).rejects.toThrow("Object changed");
    expect(service.getProperties).toHaveBeenCalledTimes(3);
  });
});

describe("RADAR mutation intentions", () => {
  it("retries a lost creation response with the same input and key, then retires it", async () => {
    const service = client();
    vi.mocked(service.createObject).mockRejectedValueOnce(new Error("Response lost"));
    const store = new RadarRootStore("tenant", service);
    const payload = { object_type: type.id, title: "Create once", properties: { tags: ["first"] } };
    await expect(store.createObject(payload)).rejects.toThrow("Response lost");
    await store.createObject({ properties: { tags: ["first"] }, title: "Create once", object_type: type.id });
    const calls = vi.mocked(service.createObject).mock.calls;
    expect(calls[0]).toEqual(calls[1]);
    expect(calls[0][2]).toMatchObject({ expected_versions: {}, idempotency_key: expect.any(String) });
    expect(store.listedObjects).toHaveLength(1);
    await store.createObject(payload);
    expect(calls[2][2].idempotency_key).not.toBe(calls[0][2].idempotency_key);
  });
  it("preserves reviewed versions after an uncertain commit and a fresh read", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await store.getObject(object.id);
    vi.mocked(service.updateObject).mockRejectedValueOnce(new Error("Timeout after commit"));
    await expect(store.updateObject(object.id, { title: "Edit" })).rejects.toThrow("Timeout");
    vi.mocked(service.getObject).mockResolvedValue({ ...object, version: 2 });
    await store.getObject(object.id);
    await store.updateObject(object.id, { title: "Edit" });
    const calls = vi.mocked(service.updateObject).mock.calls;
    expect(calls[0]).toEqual(calls[1]);
    expect(calls[1][3].expected_versions).toEqual({ object: 1 });
  });
  it("copies payloads and uses a new key for changed input", async () => {
    const service = client();
    vi.mocked(service.createObject).mockRejectedValueOnce(new Error("Lost"));
    const store = new RadarRootStore("tenant", service);
    const payload = { object_type: type.id, title: "Before", properties: { tags: ["original"] } };
    await expect(store.createObject(payload)).rejects.toThrow();
    payload.title = "After";
    payload.properties.tags.push("additional");
    await store.createObject(payload);
    const calls = vi.mocked(service.createObject).mock.calls;
    expect(calls[0][1]).toEqual({ object_type: type.id, title: "Before", properties: { tags: ["original"] } });
    expect(calls[0][2].idempotency_key).not.toBe(calls[1][2].idempotency_key);
  });
  it("does not automatically rebase conflicts; reviewed resubmission creates a new intent", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    await store.getObject(object.id);
    vi.mocked(service.updateObject).mockRejectedValueOnce({ response: { status: 409 } });
    await expect(store.updateObject(object.id, { title: "Edit" })).rejects.toBeDefined();
    expect(service.updateObject).toHaveBeenCalledTimes(1);
    vi.mocked(service.getObject).mockResolvedValue({ ...object, version: 3 });
    await store.getObject(object.id);
    await store.updateObject(object.id, { title: "Edit" });
    const calls = vi.mocked(service.updateObject).mock.calls;
    expect(calls[1][3].expected_versions).toEqual({ object: 3 });
    expect(calls[1][3].idempotency_key).not.toBe(calls[0][3].idempotency_key);
  });
  it("preserves defaults, property and relation intentions after lost responses", async () => {
    const service = client();
    const store = new RadarRootStore("tenant", service);
    vi.mocked(service.listObjects).mockResolvedValue([object, { ...object, id: "target" }]);
    await store.loadList();
    await store.loadRelations(object.id);
    vi.mocked(service.initializeProperties).mockRejectedValueOnce(new Error("Lost"));
    await expect(store.initializeProperties(object.id)).rejects.toThrow("Lost");
    await store.initializeProperties(object.id);
    expect(vi.mocked(service.initializeProperties).mock.calls[0]).toEqual(
      vi.mocked(service.initializeProperties).mock.calls[1]
    );
    vi.mocked(service.setProperty).mockRejectedValueOnce({ response: { status: 502 } });
    await expect(store.setProperty(object.id, "definition", "active")).rejects.toBeDefined();
    await store.setProperty(object.id, "definition", "active");
    expect(vi.mocked(service.setProperty).mock.calls[0]).toEqual(vi.mocked(service.setProperty).mock.calls[1]);
    vi.mocked(service.removeProperty).mockRejectedValueOnce(new Error("Lost"));
    await expect(store.removeProperty(object.id, "definition")).rejects.toThrow("Lost");
    await store.removeProperty(object.id, "definition");
    expect(vi.mocked(service.removeProperty).mock.calls[0]).toEqual(vi.mocked(service.removeProperty).mock.calls[1]);
    const payload = { relation_type: "kind", source: object.id, target: "target" };
    vi.mocked(service.createRelation).mockRejectedValueOnce(new Error("Lost"));
    await expect(store.createRelation(payload)).rejects.toThrow("Lost");
    await store.createRelation(payload);
    expect(vi.mocked(service.createRelation).mock.calls[0]).toEqual(vi.mocked(service.createRelation).mock.calls[1]);
    vi.mocked(service.removeRelation).mockRejectedValueOnce(new Error("Lost"));
    await expect(store.removeRelation(relation.id)).rejects.toThrow("Lost");
    await store.removeRelation(relation.id);
    expect(vi.mocked(service.removeRelation).mock.calls[0]).toEqual(vi.mocked(service.removeRelation).mock.calls[1]);
  });
  it("retains pending approval intent and adds its ID only after explicit resume", async () => {
    const service = client();
    const pending = Object.assign(new Error("Pending approval"), {
      command: { status: "pending_approval", command_id: "command", approval_id: "approval" },
    });
    vi.mocked(service.createObject).mockRejectedValueOnce(pending).mockRejectedValueOnce(pending);
    const store = new RadarRootStore("tenant", service);
    const payload = { object_type: type.id, title: "Governed" };
    await expect(store.createObject(payload)).rejects.toThrow("Pending");
    await expect(store.createObject(payload)).rejects.toThrow("Pending");
    expect(vi.mocked(service.createObject).mock.calls[1][2].approval_id).toBeUndefined();
    const key = vi.mocked(service.createObject).mock.calls[0][2].idempotency_key;
    expect(() => store.resumePendingMutation("different")).toThrow("review");
    store.resumePendingMutation("approval");
    await store.createObject(payload);
    expect(vi.mocked(service.createObject).mock.calls[2][2]).toEqual({
      expected_versions: {},
      idempotency_key: key,
      approval_id: "approval",
      expected_schema_revision: 0,
    });
  });
  it("does not duplicate an in-flight submission", async () => {
    const service = client();
    let finish!: (value: RadarObject) => void;
    vi.mocked(service.createObject).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      })
    );
    const store = new RadarRootStore("tenant", service);
    const payload = { object_type: type.id, title: "Once" };
    const request = store.createObject(payload);
    await expect(store.createObject(payload)).rejects.toThrow("already being submitted");
    expect(service.createObject).toHaveBeenCalledTimes(1);
    finish(object);
    await request;
  });
  it("isolates uncertainty between workspace/session instances", async () => {
    const service = client();
    vi.mocked(service.createObject).mockRejectedValueOnce(new Error("Lost"));
    const first = new RadarRootStore("first", service);
    const second = new RadarRootStore("second", service);
    const payload = { object_type: type.id, title: "Once" };
    await expect(first.createObject(payload)).rejects.toThrow();
    await second.createObject(payload);
    const calls = vi.mocked(service.createObject).mock.calls;
    expect(calls[0][2].idempotency_key).not.toBe(calls[1][2].idempotency_key);
  });
});

describe("C20 capacities and governed commands", () => {
  const capacities = (version: number, schema_revision = 0) =>
    ({
      schema_revision,
      object: { id: object.id, version, object_type: "objective" },
      can_write: true,
      metadata_errors: [],
      fields: {},
      transitions: [],
      actions: [],
      relations: {},
    }) as unknown as RadarObjectCapacities;
  const preview = {
    schema_revision: 0,
    expected_versions: { [object.id]: 9, evidence: 4 },
    requires_review: false,
    effect_plan: {} as RadarCommandPreview["effect_plan"],
  };

  it("caches capacities only for the current Object version and schema revision", async () => {
    const service = {
      ...client(),
      getCapacities: vi.fn().mockResolvedValueOnce(capacities(1)).mockResolvedValueOnce(capacities(1)),
    };
    const store = new RadarRootStore("w", service);
    await store.loadObjectSemantics(object.id);
    expect(service.getCapacities).toHaveBeenCalledWith("w", object.id);
    expect(store.capacitiesFor(object.id)?.object.version).toBe(1);
    store.objects.set(object.id, { ...object, version: 2 });
    expect(store.capacitiesFor(object.id)).toBeUndefined();
  });

  it("reviews then executes with the viewed page version and the reviewed versions of other dependencies", async () => {
    const executeCommand = vi.fn().mockResolvedValue({ command_id: "c", status: "executed", data: {} });
    const service = {
      ...client(),
      getCapacities: vi.fn().mockResolvedValue(capacities(1)),
      previewCommand: vi.fn().mockResolvedValue(preview),
      executeCommand,
    };
    const store = new RadarRootStore("w", service);
    await store.loadObjectSemantics(object.id);
    // A stale list entry for another dependency must not override the version the preview showed.
    store.objects.set("evidence", { ...object, id: "evidence", version: 2 });
    const input = { action_id: object.id, outcome: "Signed", evidence_id: "evidence" };
    const reviewed = await store.previewCommand("CompleteAction", input, "Complete");
    expect(service.previewCommand).toHaveBeenCalledWith("w", {
      command_name: "CompleteAction",
      command_version: 1,
      input,
      reason: "Complete",
      expected_schema_revision: 0,
    });
    await store.runCommand(object.id, "CompleteAction", input, reviewed);
    const context = executeCommand.mock.calls[0][3];
    expect(executeCommand.mock.calls[0].slice(0, 3)).toEqual(["w", "CompleteAction", input]);
    // The viewed v1 wins over the preview's v9, so a change since loading surfaces as a conflict.
    expect(context.expected_versions).toEqual({ [object.id]: 1, evidence: 4 });
    expect(context.expected_schema_revision).toBe(0);
    expect(service.getCapacities).toHaveBeenCalledTimes(2);
  });

  it("keeps a pending-approval intention for an explicit resume and reloads nothing", async () => {
    const pending = Object.assign(new Error("pending"), {
      command: { status: "pending_approval", command_id: "c", approval_id: "approval" },
    });
    const executeCommand = vi.fn().mockRejectedValue(pending);
    const service = { ...client(), getCapacities: vi.fn().mockResolvedValue(capacities(1)), executeCommand };
    const store = new RadarRootStore("w", service);
    await store.loadObjectSemantics(object.id);
    await expect(store.runCommand(object.id, "ApproveDecision", { decision_id: object.id }, preview)).rejects.toBe(
      pending
    );
    store.resumePendingMutation("approval");
    await expect(store.runCommand(object.id, "ApproveDecision", { decision_id: object.id }, preview)).rejects.toBe(
      pending
    );
    expect(executeCommand.mock.calls[1][3].approval_id).toBe("approval");
    expect(executeCommand.mock.calls[1][3].idempotency_key).toBe(executeCommand.mock.calls[0][3].idempotency_key);
    expect(service.getCapacities).toHaveBeenCalledTimes(1);
  });
});
