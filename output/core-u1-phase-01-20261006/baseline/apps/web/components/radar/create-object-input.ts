import type { RadarPropertyData } from "../../services/radar/types";

export function creationFields(type: string): string[] {
  if (type === "decision") return ["context", "decision", "rationale"];
  return type === "action" || type === "risk" ? ["description"] : [];
}

export function creationProperties(type: string, draft: Record<string, string>): Record<string, RadarPropertyData> {
  return Object.fromEntries(
    creationFields(type).map((key) => {
      const value = draft[key]?.trim();
      if (!value) throw new Error(`Enter ${key} before creating this object.`);
      return [key, value];
    })
  );
}
