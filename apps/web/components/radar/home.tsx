import { observer } from "mobx-react";
import Link from "next/link";
import { useRadarStore } from "@/store/radar/provider";
import { RADAR_SECTIONS, radarTypeSection } from "./sections";

export const RadarHome = observer(function RadarHome() {
  const store = useRadarStore();
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-24 font-semibold">RADAR</h1>
        <p className="text-16 text-secondary">Human–Agent Operating System</p>
      </header>
      <nav aria-label="Workspace tools" className="flex flex-wrap gap-4">
        {RADAR_SECTIONS.map((section) => (
          <Link
            key={section.key}
            className="text-accent-primary underline"
            href={`/${store.workspaceSlug}/radar/${section.key}/`}
          >
            {section.label}
          </Link>
        ))}
      </nav>
      {store.schemaStatus === "uninitialized" ? (
        <p role="status">A workspace admin must install the workspace schema to use Objects.</p>
      ) : (
        <nav aria-label="Object types" className="flex flex-wrap gap-4">
          {store.objectTypes.map((type) => (
            <Link
              key={type.id}
              className="text-accent-primary underline"
              href={`/${store.workspaceSlug}/radar/${radarTypeSection(type.key)}/`}
            >
              {type.name}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
});
