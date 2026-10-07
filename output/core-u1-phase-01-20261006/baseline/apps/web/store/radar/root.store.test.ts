import { describe, expect, it, vi } from "vitest";
import { RadarRootStore } from "./root.store";
import type { RadarClient } from "./root.store";
import type { RadarObject, RadarObjectType, RadarRelation } from "../../services/radar/types";

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
    expect(service.setProperty).toHaveBeenCalledWith("tenant", object.id, "definition", "active", {
      expected_versions: { object: 1 },
    });
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
    expect(service.removeRelation).toHaveBeenCalledWith("tenant", "edge", {
      expected_versions: { object: 2, target: 2 },
    });
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
