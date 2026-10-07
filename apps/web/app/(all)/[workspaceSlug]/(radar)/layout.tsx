/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useParams } from "next/navigation";
import { RadarStoreProvider } from "@/store/radar/provider";
import { Outlet } from "react-router";
// components
import { RadarAppSidebar } from "@/components/radar/sidebar";

/**
 * RADAR app shell. Sits next to `(projects)` under the workspace layout, so auth, workspace membership,
 * top navigation, App Rail and global modals come from there. Deliberately absent: the Projects
 * sidebar, `ProjectsAppPowerKProvider` and the project / work item modals it mounts.
 */
export default function RadarLayout() {
  const { workspaceSlug } = useParams();
  if (!workspaceSlug) return null;
  return (
    <RadarStoreProvider key={workspaceSlug.toString()} workspaceSlug={workspaceSlug.toString()}>
      <div className="relative flex h-full w-full flex-col overflow-hidden rounded-lg border border-subtle">
        <div className="relative flex size-full overflow-hidden">
          <RadarAppSidebar />
          <main className="relative flex h-full w-full flex-col overflow-hidden bg-surface-1">
            <Outlet />
          </main>
        </div>
      </div>
    </RadarStoreProvider>
  );
}
