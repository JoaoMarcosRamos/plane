import type {
  RadarCapabilityContract,
  RadarObjectType,
  RadarPropertyData,
  RadarPropertyDefinition,
  RadarRelationType,
} from "../../services/radar/types";
import { contractFields, contractInput } from "./capability-form";
import type { RadarFormDrafts, RadarFormField } from "./capability-form";
import { parsePropertyDraft, propertyDraft, semanticLabel } from "./semantic-utils";

/** Creation form composed from workspace definitions and the type's declared creation capability (C03). */
export type RadarCreationForm = {
  type: RadarObjectType;
  capability: string;
  available: boolean;
  initialState: { property: string; value: string } | null;
  required: RadarPropertyDefinition[];
  optional: RadarPropertyDefinition[];
  parameters: RadarFormField[];
  mandatoryRelations: RadarRelationType[];
};

export function creationForm(
  type: RadarObjectType,
  definitions: RadarPropertyDefinition[],
  relationTypes: RadarRelationType[],
  capabilities: Record<string, RadarCapabilityContract>
): RadarCreationForm {
  const capability = type.rules?.creation?.capability ?? "CreateObject";
  const profile = capabilities[capability]?.creation;
  const lifecycle = type.rules?.lifecycle;
  // Server-owned inputs: derived values, the lifecycle state and transition stamps.
  const excluded = new Set<string>([
    ...(type.rules?.invariants ?? []).flatMap((rule) => (rule.kind === "product" ? [rule.result] : [])),
    ...(lifecycle ? [lifecycle.property] : []),
    ...(lifecycle?.transitions ?? []).flatMap((transition) => (transition.stamp ? [transition.stamp] : [])),
  ]);
  const own = definitions.filter((item) => item.object_type === type.id && item.is_active && !excluded.has(item.key));
  const needed = (item: RadarPropertyDefinition) =>
    (item.is_required && item.config.default === undefined) || !!profile?.required_properties.includes(item.key);
  return {
    type,
    capability,
    // A selected capability missing from the catalog is unusable; never fall back to another one.
    available: !!profile && (profile.types.includes("*") || profile.types.includes(type.key)),
    initialState: lifecycle ? { property: lifecycle.property, value: lifecycle.initial } : null,
    required: own.filter(needed),
    optional: own.filter((item) => !needed(item)),
    parameters: profile ? contractFields(profile.parameters) : [],
    mandatoryRelations: relationTypes.filter(
      (kind) =>
        kind.is_active &&
        kind.cardinality === "1..1" &&
        (kind.source_types.includes("*") || kind.source_types.includes(type.key)) &&
        (!kind.allowed_pairs.length || kind.allowed_pairs.some(([source]) => source === type.key))
    ),
  };
}

export function initialDrafts(form: RadarCreationForm): Record<string, string> {
  return Object.fromEntries(
    [...form.required, ...form.optional].map((item) => [
      item.key,
      item.config.default === undefined ? "" : propertyDraft(item, item.config.default),
    ])
  );
}

/** Typed properties and parameters. Unchanged defaults stay server-materialized, never resent. */
export function creationPayload(
  form: RadarCreationForm,
  drafts: Record<string, string>,
  parameterDrafts: RadarFormDrafts = {}
): { properties: Record<string, RadarPropertyData>; parameters: Record<string, unknown> } {
  if (!form.available) throw new Error("This type's creation capability is unavailable. Refresh the workspace schema.");
  const properties: Record<string, RadarPropertyData> = {};
  for (const item of form.required) {
    const draft = drafts[item.key] ?? "";
    if (!draft.trim()) throw new Error(`Enter ${semanticLabel(item.name).toLowerCase()} before creating this object.`);
    properties[item.key] = parsePropertyDraft(item, item.value_type === "string" ? draft.trim() : draft);
  }
  for (const item of form.optional) {
    const draft = drafts[item.key] ?? "";
    const pristine = item.config.default === undefined ? "" : propertyDraft(item, item.config.default);
    if (!draft.trim() || draft === pristine) continue;
    properties[item.key] = parsePropertyDraft(item, draft);
  }
  return { properties, parameters: contractInput(form.parameters, parameterDrafts) };
}
