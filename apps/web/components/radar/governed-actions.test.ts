import { describe, expect, it } from "vitest";
import type { RadarObject, RadarObjectCapacities, RadarObjectProperty } from "../../services/radar/types";
import { governedActions } from "./governed-actions";
import { propertySections } from "./property-sections";

const object = { id: "decision" } as RadarObject;
const base: Omit<RadarObjectCapacities, "transitions" | "actions"> = {
  schema_revision: 3,
  object: { id: "decision", version: 2, object_type: "decision" },
  can_write: true,
  metadata_errors: [],
  presentation: {
    source: "presentation",
    diagnostic: null,
    retired_references: [],
    narrative: { field: "decision", label: "decision" },
    content: { role: "notes", label: "Notes" },
    sections: [
      { key: "reasoning", label: "Reasoning", properties: ["decision", "context", "missing"] },
      { key: "status", label: "Status", properties: ["status"] },
      { key: "empty", label: "Empty", properties: ["retired"] },
    ],
    legacy_notes: false,
  },
  envelope: { title: { editable: true, reason: null }, content: { editable: true, reason: null } },
  state: { property: "status", current: "proposed", initial: "proposed", terminal: false },
  fields: {},
  relations: {},
};
const transition = (to: string, extra: Partial<RadarObjectCapacities["transitions"][number]> = {}) => ({
  to,
  capability: "UpdateObject",
  guard: null,
  parameter: null,
  stamp: null,
  human_only: false,
  available: true,
  reason: null,
  detail: null,
  requires_review: false,
  ...extra,
});
const capacities: RadarObjectCapacities = {
  ...base,
  transitions: [
    transition("active"),
    transition("decided", { guard: "decision_approval", human_only: true, available: false, reason: "approval_stale" }),
    transition("closed", {
      capability: "ReviewObject",
      parameter: "resolved",
      available: false,
      reason: "runtime_context",
    }),
    transition("done", { capability: "CompleteAction", reason: "requires_input" }),
  ],
  actions: [
    {
      capability: "ApproveDecision",
      target_field: "decision_id",
      prefill: { decision_id: "decision", approver_person_id: "person" },
      transition: null,
      human_only: true,
      available: true,
      reason: null,
      detail: null,
      requires_review: false,
    },
    {
      capability: "CompleteAction",
      target_field: "action_id",
      prefill: { action_id: "decision" },
      transition: { to: "done", stamp: "completed_at" },
      human_only: false,
      available: false,
      reason: "invalid_metadata",
      detail: null,
      requires_review: false,
    },
  ],
};
const contracts = {
  ApproveDecision: {
    input: {
      decision_id: { type: "uuid" as const, required: true, nullable: false },
      rationale: { type: "string" as const, required: true, nullable: false },
      approver_person_id: { type: "uuid" as const, required: true, nullable: false },
    },
  },
};

describe("C20 governed actions from server capacities", () => {
  it("keeps plain transitions in the state field and lists guarded, runtime and Object actions", () => {
    const actions = governedActions(object, capacities, contracts);
    expect(actions.map((item) => item.key)).toEqual([
      "transition:UpdateObject:decided:",
      "transition:ReviewObject:closed:resolved",
      "action:ApproveDecision",
      "action:CompleteAction",
    ]);
    const take = actions[0];
    expect(take.base).toEqual({ object_id: "decision", set_properties: { status: "decided" } });
    expect(take.reason).toBe("Requires a current, independent approval of this version.");
    expect(take.humanOnly).toBe(true);
    expect(actions[1].reason).toContain("management runtime");
  });

  it("asks only for inputs the server did not prefill and flags invalid metadata apart", () => {
    const [, , approve, complete] = governedActions(object, capacities, contracts);
    expect(approve.fields.map((field) => field.key)).toEqual(["rationale"]);
    expect(approve.base).toEqual({ decision_id: "decision", approver_person_id: "person" });
    expect(complete.title).toBe("Complete action → Done");
    expect(approve.title).toBe("Approve decision");
    expect(complete.metadataProblem).toBe(true);
    expect(approve.metadataProblem).toBe(false);
  });
});

describe("C21 property sections", () => {
  const row = (key: string) => ({ definition: { key } }) as unknown as RadarObjectProperty;
  const rows = ["decision", "context", "status", "consequences"].map(row);
  it("follows the server layout, skips the narrative slot and empty sections", () => {
    const sections = propertySections(rows, capacities.presentation);
    expect(sections.map((section) => [section.key, section.rows.map((item) => item.definition.key)])).toEqual([
      ["reasoning", ["context"]],
      ["status", ["status"]],
    ]);
  });
  it("uses the documented single-section fallback while capacities load", () => {
    expect(propertySections(rows, undefined)).toEqual([{ key: "properties", label: "Properties", rows }]);
  });
});
