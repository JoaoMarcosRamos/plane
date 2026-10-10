/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet } from "react-router";
import { RadarMockupShell } from "@/components/radar/mockups/shell";

/**
 * RADAR_UX_VIEW mockups. Sibling of the (radar) group so it can replace the RADAR sidebar with the
 * proposed navigation; inherits auth, workspace, top navigation and App Rail like (radar) does.
 */
export default function RadarMockupsLayout() {
  return (
    <RadarMockupShell>
      <Outlet />
    </RadarMockupShell>
  );
}
