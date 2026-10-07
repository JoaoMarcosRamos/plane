import { describe, expect, it, vi } from "vitest";
import { RadarRootStore } from "./root.store";
import type { RadarClient } from "./root.store";
import type { RadarSchemaCatalog, RadarObject, RadarPropertySnapshot } from "../../services/radar/types";

const type = {
  id: "type",
  workspace: "w",
  key: "custom",
  name: "Custom",
  description: "",
  icon: "",
  is_system: false,
  is_active: true,
};
const object: RadarObject = {
  id: "object",
  workspace: "w",
  object_type: "type",
  object_type_detail: type,
  title: "Draft",
  content: "",
  version: 1,
  created_by: null,
  updated_by: null,
  created_at: "",
  updated_at: "",
};
const catalog = (revision: number, extra: Partial<RadarSchemaCatalog> = {}): RadarSchemaCatalog => ({
  status: "installed",
  schema_revision: revision,
  package_version: "3.2.0",
  authority_revision: "member",
  can_write: true,
  object_types: [type],
  property_definitions: [],
  relation_types: [],
  ...extra,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const setup = () => {
  const service = {
    getSchema: vi.fn().mockResolvedValue(catalog(1)),
    getProperties: vi.fn(),
    getRelations: vi.fn(),
    createObject: vi.fn().mockResolvedValue(object),
    listObjects: vi.fn().mockResolvedValue([object]),
  } as unknown as RadarClient;
  return { service, store: new RadarRootStore("w", service) };
};

describe("workspace schema revision cache", () => {
  it("rejects late old catalogs and accepts a higher revision regardless of request order", async () => {
    const { store, service } = setup();
    const old = deferred<RadarSchemaCatalog>(),
      current = deferred<RadarSchemaCatalog>();
    vi.mocked(service.getSchema!).mockReturnValueOnce(current.promise).mockReturnValueOnce(old.promise);
    const first = store.loadSchema(),
      second = store.loadSchema();
    old.resolve(catalog(1));
    await second;
    current.resolve(catalog(2));
    await first;
    expect(store.schemaRevision).toBe(2);
    vi.mocked(service.getSchema!).mockResolvedValue(catalog(1, { object_types: [] }));
    await store.loadSchema();
    expect(store.objectTypes).toHaveLength(1);
  });
  it("invalidates semantics without changing Object.version and rejects stale metadata", async () => {
    const { store, service } = setup();
    await store.loadSchema();
    await store.loadList();
    const first: RadarPropertySnapshot = { schema_revision: 1, object, properties: [] };
    vi.mocked(service.getProperties).mockResolvedValue(first);
    await store.loadProperties(object.id);
    expect(store.propertiesFor(object.id)).toEqual([]);
    vi.mocked(service.getSchema!).mockResolvedValue(catalog(2));
    await store.loadSchema();
    expect(store.objects.get(object.id)?.version).toBe(1);
    expect(store.propertiesFor(object.id)).toBeUndefined();
    await store.loadProperties(object.id);
    expect(store.propertiesFor(object.id)).toBeUndefined();
    vi.mocked(service.getProperties).mockResolvedValue({ ...first, schema_revision: 2 });
    await store.loadProperties(object.id);
    expect(store.propertiesFor(object.id)).toEqual([]);
  });
  it("does not accept mixed property/relation revisions", async () => {
    const { store, service } = setup();
    await store.loadSchema();
    vi.mocked(service.getSchema!).mockResolvedValue(catalog(2));
    vi.mocked(service.getProperties).mockResolvedValue({ schema_revision: 1, object, properties: [] });
    vi.mocked(service.getRelations).mockResolvedValue({ schema_revision: 2, object, relations: [] });
    await expect(store.loadObjectSemantics(object.id)).rejects.toThrow("Object changed while loading");
    expect(store.schemaRevision).toBe(2);
  });
  it("removes retired types from the current object cache", async () => {
    const { store, service } = setup();
    await store.loadSchema();
    await store.loadList();
    vi.mocked(service.getSchema!).mockResolvedValue(catalog(2, { object_types: [] }));
    await store.loadSchema();
    expect(store.listedObjects).toEqual([]);
  });
  it("updates permissions at an unchanged schema revision and prevents writing", async () => {
    const { store, service } = setup();
    await store.loadSchema();
    vi.mocked(service.getSchema!).mockResolvedValue(catalog(1, { authority_revision: "viewer", can_write: false }));
    await store.loadSchema();
    await expect(store.createObject({ object_type: "type", title: "Draft" })).rejects.toThrow("permission changed");
    expect(service.createObject).not.toHaveBeenCalled();
  });
  it("keeps the original schema precondition when retrying an uncertain intention", async () => {
    const { store, service } = setup();
    await store.loadSchema();
    vi.mocked(service.createObject)
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce(object);
    const payload = { object_type: "type", title: "Draft" };
    await expect(store.createObject(payload)).rejects.toBeDefined();
    vi.mocked(service.getSchema!).mockResolvedValue(catalog(2));
    await store.loadSchema();
    await store.createObject(payload);
    expect(vi.mocked(service.createObject).mock.calls[1][2]).toEqual(vi.mocked(service.createObject).mock.calls[0][2]);
    expect(vi.mocked(service.createObject).mock.calls[1][2]?.expected_schema_revision).toBe(1);
  });
});

it("marks authority unavailable when the membership is revoked", async () => {
  const { store, service } = setup();
  await store.loadSchema();
  vi.mocked(service.getSchema!).mockRejectedValue({ response: { status: 403 } });
  await expect(store.loadSchema()).rejects.toBeDefined();
  expect(store.canWrite).toBe(false);
  expect(store.authorityRevision).toBe("unavailable");
});

it("does not replace the current list with a delayed empty list from an older schema", async () => {
  const { store, service } = setup();
  await store.loadSchema();
  await store.loadList();
  const old: import("../../services/radar/types").RadarObjectCollection = [];
  old.schema_revision = 0;
  vi.mocked(service.listObjects).mockResolvedValue(old);
  await store.loadList();
  expect(store.listedObjects).toHaveLength(1);
});

it("discards inflight snapshots and endpoint summaries after access is lost", async () => {
  const { store, service } = setup();
  await store.loadSchema();
  await store.loadList();
  let resolve!: (value: { object: typeof object; properties: []; schema_revision: number }) => void;
  vi.mocked(service.getProperties).mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    })
  );
  const pending = store.loadProperties(object.id);
  vi.mocked(service.getSchema!).mockRejectedValueOnce({ response: { status: 403 } });
  await expect(store.loadSchema()).rejects.toBeDefined();
  resolve({ object, properties: [], schema_revision: 1 });
  await pending;
  expect(store.objects.size).toBe(0);
  expect(store.propertySnapshots.size).toBe(0);
  expect(store.listedObjects).toEqual([]);
});
