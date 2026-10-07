/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
import { PageHead } from "@/components/core/page-title";
import { RadarHeader } from "@/components/radar/header";
import { RadarSpikePlayground } from "@/components/radar/spike/playground";

export default function RadarSpikePage() {
  return (
    <>
      <AppHeader header={<RadarHeader crumbs={[{ label: "Spike Components" }]} />} />
      <ContentWrapper>
        <PageHead title="RADAR - Spike Components" />
        <RadarSpikePlayground />
      </ContentWrapper>
    </>
  );
}
