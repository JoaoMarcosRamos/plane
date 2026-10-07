import type {
  RadarObject,
  RadarPropertyData,
  RadarPropertyDefinition,
  RadarRelation,
  RadarRelationType,
} from "../../services/radar/types";

export const semanticLabel = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
export type RelationDirection = "outgoing" | "incoming";

export function relationCandidates(
  kind: RadarRelationType,
  object: RadarObject,
  objects: RadarObject[],
  direction: RelationDirection,
  relations: RadarRelation[]
) {
  if (!kind.is_active || kind.workspace !== object.workspace) return [];
  return objects.filter((other) => {
    const source = direction === "outgoing" ? object : other;
    const target = direction === "outgoing" ? other : object;
    const sourceKey = source.object_type_detail.key;
    const targetKey = target.object_type_detail.key;
    if (other.workspace !== object.workspace || !other.object_type_detail.is_active) return false;
    if (source.id === target.id && !kind.allow_self) return false;
    if (!kind.source_types.includes("*") && !kind.source_types.includes(sourceKey)) return false;
    if (!kind.target_types.includes("*") && !kind.target_types.includes(targetKey)) return false;
    if (kind.allowed_pairs.length && !kind.allowed_pairs.some(([a, b]) => a === sourceKey && b === targetKey))
      return false;
    if (
      relations.some((edge) => edge.relation_type === kind.id && edge.source === source.id && edge.target === target.id)
    )
      return false;
    return (
      (kind.cardinality !== "0..1" && kind.cardinality !== "1..1") ||
      !relations.some((edge) => edge.relation_type === kind.id && edge.source === source.id)
    );
  });
}

export function propertyDraft(definition: RadarPropertyDefinition, value: RadarPropertyData | null): string {
  if (value === null) return "";
  if (definition.value_type === "string_list") return Array.isArray(value) ? value.join("\n") : String(value);
  if (definition.value_type === "datetime" && typeof value === "string") {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime()))
      return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
  return String(value);
}

export function parsePropertyDraft(definition: RadarPropertyDefinition, draft: string): RadarPropertyData {
  const type = definition.value_type;
  if (type === "number" || type === "integer") {
    if (!draft.trim()) throw new Error("Enter a number.");
    const value = Number(draft);
    if (!Number.isFinite(value) || (type === "integer" && !Number.isInteger(value)))
      throw new Error(type === "integer" ? "Enter a whole number." : "Enter a finite number.");
    if (
      (definition.config.min !== undefined && value < definition.config.min) ||
      (definition.config.max !== undefined && value > definition.config.max)
    )
      throw new Error("Value is outside the allowed range.");
    return value;
  }
  if (type === "boolean") {
    if (draft !== "true" && draft !== "false") throw new Error("Select Yes or No.");
    return draft === "true";
  }
  if (type === "enum" && !definition.config.choices?.includes(draft)) throw new Error("Select an available value.");
  if (type === "string_list") return draft ? draft.split("\n") : [];
  if (type === "datetime") {
    const date = new Date(draft);
    if (!draft || Number.isNaN(date.getTime())) throw new Error("Enter a date and time.");
    return date.toISOString();
  }
  if (type === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(draft)) throw new Error("Enter a date.");
  if (type === "user" && !draft) throw new Error("Select a workspace member.");
  return draft;
}

const messages = (value: unknown): string[] => {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(messages);
  if (value && typeof value === "object") return Object.values(value).flatMap(messages);
  return [];
};

export function semanticError(cause: unknown): string {
  if (cause && typeof cause === "object" && "response" in cause) {
    const response = cause.response;
    if (response && typeof response === "object" && "status" in response && response.status === 409)
      return "This change is based on an older snapshot. Refresh and review before trying again.";
    if (response && typeof response === "object" && "data" in response) {
      const detail = messages(response.data).slice(0, 3).join(" ");
      if (detail) return detail;
    }
  }
  return cause instanceof Error ? cause.message : "Could not save. Please try again.";
}
