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
import { RadarObjectsList } from "@/components/radar/objects-list";
import { RadarRiskReview } from "@/components/radar/risk-review";
import { RadarToday } from "@/components/radar/today";
import { RadarAgentConfig } from "@/components/radar/agent-config";
import { observer } from "mobx-react";
import { useRadarStore } from "@/store/radar/provider";
import { getRadarSection, radarTypeKey } from "@/components/radar/sections";
import type { Route } from "./+types/page";

const RadarSectionPage = observer(function RadarSectionPage({ params }: Route.ComponentProps) {
  const store = useRadarStore();
  const typeKey = radarTypeKey(params.section);
  const type = store.objectTypes.find((item) => item.key === typeKey);
  const section = getRadarSection(params.section);
  const title = type?.name ?? section?.label ?? (typeKey ? "Objects" : "Not found");

  return (
    <>
      <AppHeader header={<RadarHeader crumbs={[{ label: title }]} />} />
      <ContentWrapper>
        <PageHead title={`RADAR - ${title}`} />
        {params.section === "today" ? (
          <RadarToday key={params.workspaceSlug} />
        ) : params.section === "objects" || typeKey ? (
          <RadarObjectsList key={params.section} typeKey={typeKey} />
        ) : params.section === "risk-review" ? (
          <RadarRiskReview key={params.workspaceSlug} />
        ) : params.section === "agent-config" ? (
          <RadarAgentConfig key={params.workspaceSlug} />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 p-6">
            <h1 className="text-20 font-semibold text-primary">{title}</h1>
            <p className="text-13 text-secondary">{`There is no RADAR section called "${params.section}".`}</p>
          </div>
        )}
      </ContentWrapper>
    </>
  );
});
export default RadarSectionPage;
