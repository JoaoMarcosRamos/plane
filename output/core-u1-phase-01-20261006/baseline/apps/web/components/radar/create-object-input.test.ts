import { describe, expect, it } from "vitest";
import { creationFields, creationProperties } from "./create-object-input";

describe("shared specialized creation requirements", () => {
  it.each(["action", "risk"])("requires a described %s", (type) => {
    expect(() => creationProperties(type, {})).toThrow("description");
    expect(creationProperties(type, { description: "  Work or uncertain event  " })).toEqual({
      description: "Work or uncertain event",
    });
  });
  it("requires a reviewable proposed choice", () => {
    expect(creationFields("decision")).toEqual(["context", "decision", "rationale"]);
    expect(() => creationProperties("decision", { context: "Sandbox", decision: "Choice" })).toThrow("rationale");
    expect(
      creationProperties("decision", { context: "Sandbox", decision: "Choice", rationale: "Reason", status: "decided" })
    ).toEqual({ context: "Sandbox", decision: "Choice", rationale: "Reason" });
  });
  it("keeps generic creation independent of domain-specific forms", () => {
    expect(creationFields("objective")).toEqual([]);
    expect(creationProperties("custom_type", {})).toEqual({});
  });
});
