import type { RadarLayout, RadarObjectProperty } from "../../services/radar/types";

/** Sections from the server layout; the narrative property is rendered by the Object Page itself. */
export function propertySections(
  rows: RadarObjectProperty[],
  layout: Pick<RadarLayout, "narrative" | "sections"> | undefined
) {
  if (!layout) return [{ key: "properties", label: "Properties", rows }];
  const byKey = new Map(rows.map((row) => [row.definition.key, row]));
  return layout.sections
    .map((section) => ({
      key: section.key,
      label: section.label,
      rows: section.properties
        .filter((key) => key !== layout.narrative.field)
        .map((key) => byKey.get(key))
        .filter((row): row is RadarObjectProperty => !!row),
    }))
    .filter((section) => section.rows.length > 0);
}
