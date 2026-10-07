/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** RADAR sidebar sections; each maps to `/:slug/radar/:section`. */
export const RADAR_SECTIONS = [
  { key: "today", label: "Today" },
  { key: "objects", label: "Objects" },
  { key: "risk-review", label: "Risk Review" },
  { key: "agent-config", label: "Agent configuration" },
] as const;

export type TRadarSectionKey = (typeof RADAR_SECTIONS)[number]["key"];

export const getRadarSection = (key: string | undefined) => RADAR_SECTIONS.find((section) => section.key === key);

/** Type routes have their own namespace, so a type named today never shadows a function. */
export const radarTypeSection = (key: string) => `type-${key}`;
export const radarTypeKey = (section: string) =>
  section.startsWith("type-")
    ? section.slice(5)
    : ({ decisions: "decision", risks: "risk" } as Record<string, string>)[section];
