import { beforeEach, describe, expect, it, vi } from "vitest";
import { RadarCollaborationStore } from "./collaboration.store";
import type { RadarCollaborationSnapshot } from "../../services/radar/collaboration.types";

const snapshot: RadarCollaborationSnapshot = {
  object_id: "object",
  object_version: 3,
  can_write: true,
  comments: [],
  attachments: [],
  activity: [],
  activity_next: null,
};
const makeClient = () => ({
  getCollaboration: vi.fn().mockResolvedValue(structuredClone(snapshot)),
  collaborationCommand: vi.fn().mockResolvedValue({ status: "executed" }),
  uploadObjectAttachment: vi.fn().mockResolvedValue({ status: "executed" }),
  downloadObjectAttachment: vi.fn().mockResolvedValue(new Blob(["evidence"])),
});
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

describe("Object collaboration persistence and retry", () => {
  it("scopes loads and commands to the workspace and reviewed Object", async () => {
    const client = makeClient();
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    expect(await store.command("AddComment", { object_id: "object", body: "Discussion" })).toBe(true);
    expect(client.collaborationCommand).toHaveBeenCalledWith(
      "team",
      "AddComment",
      { object_id: "object", body: "Discussion" },
      expect.objectContaining({ expected_versions: { object: 3 }, idempotency_key: expect.any(String) })
    );
    expect(client.getCollaboration).toHaveBeenCalledTimes(2);
    expect(new RadarCollaborationStore("other", client).snapshot).toBeNull();
  });
  it("reuses the exact intention after uncertain transport failures, even after reload", async () => {
    const client = makeClient();
    client.collaborationCommand.mockRejectedValueOnce(new Error("Response lost"));
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    expect(await store.command("AddComment", { object_id: "object", body: "Discussion" })).toBe(false);
    client.getCollaboration.mockResolvedValue({ ...snapshot, object_version: 4 });
    await store.load("object");
    await store.command("AddComment", { object_id: "object", body: "Discussion" });
    expect(client.collaborationCommand.mock.calls[0]).toEqual(client.collaborationCommand.mock.calls[1]);
  });
  it("requires reload on conflicts and creates a new reviewed intention", async () => {
    const client = makeClient();
    client.collaborationCommand.mockRejectedValueOnce({ response: { status: 409 } });
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    await store.command("EditComment", { object_id: "object", item_id: "comment", expected_revision: 1, body: "Edit" });
    expect(store.snapshot).toBeNull();
    expect(store.error).toContain("Reload and review");
    expect(await store.command("AddComment", { object_id: "object", body: "No load" })).toBe(false);
    await store.load("object");
    await store.command("EditComment", { object_id: "object", item_id: "comment", expected_revision: 2, body: "Edit" });
    expect(client.collaborationCommand.mock.calls[0][3].idempotency_key).not.toEqual(
      client.collaborationCommand.mock.calls[1][3].idempotency_key
    );
  });
  it("keeps successful mutations successful when the subsequent read fails", async () => {
    const client = makeClient();
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    client.getCollaboration.mockRejectedValueOnce(new Error("Read unavailable"));
    expect(await store.command("AddComment", { object_id: "object", body: "Saved" })).toBe(true);
    expect(store.snapshot).toBeNull();
    expect(store.error).toContain("Change saved");
    expect(client.collaborationCommand).toHaveBeenCalledTimes(1);
  });
  it("rejects guest mutations and clears inaccessible cached data", async () => {
    const client = makeClient();
    const store = new RadarCollaborationStore("team", client);
    client.getCollaboration.mockResolvedValueOnce({ ...snapshot, can_write: false });
    await store.load("object");
    expect(await store.command("AddComment", { object_id: "object", body: "Guest" })).toBe(false);
    expect(client.collaborationCommand).not.toHaveBeenCalled();
    client.getCollaboration.mockRejectedValueOnce({ response: { status: 403 } });
    await store.load("object");
    expect(store.snapshot).toBeNull();
    expect(store.error).toContain("membership");
  });
  it("ignores late responses from a previously opened Object", async () => {
    const client = makeClient();
    let resolve!: (snapshot: RadarCollaborationSnapshot) => void;
    client.getCollaboration.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        })
    );
    const store = new RadarCollaborationStore("team", client);
    const first = store.load("previous");
    await store.load("object");
    resolve({ ...snapshot, object_id: "previous" });
    await first;
    expect(store.snapshot?.object_id).toBe("object");
  });
  it("bounds files and preserves the upload key on failure", async () => {
    const client = makeClient();
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    expect(await store.upload("object", new File([], "empty.txt"))).toBe(false);
    expect(await store.upload("object", new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.txt"))).toBe(false);
    expect(client.uploadObjectAttachment).not.toHaveBeenCalled();
    const file = new File(["evidence"], "source.txt");
    client.uploadObjectAttachment.mockRejectedValueOnce({ response: { status: 503 } });
    expect(await store.upload("object", file)).toBe(false);
    expect(await store.upload("object", file)).toBe(true);
    expect(client.uploadObjectAttachment.mock.calls[0]).toEqual(client.uploadObjectAttachment.mock.calls[1]);
  });
  it("loads older activity without repeating records or changing comments", async () => {
    const client = makeClient();
    const record = {
      id: "one",
      command_id: "cmd",
      command_name: "AddComment",
      actor_type: "human",
      actor_id: "author",
      timestamp: "2026-10-05T12:00:00Z",
      reason: "Discussion",
      source: "session",
      outcome: "executed",
      correlation_id: "corr",
    };
    client.getCollaboration
      .mockResolvedValueOnce({ ...snapshot, activity: [record], activity_next: "one" })
      .mockResolvedValueOnce({ ...snapshot, activity: [record, { ...record, id: "two" }] });
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    await store.moreActivity();
    expect(client.getCollaboration).toHaveBeenLastCalledWith("team", "object", "one");
    expect(store.snapshot?.activity.map((item) => item.id)).toEqual(["one", "two"]);
    expect(store.snapshot?.activity_next).toBeNull();
  });
  it("reports failed downloads and never returns error content as a file", async () => {
    const client = makeClient();
    client.downloadObjectAttachment.mockRejectedValueOnce({ response: { status: 404 } });
    const store = new RadarCollaborationStore("team", client);
    expect(await store.download("object", "attachment")).toBeNull();
    expect(store.error).toContain("no longer available");
    expect(store.busy).toBe(false);
  });
  it("does not navigate back to an old Object after an in-flight mutation finishes", async () => {
    const client = makeClient();
    let resolve!: () => void;
    client.collaborationCommand.mockImplementationOnce(
      () =>
        new Promise<void>((done) => {
          resolve = done;
        })
    );
    const store = new RadarCollaborationStore("team", client);
    await store.load("object");
    const pending = store.command("AddComment", { object_id: "object", body: "Saved on previous Object" });
    client.getCollaboration.mockResolvedValueOnce({ ...snapshot, object_id: "next" });
    await store.load("next");
    resolve();
    await pending;
    expect(store.snapshot?.object_id).toBe("next");
    expect(client.getCollaboration).toHaveBeenCalledTimes(2);
  });
});
