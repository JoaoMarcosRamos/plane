import type { RadarCapacityReason } from "../../services/radar/types";
import { capabilityLabel } from "./semantic-utils";

/** Invalid configuration is reported apart from what is merely unavailable right now. */
export const isMetadataProblem = (reason: RadarCapacityReason | null) => reason === "invalid_metadata";

const MESSAGES: Record<string, string> = {
  read_only_access: "Read-only workspace access.",
  invalid_metadata: "Unavailable: this type's workspace configuration is invalid. Ask a workspace admin to review it.",
  derived: "Calculated from other properties.",
  lifecycle_state: "Changes follow this type's lifecycle.",
  measurement: "Updated by RecordMeasurement with evidence.",
  decision_taken: "A taken decision is immutable. Create a new decision instead.",
  evidence_in_use: "Used as approval or completion evidence. Create a new revision instead.",
  mandatory_relation: "Required relation. It cannot be removed on its own.",
  approval_history: "Part of the decision approval history.",
  completion_evidence: "Evidence of a completed action.",
  decision_evidence: "Evidence of a taken decision.",
  runtime_context: "Performed by the management runtime in a bound context.",
  not_declared_from_state: "Not available from the current state.",
  approval_stale: "Requires a current, independent approval of this version.",
  not_permitted: "You don't have the authority for this.",
};

export function capacityReason(reason: RadarCapacityReason | null, governedBy: string[] = [], detail?: string | null) {
  if (!reason || reason === "requires_input") return null;
  if (reason === "lifecycle_stamp") {
    const specialized = governedBy.filter((name) => name !== "UpdateObject");
    return specialized.length
      ? `Recorded by ${specialized.map(capabilityLabel).join(" or ")} when the transition happens.`
      : "Recorded automatically when the status changes.";
  }
  if (reason === "requirements_not_met" && detail) return detail;
  return MESSAGES[reason] ?? detail ?? "Unavailable right now.";
}
