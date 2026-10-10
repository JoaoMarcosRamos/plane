/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { RadarMockupInbox } from "./inbox-screen";
import { RadarMockupPeople } from "./people-screen";
import { RadarMockupProject, RadarMockupProjects } from "./projects-screen";
import { RadarMockupReview } from "./review-screen";
import { RadarMockupToday } from "./today-screen";

/** One entry point for the app routes and the standalone preview. */
export function RadarMockupScreen({ screen, projectId }: { screen?: string; projectId?: string }) {
  if (projectId) return <RadarMockupProject projectId={projectId} />;
  if (screen === "inbox") return <RadarMockupInbox />;
  if (screen === "projetos") return <RadarMockupProjects />;
  if (screen === "pessoas") return <RadarMockupPeople />;
  if (screen === "revisao") return <RadarMockupReview />;
  return <RadarMockupToday />;
}
