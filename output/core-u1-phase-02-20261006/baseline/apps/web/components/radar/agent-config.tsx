import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { RadarService } from "@/services/radar/radar.service";
import { RadarAgentConfigStore } from "@/store/radar/agent-config.store";
import { useRadarStore } from "@/store/radar/provider";
import { AgentConfigurationForm } from "./agent-config-form";
import { semanticError } from "./semantic-utils";

export const RadarAgentConfig = observer(function RadarAgentConfig() {
  const { workspaceSlug } = useRadarStore();
  const [store] = useState(() => new RadarAgentConfigStore(workspaceSlug, new RadarService()));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await store.load();
    } catch (cause) {
      setError(semanticError(cause));
    } finally {
      setLoading(false);
    }
  }, [store]);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 p-6">
      <div>
        <h1 className="text-20 font-semibold">Agent configuration</h1>
        <p className="text-13 text-secondary">Identity, role, policies and permissions for your RADAR copilot.</p>
      </div>
      {loading && <p role="status">Loading configuration…</p>}
      {error && (
        <div>
          <p role="alert" className="text-13 text-danger-primary">
            {error}
          </p>
          <Button variant="secondary" size="sm" stretch="auto" label="Try again" onClick={() => void load()} />
        </div>
      )}
      {!loading && !error && store.entries.length === 0 && (
        <p className="text-13 text-secondary">
          No agent is linked to your account in this workspace. Ask a workspace administrator to provision a RADAR
          agent.
        </p>
      )}
      {!loading &&
        !error &&
        store.entries.map((entry) => <AgentConfigurationForm key={entry.binding_id} entry={entry} store={store} />)}
    </div>
  );
});
