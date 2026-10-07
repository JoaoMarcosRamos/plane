import { describe, expect, it } from "vitest";
import { dateText, deadlineText, instantText, operationalActor } from "./operational-text";
import type { RadarDeadline, RadarOperationalEntry } from "../../services/radar/operational.types";
const base: RadarDeadline = {
  source: null,
  timezone: "America/Bahia",
  conflict: false,
  overdue: false,
  due_date: null,
  due_at: null,
  effective_date: null,
  effective_at: null,
};
describe("C18 deadline and historical authorship labels", () => {
  it("renders a date without browser timezone conversion", () => {
    expect(dateText("2026-10-08")).toBe("08/10/2026");
    expect(deadlineText({ ...base, source: "due_date", due_date: "2026-10-08", effective_date: "2026-10-08" })).toBe(
      "08/10/2026"
    );
  });
  it("renders the declared instant in its explicit timezone", () => {
    expect(instantText("2026-10-08T02:30:12.123456Z", "America/Bahia")).toContain("07/10/2026");
    expect(instantText("2026-10-08T02:30:12Z", "America/Bahia")).toContain("23:30:12");
    expect(deadlineText({ ...base, source: "due_at", effective_at: "2026-10-08T02:30:12Z" })).toContain(
      "America/Bahia"
    );
  });
  it("shows both conflicting deadlines and preserves unknown legacy authorship", () => {
    const text = deadlineText({
      ...base,
      source: "conflict",
      conflict: true,
      due_date: "2026-10-08",
      due_at: "2026-10-08T02:30:12Z",
    });
    expect(text).toContain("08/10/2026");
    expect(text).toContain("07/10/2026");
    expect(text).toContain("Prazos divergentes");
    expect(operationalActor({ actor_type: "unknown", actor_id: "unproven" } as RadarOperationalEntry)).toBe(
      "Autoria original desconhecida (legado)"
    );
  });
});
