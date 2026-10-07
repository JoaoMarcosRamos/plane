import type { RadarCapabilityField, RadarObject } from "../../services/radar/types";
import { semanticLabel } from "./semantic-utils";

/** Form controls derived from a registered capability input contract (C03/C20). */
export type RadarFormField = {
  key: string;
  label: string;
  kind: "text" | "choice" | "object" | "objects" | "number" | "integer" | "datetime" | "boolean" | "unsupported";
  required: boolean;
  objectTypes: string[];
  choices: string[];
};
export type RadarFormDrafts = Record<string, string | string[]>;

function kindOf(field: RadarCapabilityField): RadarFormField["kind"] {
  if (field.type === "string") return field.choices ? "choice" : "text";
  if (field.type === "uuid") return "object";
  if (field.type === "array" && field.items?.type === "uuid") return "objects";
  if (field.type === "integer" || field.type === "number" || field.type === "datetime" || field.type === "boolean")
    return field.type;
  return "unsupported";
}

export function contractFields(
  contract: Record<string, RadarCapabilityField>,
  omit: Iterable<string> = []
): RadarFormField[] {
  const skipped = new Set(omit);
  return Object.entries(contract)
    .filter(([key]) => !skipped.has(key))
    .map(([key, field]) => ({
      key,
      label: semanticLabel(key.replace(/_ids?$/, "")),
      kind: kindOf(field),
      required: field.required,
      objectTypes: field.object_types ?? field.items?.object_types ?? ["*"],
      choices: field.choices ?? [],
    }));
}

/** Objects of the hinted types, excluding the current one; the server still validates references. */
export function objectOptions(objects: RadarObject[], types: string[], exclude?: string) {
  return objects
    .filter((item) => item.id !== exclude && (types.includes("*") || types.includes(item.object_type_detail.key)))
    .map((item) => ({ value: item.id, label: `${item.object_type_detail.name} · ${item.title}` }));
}

/** Build a typed input from drafts. Empty optional values are omitted rather than sent as blanks. */
export function contractInput(
  fields: RadarFormField[],
  drafts: RadarFormDrafts,
  base: Record<string, unknown> = {}
): Record<string, unknown> {
  const input: Record<string, unknown> = { ...base };
  for (const field of fields) {
    if (field.key in base) continue;
    const draft = drafts[field.key];
    const empty = Array.isArray(draft) ? draft.length === 0 : !draft?.trim();
    if (empty) {
      if (field.required) throw new Error(`Enter ${field.label.toLowerCase()}.`);
      continue;
    }
    if (field.kind === "unsupported") throw new Error(`${field.label} cannot be edited here.`);
    if (field.kind === "objects") input[field.key] = Array.isArray(draft) ? draft : [draft];
    else if (field.kind === "number" || field.kind === "integer") {
      const value = Number(draft);
      if (!Number.isFinite(value) || (field.kind === "integer" && !Number.isInteger(value)))
        throw new Error(`Enter a valid number for ${field.label.toLowerCase()}.`);
      input[field.key] = value;
    } else if (field.kind === "boolean") input[field.key] = draft === "true";
    else if (field.kind === "datetime") {
      const date = new Date(String(draft));
      if (Number.isNaN(date.getTime())) throw new Error(`Enter a date and time for ${field.label.toLowerCase()}.`);
      input[field.key] = date.toISOString();
    } else if (field.kind === "choice" && !field.choices.includes(String(draft)))
      throw new Error(`Select an available ${field.label.toLowerCase()}.`);
    else input[field.key] = Array.isArray(draft) ? draft[0] : draft.trim();
  }
  return input;
}
