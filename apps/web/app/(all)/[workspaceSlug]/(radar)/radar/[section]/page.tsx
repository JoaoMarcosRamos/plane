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
import { getRadarSection } from "@/components/radar/sections";
import type { Route } from "./+types/page";

export default function RadarSectionPage({ params }: Route.ComponentProps) {
  const section = getRadarSection(params.section);
  const title = section?.label ?? "Not found";

  return (
    <>
      <AppHeader header={<RadarHeader crumbs={[{ label: title }]} />} />
      <ContentWrapper>
        <PageHead title={`RADAR - ${title}`} />
        {params.section === "today" ? (
          <RadarToday key={params.workspaceSlug} />
        ) : params.section === "objects" ? (
          <RadarObjectsList />
        ) : params.section === "risk-review" ? (
          <RadarRiskReview key={params.workspaceSlug} />
        ) : params.section === "agent-config" ? (
          <RadarAgentConfig key={params.workspaceSlug} />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 p-6">
            <h1 className="text-20 font-semibold text-primary">{title}</h1>
            <p className="text-13 text-secondary">
              {section
                ? "Placeholder. This view will list RADAR objects in a future slice."
                : `There is no RADAR section called "${params.section}".`}
            </p>
          </div>
        )}
      </ContentWrapper>
    </>
  );
}
