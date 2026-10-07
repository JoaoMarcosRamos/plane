import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
import { RadarHeader } from "@/components/radar/header";
import { RadarObjectPage } from "@/components/radar/object-page";
import type { Route } from "./+types/page";

export default function ObjectPage({ params }: Route.ComponentProps) {
  return (
    <>
      <AppHeader
        header={
          <RadarHeader
            crumbs={[{ label: "Objects", href: `/${params.workspaceSlug}/radar/objects/` }, { label: "Object" }]}
          />
        }
      />
      <ContentWrapper>
        <RadarObjectPage objectId={params.objectId} />
      </ContentWrapper>
    </>
  );
}
