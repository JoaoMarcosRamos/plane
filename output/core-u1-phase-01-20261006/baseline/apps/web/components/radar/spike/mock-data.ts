/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Hardcoded fixtures for the Phase 0 shell spike. These are NOT the RADAR Core model: there is no
 * ObjectType / PropertyDefinition / RelationType here, only enough shape to exercise Plane's generic
 * UI against something that is not a work item.
 */

export type TRadarSpikeObjectType = "objective" | "project" | "decision" | "action" | "risk";

export type TRadarSpikeStatus = "planned" | "active" | "done";

export type TRadarSpikeRelationType = "SUPPORTS" | "AFFECTS" | "CREATES" | "THREATENS";

export type TRadarSpikeObject = {
  id: string;
  title: string;
  type: TRadarSpikeObjectType;
  status: TRadarSpikeStatus;
};

export type TRadarSpikeRelation = {
  id: string;
  type: TRadarSpikeRelationType;
  sourceId: string;
  targetId: string;
};

export const RADAR_SPIKE_TYPES: { key: TRadarSpikeObjectType; label: string }[] = [
  { key: "objective", label: "Objective" },
  { key: "project", label: "Project" },
  { key: "decision", label: "Decision" },
  { key: "action", label: "Action" },
  { key: "risk", label: "Risk" },
];

export const RADAR_SPIKE_STATUSES: { key: TRadarSpikeStatus; label: string }[] = [
  { key: "planned", label: "Planned" },
  { key: "active", label: "Active" },
  { key: "done", label: "Done" },
];

export const RADAR_SPIKE_OBJECTS: TRadarSpikeObject[] = [
  { id: "objective-ai-governance", title: "Implantar Governança de IA", type: "objective", status: "active" },
  { id: "project-ai-sandbox", title: "Sandbox IA", type: "project", status: "active" },
  { id: "decision-github-enterprise", title: "Adotar GitHub Enterprise", type: "decision", status: "done" },
  { id: "action-negotiate-licenses", title: "Negociar licenças", type: "action", status: "planned" },
  { id: "action-map-use-cases", title: "Mapear casos de uso de IA", type: "action", status: "done" },
  { id: "risk-licensing-delay", title: "Licenciamento pode atrasar", type: "risk", status: "active" },
];

export const RADAR_SPIKE_RELATIONS: TRadarSpikeRelation[] = [
  { id: "rel-1", type: "SUPPORTS", sourceId: "project-ai-sandbox", targetId: "objective-ai-governance" },
  { id: "rel-2", type: "AFFECTS", sourceId: "decision-github-enterprise", targetId: "project-ai-sandbox" },
  { id: "rel-3", type: "CREATES", sourceId: "decision-github-enterprise", targetId: "action-negotiate-licenses" },
  { id: "rel-4", type: "THREATENS", sourceId: "risk-licensing-delay", targetId: "decision-github-enterprise" },
];

export const getRadarSpikeTypeLabel = (type: TRadarSpikeObjectType) =>
  RADAR_SPIKE_TYPES.find((option) => option.key === type)?.label ?? type;

export const getRadarSpikeStatusLabel = (status: TRadarSpikeStatus) =>
  RADAR_SPIKE_STATUSES.find((option) => option.key === status)?.label ?? status;

/** Buckets object ids by one of their fields, preserving the given group order. */
export const groupRadarSpikeObjectIds = <K extends "type" | "status">(
  objects: TRadarSpikeObject[],
  field: K,
  groupKeys: TRadarSpikeObject[K][]
): Record<string, string[]> => {
  const grouped: Record<string, string[]> = Object.fromEntries(groupKeys.map((key) => [key, []]));
  for (const object of objects) grouped[object[field]]?.push(object.id);
  return grouped;
};
