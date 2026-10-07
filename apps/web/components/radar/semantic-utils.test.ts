import { describe, expect, it } from "vitest";
import type {
  RadarObject,
  RadarPropertyDefinition,
  RadarRelation,
  RadarRelationType,
} from "../../services/radar/types";
import { parsePropertyDraft, propertyDraft, relationCandidates, semanticError } from "./semantic-utils";

const object = (id: string, key: string, workspace = "workspace"): RadarObject => ({
  id,
  workspace,
  object_type: key,
  object_type_detail: {
    id: key,
    workspace,
    key,
    name: key,
    description: "",
    icon: "",
    is_system: true,
    is_active: true,
  },
  title: id,
  content: "",
  version: 1,
  created_by: null,
  updated_by: null,
  created_at: "",
  updated_at: "",
});
const definition = (
  value_type: RadarPropertyDefinition["value_type"],
  config: RadarPropertyDefinition["config"] = {}
): RadarPropertyDefinition => ({
  id: "def",
  workspace: "workspace",
  object_type: "objective",
  key: "test",
  name: "Test",
  value_type,
  config,
  is_required: false,
  is_system: true,
  is_active: true,
});
const kind: RadarRelationType = {
  id: "creates",
  workspace: "workspace",
  key: "creates",
  forward_label: "creates",
  reverse_label: "created_by",
  description: "",
  source_types: ["decision", "management_item"],
  target_types: ["action", "risk"],
  allowed_pairs: [
    ["decision", "action"],
    ["management_item", "risk"],
  ],
  cardinality: "0..n",
  allow_self: false,
  is_active: true,
  is_system: true,
};
const edge = (source: string, target: string, relation_type = "creates"): RadarRelation => ({
  id: "edge",
  workspace: "workspace",
  source,
  target,
  relation_type,
  relation_type_detail: kind,
  created_by: null,
  updated_by: null,
  created_at: "",
  updated_at: "",
});

describe("semantic property input", () => {
  it("keeps scalar types, empty text and lists without coercing booleans", () => {
    expect(parsePropertyDraft(definition("integer"), "3")).toBe(3);
    expect(parsePropertyDraft(definition("number"), "2.5")).toBe(2.5);
    expect(parsePropertyDraft(definition("boolean"), "false")).toBe(false);
    expect(parsePropertyDraft(definition("string"), "")).toBe("");
    expect(parsePropertyDraft(definition("string_list"), "First\nSecond")).toEqual(["First", "Second"]);
    expect(parsePropertyDraft(definition("string_list"), "")).toEqual([]);
    expect(propertyDraft(definition("string_list"), ["First", "Second"])).toBe("First\nSecond");
  });
  it.each(["", "false", "Infinity", "NaN", "1.5"])("rejects invalid whole numbers: %s", (value) => {
    expect(() => parsePropertyDraft(definition("integer"), value)).toThrow();
  });
  it("enforces bounds, closed vocabularies and explicit boolean choices", () => {
    expect(() => parsePropertyDraft(definition("number", { min: 0, max: 100 }), "101")).toThrow();
    expect(() => parsePropertyDraft(definition("enum", { choices: ["active"] }), "closed")).toThrow();
    expect(() => parsePropertyDraft(definition("boolean"), "")).toThrow();
    expect(parsePropertyDraft(definition("enum", { choices: ["active"] }), "active")).toBe("active");
  });
  it("converts a local datetime to a timezone-aware value and round trips it", () => {
    const input = "2026-10-03T12:30";
    const parsed = parsePropertyDraft(definition("datetime"), input);
    expect(typeof parsed).toBe("string");
    expect(propertyDraft(definition("datetime"), parsed)).toBe(input);
    expect(() => parsePropertyDraft(definition("datetime"), "")).toThrow();
  });
  it("extracts backend field errors without dropping the user's reason", () => {
    expect(semanticError({ response: { data: { due_date: ["due_date cannot precede start_date."] } } })).toBe(
      "due_date cannot precede start_date."
    );
    expect(semanticError(new Error("Offline"))).toBe("Offline");
    expect(semanticError({ response: { status: 409, data: { code: "revision_conflict" } } })).toBe(
      "This change is based on an older snapshot. Refresh and review before trying again."
    );
  });
});

describe("semantic relation choices", () => {
  const decision = object("decision", "decision");
  const action = object("action", "action");
  const risk = object("risk", "risk");
  it("respects allowed_pairs as well as source and target types", () => {
    expect(relationCandidates(kind, decision, [action, risk], "outgoing", [])).toEqual([action]);
    expect(relationCandidates(kind, action, [decision, risk], "incoming", [])).toEqual([decision]);
  });
  it("excludes cross-workspace objects, inactive types and duplicate edges", () => {
    const inactive = {
      ...action,
      id: "inactive",
      object_type_detail: { ...action.object_type_detail, is_active: false },
    };
    expect(
      relationCandidates(kind, decision, [action, inactive, object("foreign", "action", "other")], "outgoing", [
        edge(decision.id, action.id),
      ])
    ).toEqual([]);
  });
  it("limits outgoing 0..1 and rejects forbidden self-links", () => {
    const owns = {
      ...kind,
      id: "owns",
      source_types: ["*"],
      target_types: ["*"],
      allowed_pairs: [],
      cardinality: "0..1" as const,
    };
    expect(
      relationCandidates(owns, decision, [action, risk], "outgoing", [edge(decision.id, action.id, "owns")])
    ).toEqual([]);
    expect(relationCandidates(owns, decision, [decision], "outgoing", [])).toEqual([]);
    expect(relationCandidates({ ...owns, allow_self: true }, decision, [decision], "outgoing", [])).toEqual([decision]);
  });
  it("limits mandatory 1..1 targets in both directions", () => {
    const mandatory = { ...kind, id: "mandatory", cardinality: "1..1" as const };
    const another = object("another", "action");
    const existing = edge(decision.id, action.id, mandatory.id);
    expect(relationCandidates(mandatory, decision, [another], "outgoing", [existing])).toEqual([]);
    expect(relationCandidates(mandatory, another, [decision], "incoming", [existing])).toEqual([]);
    expect(relationCandidates(mandatory, decision, [action], "outgoing", [])).toEqual([action]);
  });
});
