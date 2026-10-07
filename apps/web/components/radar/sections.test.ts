import { describe, expect, it } from "vitest";
import { RADAR_SECTIONS, radarTypeKey, radarTypeSection } from "./sections";

describe("metadata type routes", () => {
  it("navigates arbitrary custom types independently of functional sections", () => {
    for (const key of ["custom_type", "today", "objects", "meeting"]) {
      expect(radarTypeKey(radarTypeSection(key))).toBe(key);
      expect(RADAR_SECTIONS.some((section) => section.key === radarTypeSection(key))).toBe(false);
    }
  });
  it("keeps legacy Decisions/Risks bookmarks as views while removing placeholders", () => {
    expect(radarTypeKey("decisions")).toBe("decision");
    expect(radarTypeKey("risks")).toBe("risk");
    expect(radarTypeKey("unknown")).toBeUndefined();
    expect(RADAR_SECTIONS.map((section) => section.key)).toEqual(["today", "objects", "risk-review", "agent-config"]);
  });
});
