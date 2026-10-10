/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

/**
 * RADAR app routes.
 *
 * The outer two layouts repeat the core workspace shell files on purpose: `mergeRoutes` merges
 * entries by `file`, so these deep-merge into the existing `(all)` -> `[workspaceSlug]` branch and
 * `(radar)` lands as a sibling of `(projects)` and `(settings)`. It inherits authentication, the
 * workspace wrapper, top navigation, App Rail and global modals, but none of the Projects app
 * chrome (sidebar, Power K provider, project/work item modals).
 */
export const radarRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(radar)/layout.tsx", [
        route(":workspaceSlug/radar", "./(all)/[workspaceSlug]/(radar)/radar/page.tsx"),
        // Phase 0 shell spike: component playground and mock object page
        route(":workspaceSlug/radar/spike", "./(all)/[workspaceSlug]/(radar)/radar/spike/page.tsx"),
        route(":workspaceSlug/radar/spike/object", "./(all)/[workspaceSlug]/(radar)/radar/spike/object/page.tsx"),
        route(
          ":workspaceSlug/radar/objects/:objectId",
          "./(all)/[workspaceSlug]/(radar)/radar/objects/[objectId]/page.tsx"
        ),
        // Sidebar sections (placeholders until the RADAR Core exists)
        route(":workspaceSlug/radar/:section", "./(all)/[workspaceSlug]/(radar)/radar/[section]/page.tsx"),
      ]),
      // RADAR_UX_VIEW mockups: proposed navigation and screens over mock data, own sidebar
      layout("./(all)/[workspaceSlug]/(radar-mockups)/layout.tsx", [
        route(":workspaceSlug/radar/mockups", "./(all)/[workspaceSlug]/(radar-mockups)/radar/mockups/page.tsx"),
        route(
          ":workspaceSlug/radar/mockups/projetos/:projectId",
          "./(all)/[workspaceSlug]/(radar-mockups)/radar/mockups/projetos/[projectId]/page.tsx"
        ),
        route(
          ":workspaceSlug/radar/mockups/:screen",
          "./(all)/[workspaceSlug]/(radar-mockups)/radar/mockups/[screen]/page.tsx"
        ),
      ]),
    ]),
  ]),
];
