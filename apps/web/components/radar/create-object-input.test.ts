import { describe, expect, it } from "vitest";
import type {
  RadarCapabilityContract,
  RadarObjectType,
  RadarPropertyDefinition,
  RadarRelationType,
} from "../../services/radar/types";
import { creationForm, creationPayload, initialDrafts } from "./create-object-input";

const definition = (
  object_type: string,
  key: string,
  value_type: RadarPropertyDefinition["value_type"],
  config: RadarPropertyDefinition["config"] = {},
  is_required = false
): RadarPropertyDefinition => ({
  id: `${object_type}:${key}`,
  workspace: "w",
  object_type,
  key,
  name: key,
  value_type,
  config,
  is_required,
  is_system: true,
  is_active: true,
});
const type = (key: string, rules: RadarObjectType["rules"] = {}): RadarObjectType => ({
  id: key,
  workspace: "w",
  key,
  name: key,
  description: "",
  icon: "",
  is_system: true,
  is_active: true,
  rules,
});
const contract = (creation: RadarCapabilityContract["creation"]) => ({ creation }) as RadarCapabilityContract;
const capabilities: Record<string, RadarCapabilityContract> = {
  CreateObject: contract({
    types: ["*"],
    parameters: {},
    property_fields: [],
    required_properties: [],
    initial_states: [],
  }),
  CreateAction: contract({
    types: ["action"],
    parameters: {
      owner_person_id: { type: "uuid", required: false, nullable: false, object_types: ["person"] },
      executor_person_ids: {
        type: "array",
        required: false,
        nullable: false,
        items: { type: "uuid", required: true, nullable: false, object_types: ["person"] },
      },
    },
    property_fields: ["description", "priority"],
    required_properties: ["description"],
    initial_states: ["todo"],
  }),
};
const action = type("action", {
  creation: { capability: "CreateAction" },
  lifecycle: {
    property: "status",
    initial: "todo",
    transitions: [
      { from: ["todo"], to: "in_progress" },
      { from: ["todo"], to: "done", capability: "CompleteAction", stamp: "completed_at" },
    ],
  },
});
const definitions = [
  definition("action", "status", "enum", { choices: ["todo", "in_progress", "done"], default: "todo" }),
  definition("action", "description", "string", { default: "" }),
  definition("action", "priority", "enum", { choices: ["low", "medium"], default: "medium" }),
  definition("action", "due_date", "date"),
  definition("action", "completed_at", "datetime"),
  definition("action", "estimate", "integer", {}, true),
  definition("risk", "score", "integer", { default: 9 }),
];

describe("C03 creation form from workspace metadata", () => {
  it("asks for required metadata, hides server-owned fields and keeps the creation contract", () => {
    const form = creationForm(action, definitions, [], capabilities);
    expect(form.capability).toBe("CreateAction");
    expect(form.available).toBe(true);
    expect(form.required.map((item) => item.key)).toEqual(["description", "estimate"]);
    expect(form.optional.map((item) => item.key)).toEqual(["priority", "due_date"]);
    expect(form.initialState).toEqual({ property: "status", value: "todo" });
    expect(form.parameters.map((field) => [field.key, field.kind, field.objectTypes])).toEqual([
      ["owner_person_id", "object", ["person"]],
      ["executor_person_ids", "objects", ["person"]],
    ]);
  });

  it("builds typed properties and parameters without resending untouched defaults", () => {
    const form = creationForm(action, definitions, [], capabilities);
    const drafts = { ...initialDrafts(form), description: "  Negotiate  ", estimate: "3" };
    expect(creationPayload(form, drafts, { owner_person_id: "person", executor_person_ids: ["a", "b"] })).toEqual({
      properties: { description: "Negotiate", estimate: 3 },
      parameters: { owner_person_id: "person", executor_person_ids: ["a", "b"] },
    });
    expect(creationPayload(form, { ...drafts, priority: "low" }).properties.priority).toBe("low");
    expect(() => creationPayload(form, { ...drafts, estimate: "" })).toThrow("estimate");
    expect(() => creationPayload(form, { ...drafts, estimate: "2.5" })).toThrow("whole number");
    expect(() => creationPayload(form, { ...drafts, description: "   " })).toThrow("description");
  });

  it("excludes derived values and uses the generic capability for a type without a descriptor", () => {
    const risk = type("risk", { invariants: [{ kind: "product", result: "score", factors: ["a", "b"] }] });
    const form = creationForm(risk, definitions, [], capabilities);
    expect(form.capability).toBe("CreateObject");
    expect([...form.required, ...form.optional]).toEqual([]);
    expect(form.parameters).toEqual([]);
    expect(form.initialState).toBeNull();
  });

  it("never falls back when the declared capability is missing from the catalog", () => {
    const form = creationForm(action, definitions, [], { CreateObject: capabilities.CreateObject });
    expect(form.available).toBe(false);
    expect(() => creationPayload(form, {})).toThrow("unavailable");
  });

  it("announces mandatory relations the type must assemble later", () => {
    const commitsTo = {
      id: "r",
      key: "commits_to",
      forward_label: "commits_to",
      source_types: ["commitment"],
      target_types: ["action"],
      allowed_pairs: [],
      cardinality: "1..1",
      is_active: true,
    } as unknown as RadarRelationType;
    const form = creationForm(type("commitment"), [], [commitsTo], capabilities);
    expect(form.mandatoryRelations).toEqual([commitsTo]);
    expect(creationForm(action, definitions, [commitsTo], capabilities).mandatoryRelations).toEqual([]);
  });
});
