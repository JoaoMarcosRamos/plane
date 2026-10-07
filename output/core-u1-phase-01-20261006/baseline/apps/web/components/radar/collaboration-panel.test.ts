import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RadarCollaborationPanel } from "./collaboration-panel";
import type { RadarCollaborationSnapshot } from "../../services/radar/collaboration.types";

const state = vi.hoisted(() => ({
  snapshot: null as RadarCollaborationSnapshot | null,
  loading: false,
  busy: false,
  error: null as string | null,
}));
vi.mock("@/store/radar/provider", () => ({ useRadarCollaborationStore: () => ({ ...state, load: vi.fn() }) }));
vi.mock("@makeplane/propel/components/button", () => ({
  Button: (props: { label: string; disabled?: boolean }) =>
    createElement("button", { disabled: props.disabled }, props.label),
}));
vi.mock("@makeplane/propel/components/text-area-field", () => ({
  TextAreaField: (props: { id: string; label: string }) =>
    createElement("textarea", { id: props.id, "aria-label": props.label }),
}));
vi.mock("@makeplane/propel/components/input-field", () => ({ InputField: () => createElement("input") }));
const item = {
  id: "comment",
  revision: 1,
  created_by: "author",
  author: "Author",
  created_at: "2026-10-05T12:00:00Z",
  updated_at: "2026-10-05T12:00:00Z",
  created_provenance_id: "p",
  last_provenance_id: "p",
  can_edit: true,
  can_delete: true,
};
const render = (canWrite = true) =>
  renderToStaticMarkup(createElement(RadarCollaborationPanel, { objectId: "object", objectVersion: 1, canWrite }));
beforeEach(() => {
  state.loading = state.busy = false;
  state.error = null;
  state.snapshot = {
    object_id: "object",
    object_version: 1,
    can_write: true,
    comments: [{ ...item, body: "<script>evil</script>" }],
    attachments: [{ ...item, id: "attachment", filename: "evidence.txt", size: 3, sha256: "sha" }],
    activity: [
      {
        id: "p",
        command_id: "cmd",
        command_name: "AddComment",
        actor_id: "author",
        actor_type: "human",
        timestamp: item.created_at,
        reason: "Discussion",
        source: "session",
        outcome: "executed",
        correlation_id: "correlation",
      },
    ],
    activity_next: null,
  };
});
describe("minimal collaboration UI", () => {
  it("renders escaped plain text, real audit metadata and file download controls", () => {
    const html = render();
    expect(html).toContain("&lt;script&gt;evil&lt;/script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).toContain("Add Comment");
    expect(html).toContain("human: author");
    expect(html).toContain("Download evidence.txt");
    expect(html).toContain("New comment");
  });
  it("respects both Plane membership and server item authority", () => {
    expect(render(false)).not.toContain("Add comment");
    expect(render(false)).not.toContain("Remove attachment");
    state.snapshot!.comments[0].can_edit = false;
    state.snapshot!.comments[0].can_delete = false;
    expect(render()).not.toContain("Edit comment");
    expect(render()).not.toContain("Delete comment");
    state.snapshot!.can_write = false;
    expect(render()).not.toContain("Upload attachment");
    expect(render()).toContain("Download evidence.txt");
  });
  it("shows actionable failure and loading states without cached content", () => {
    state.snapshot = null;
    state.error = "Reload and review";
    expect(render()).toContain('role="alert"');
    expect(render()).not.toContain("evidence.txt");
    state.loading = true;
    expect(render()).toContain("Loading collaboration");
  });
});
