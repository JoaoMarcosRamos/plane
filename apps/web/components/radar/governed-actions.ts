import type {
  RadarCapabilityContract,
  RadarObject,
  RadarObjectCapacities,
  RadarTransitionCapacity,
} from "../../services/radar/types";
import { contractFields } from "./capability-form";
import type { RadarFormField } from "./capability-form";
import { capacityReason, isMetadataProblem } from "./capacity-text";
import { capabilityLabel, semanticLabel } from "./semantic-utils";

export type RadarGovernedAction = {
  key: string;
  title: string;
  capability: string;
  available: boolean;
  reason: string | null;
  metadataProblem: boolean;
  humanOnly: boolean;
  requiresReview: boolean;
  fields: RadarFormField[];
  base: Record<string, unknown>;
};

/** Guarded/specialized transitions and Object actions; plain transitions stay in the state field. */
export function governedActions(
  object: RadarObject,
  capacities: RadarObjectCapacities,
  contracts: Record<string, Pick<RadarCapabilityContract, "input">>
): RadarGovernedAction[] {
  const state = capacities.state;
  const transition = (item: RadarTransitionCapacity): RadarGovernedAction => ({
    key: `transition:${item.capability}:${item.to}:${item.parameter ?? ""}`,
    title: item.parameter
      ? `${semanticLabel(item.parameter)} → ${semanticLabel(item.to)}`
      : `Move to ${semanticLabel(item.to)}`,
    capability: item.capability,
    available: item.available,
    reason: capacityReason(item.reason, [item.capability], item.detail),
    metadataProblem: isMetadataProblem(item.reason),
    humanOnly: item.human_only,
    requiresReview: item.requires_review,
    fields: [],
    base: { object_id: object.id, set_properties: { [state?.property ?? "status"]: item.to } },
  });
  const actionCapabilities = new Set(capacities.actions.map((item) => item.capability));
  return [
    ...capacities.transitions
      .filter((item) => (item.capability === "UpdateObject" ? !!item.guard : !actionCapabilities.has(item.capability)))
      .map(transition),
    ...capacities.actions.map((item) => ({
      key: `action:${item.capability}`,
      title: item.transition
        ? `${capabilityLabel(item.capability)} → ${semanticLabel(item.transition.to)}`
        : capabilityLabel(item.capability),
      capability: item.capability,
      available: item.available,
      reason: capacityReason(item.reason, [item.capability], item.detail),
      metadataProblem: isMetadataProblem(item.reason),
      humanOnly: item.human_only,
      requiresReview: item.requires_review,
      fields: contractFields(contracts[item.capability]?.input ?? {}, Object.keys(item.prefill)),
      base: item.prefill,
    })),
  ];
}
