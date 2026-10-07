import { describe, expect, it } from "vitest";
import type { RadarActorSummary } from "../../services/radar/types";
import { actorLabel } from "./actor-summary";

const summary: RadarActorSummary = {
  actor_type: "human",
  actor_id: "historical-id",
  display_name: "João",
  user_status: "available",
  source: "radar.session-api",
  timestamp: "2026-10-06T00:00:00Z",
  provenance_id: "provenance",
};

describe("RADAR authorship labels", () => {
  it("shows the human name from provenance", () => {
    expect(actorLabel(summary, null)).toBe("Human: João");
  });
  it.each(["agent", "system", "integration"] as const)("never calls a %s a deleted user", (actor_type) => {
    expect(actorLabel({ ...summary, actor_type, display_name: null, user_status: "not_applicable" }, null)).toBe(
      `${actor_type[0].toUpperCase()}${actor_type.slice(1)}: historical-id`
    );
  });
  it("distinguishes a deleted human from missing provenance", () => {
    expect(actorLabel({ ...summary, display_name: null, user_status: "deleted" }, null)).toBe(
      "Deleted user (historical-id)"
    );
    expect(actorLabel(undefined, null)).toBe("Unknown author");
    expect(
      actorLabel(
        { ...summary, actor_type: "unknown", actor_id: null, display_name: null, user_status: "unknown" },
        null
      )
    ).toBe("Unknown author");
    expect(actorLabel(undefined, "legacy-id")).toBe("Human (legacy-id)");
  });
});
