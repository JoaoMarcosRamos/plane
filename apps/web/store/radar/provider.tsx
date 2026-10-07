import { createContext, useContext, useState, useEffect } from "react";
import { observer } from "mobx-react";
import type { ReactNode } from "react";
import { RadarService } from "@/services/radar/radar.service";
import { useUser } from "@/hooks/store/user";
import { RadarCollaborationStore } from "./collaboration.store";
import { RadarRootStore } from "./root.store";

const CollaborationContext = createContext<RadarCollaborationStore | null>(null);
const RadarContext = createContext<RadarRootStore | null>(null);
export const RadarStoreProvider = observer(function RadarStoreProvider({
  workspaceSlug,
  children,
}: {
  workspaceSlug: string;
  children: ReactNode;
}) {
  const { data: user } = useUser();
  return (
    <RadarSessionProvider key={`${workspaceSlug}:${user?.id ?? "anonymous"}`} workspaceSlug={workspaceSlug}>
      {children}
    </RadarSessionProvider>
  );
});

function RadarSessionProvider({ workspaceSlug, children }: { workspaceSlug: string; children: ReactNode }) {
  const [store] = useState(() => new RadarRootStore(workspaceSlug, new RadarService()));
  const [collaboration] = useState(() => new RadarCollaborationStore(workspaceSlug, new RadarService()));
  useEffect(() => {
    const refresh = () => {
      void store.loadSchema().catch((cause: unknown) => console.error("RADAR schema refresh failed", cause));
    };
    refresh();
    window.addEventListener("focus", refresh);
    const interval = window.setInterval(refresh, 30_000);
    return () => {
      window.removeEventListener("focus", refresh);
      window.clearInterval(interval);
    };
  }, [store]);
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
