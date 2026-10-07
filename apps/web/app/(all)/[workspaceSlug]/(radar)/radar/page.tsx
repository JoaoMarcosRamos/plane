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
import { RadarHome } from "@/components/radar/home";

export default function RadarHomePage() {
  return (
    <>
      <AppHeader header={<RadarHeader />} />
      <ContentWrapper>
        <PageHead title="RADAR" />
        <RadarHome />
      </ContentWrapper>
    </>
  );
}
