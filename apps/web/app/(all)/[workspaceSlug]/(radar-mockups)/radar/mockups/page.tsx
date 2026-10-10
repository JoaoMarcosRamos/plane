/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { PageHead } from "@/components/core/page-title";
import { RadarMockupScreen } from "@/components/radar/mockups/screens";

export default function RadarMockupsHomePage() {
  return (
    <>
      <PageHead title="RADAR - Mockups" />
      <RadarMockupScreen screen="hoje" />
    </>
  );
}
