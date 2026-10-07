import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";
import { RadarService } from "@/services/radar/radar.service";
import { RadarCollaborationStore } from "./collaboration.store";
import { RadarRootStore } from "./root.store";

const CollaborationContext = createContext<RadarCollaborationStore | null>(null);
const RadarContext = createContext<RadarRootStore | null>(null);
export function RadarStoreProvider({ workspaceSlug, children }: { workspaceSlug: string; children: ReactNode }) {
  const [store] = useState(() => new RadarRootStore(workspaceSlug, new RadarService()));
  const [collaboration] = useState(() => new RadarCollaborationStore(workspaceSlug, new RadarService()));
  return (
    <RadarContext.Provider value={store}>
      <CollaborationContext.Provider value={collaboration}>{children}</CollaborationContext.Provider>
    </RadarContext.Provider>
  );
}
export function useRadarStore() {
  const store = useContext(RadarContext);
  if (!store) throw new Error("RadarStoreProvider is required.");
  return store;
}

export function useRadarCollaborationStore() {
  const store = useContext(CollaborationContext);
  if (!store) throw new Error("RadarStoreProvider is required.");
  return store;
}
