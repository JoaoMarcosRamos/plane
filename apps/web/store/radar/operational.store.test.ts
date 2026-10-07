import { beforeEach, describe, expect, it, vi } from "vitest";
import { RadarOperationalStore } from "./operational.store";
import type {
  RadarOperationalSnapshot,
  RadarOperationalHistory,
  RadarOperationalEntry,
} from "../../services/radar/operational.types";

const entry = (id: string): RadarOperationalEntry => ({
  id,
  kind: "review",
  schema_version: 1,
  object_version: 3,
  occurred_at: null,
  recorded_at: "2026-10-06T12:00:00Z",
  actor_type: "unknown",
  actor_id: null,
  origin: "legacy",
  source_record_id: "archive",
  source_provenance_id: null,
  provenance_id: "migration",
  command_id: "backfill",
  payload: { assessment: id },
});
const snapshot: RadarOperationalSnapshot = {
  object_id: "object",
  object_version: 3,
  schema_revision: 4,
  schema_version: 1,
  migration_required: false,
  deadline: null,
  executors: [],
  origins: {},
  operation_data: {},
};
const history: RadarOperationalHistory = {
  object_id: "object",
  object_version: 3,
  schema_revision: 4,
  items: [entry("one")],
  next_cursor: "page",
};
const client = () => ({
  getOperations: vi.fn().mockResolvedValue(structuredClone(snapshot)),
  getOperationalHistory: vi.fn().mockResolvedValue(structuredClone(history)),
});
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

describe("C18 bounded operational history", () => {
  it("loads both scoped reads with the chosen timezone and filter", async () => {
    const service = client(),
      store = new RadarOperationalStore("team", service);
    await store.load("object", 3, 4, "America/Bahia", "review");
    expect(service.getOperations).toHaveBeenCalledWith("team", "object", "America/Bahia");
    expect(service.getOperationalHistory).toHaveBeenCalledWith("team", "object", { kind: "review", limit: 20 });
    expect(store.entries.map((item) => item.id)).toEqual(["one"]);
    expect(new RadarOperationalStore("other", service).snapshot).toBeNull();
  });
  it.each([{ object_version: 2 }, { schema_revision: 3 }, { object_id: "other" }])(
    "rejects an obsolete or wrong Object response: %j",
    async (change) => {
      const service = client(),
        store = new RadarOperationalStore("team", service);
      service.getOperations.mockResolvedValueOnce({ ...snapshot, ...change });
      await store.load("object", 3, 4, "UTC");
      expect(store.snapshot).toBeNull();
      expect(store.entries).toEqual([]);
      expect(store.error).toBeTruthy();
    }
  );
  it("rejects mixed revisions even when each response is newer", async () => {
    const service = client(),
      store = new RadarOperationalStore("team", service);
    service.getOperations.mockResolvedValueOnce({ ...snapshot, object_version: 4 });
    await store.load("object", 3, 4, "UTC");
    expect(store.snapshot).toBeNull();
    expect(store.error).toBeTruthy();
  });
  it("ignores late loads from an old Object and after unmount", async () => {
    const service = client(),
      store = new RadarOperationalStore("team", service);
    let resolve!: (value: RadarOperationalSnapshot) => void;
    service.getOperations.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        })
    );
    const pending = store.load("old", 3, 4, "UTC");
    await store.load("object", 3, 4, "UTC");
    resolve({ ...snapshot, object_id: "old" });
    await pending;
    expect(store.snapshot?.object_id).toBe("object");
    service.getOperations.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        })
    );
    const unmounted = store.load("object", 3, 4, "UTC");
    store.clear();
    resolve(snapshot);
    await unmounted;
    expect(store.snapshot).toBeNull();
    expect(store.loading).toBe(false);
  });
  it("pages once while busy and deduplicates rows", async () => {
    const service = client(),
      store = new RadarOperationalStore("team", service);
    await store.load("object", 3, 4, "UTC", "review");
    service.getOperationalHistory.mockResolvedValueOnce({
      ...history,
      items: [entry("one"), entry("two")],
      next_cursor: null,
    });
    const pending = store.loadMore();
    await store.loadMore();
    await pending;
    expect(service.getOperationalHistory).toHaveBeenCalledTimes(2);
    expect(service.getOperationalHistory).toHaveBeenLastCalledWith("team", "object", {
      kind: "review",
      cursor: "page",
      limit: 20,
    });
    expect(store.entries.map((item) => item.id)).toEqual(["one", "two"]);
    expect(store.cursor).toBeNull();
  });
  it.each([403, 404, 409])("clears cached history when access/paging fails: %s", async (status) => {
    const service = client(),
      store = new RadarOperationalStore("team", service);
    await store.load("object", 3, 4, "UTC");
    service.getOperationalHistory.mockRejectedValueOnce({ response: { status } });
    await store.loadMore();
    expect(store.snapshot).toBeNull();
    expect(store.entries).toEqual([]);
    expect(store.cursor).toBeNull();
    expect(store.error).toBeTruthy();
  });
  it("discards earlier pages if metadata or Object changes", async () => {
    const service = client(),
      store = new RadarOperationalStore("team", service);
    await store.load("object", 3, 4, "UTC");
    service.getOperationalHistory.mockResolvedValueOnce({ ...history, schema_revision: 5 });
    await store.loadMore();
    expect(store.snapshot).toBeNull();
    expect(store.entries).toEqual([]);
  });
});
