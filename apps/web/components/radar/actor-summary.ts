import type { RadarActorSummary } from "../../services/radar/types";

export function actorLabel(summary: RadarActorSummary | undefined, legacyId: string | null): string {
  if (!summary || summary.actor_type === "unknown") return legacyId ? `Human (${legacyId})` : "Unknown author";
  const label = { human: "Human", agent: "Agent", system: "System", integration: "Integration" }[summary.actor_type];
  if (summary.actor_type === "human" && summary.user_status === "deleted") return `Deleted user (${summary.actor_id})`;
  return `${label}: ${summary.display_name || summary.actor_id}`;
}
