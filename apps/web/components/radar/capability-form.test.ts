import { describe, expect, it } from "vitest";
import type { RadarCapabilityField, RadarObject } from "../../services/radar/types";
import { contractFields, contractInput, objectOptions } from "./capability-form";

const field = (
  type: RadarCapabilityField["type"],
  extra: Partial<RadarCapabilityField> = {}
): RadarCapabilityField => ({
  type,
  required: true,
  nullable: false,
  ...extra,
});
const contract = {
  action_id: field("uuid", { object_types: ["action"] }),
  outcome: field("string"),
  evidence_id: field("uuid", { object_types: ["document"] }),
  score: field("integer", { required: false }),
  measured_at: field("datetime", { required: false }),
  disposition: field("string", { required: false, choices: ["resolved", "accepted"] }),
  document: field("object", { required: false }),
};

describe("capability contract forms", () => {
  it("derives controls, labels and reference hints and omits prefilled inputs", () => {
    const fields = contractFields(contract, ["action_id"]);
    expect(fields.map((item) => [item.key, item.kind, item.label])).toEqual([
      ["outcome", "text", "Outcome"],
      ["evidence_id", "object", "Evidence"],
      ["score", "integer", "Score"],
      ["measured_at", "datetime", "Measured at"],
      ["disposition", "choice", "Disposition"],
      ["document", "unsupported", "Document"],
    ]);
    expect(fields[1].objectTypes).toEqual(["document"]);
  });

  it("types values, keeps the prefill and omits empty optional inputs", () => {
    const fields = contractFields(contract, ["action_id"]);
    expect(contractInput(fields, { outcome: " Signed ", evidence_id: "doc", score: "4" }, { action_id: "a" })).toEqual({
      action_id: "a",
      outcome: "Signed",
      evidence_id: "doc",
      score: 4,
    });
    expect(contractInput(fields, { outcome: "x", evidence_id: "d", measured_at: "2026-10-06T10:00" })).toHaveProperty(
      "measured_at"
    );
    expect(() => contractInput(fields, { evidence_id: "doc" })).toThrow("outcome");
    expect(() => contractInput(fields, { outcome: "x", evidence_id: "d", score: "1.5" })).toThrow("number");
    expect(() => contractInput(fields, { outcome: "x", evidence_id: "d", disposition: "maybe" })).toThrow(
      "disposition"
    );
    expect(() => contractInput(fields, { outcome: "x", evidence_id: "d", document: "{}" })).toThrow("cannot be edited");
  });

  it("lists only objects of the hinted types and never the current object", () => {
    const object = (id: string, key: string) =>
      ({ id, title: id, object_type_detail: { key, name: key } }) as unknown as RadarObject;
    const objects = [object("doc", "document"), object("act", "action"), object("self", "document")];
    expect(objectOptions(objects, ["document"], "self")).toEqual([{ value: "doc", label: "document · doc" }]);
    expect(objectOptions(objects, ["*"], "self").map((item) => item.value)).toEqual(["doc", "act"]);
  });
});
