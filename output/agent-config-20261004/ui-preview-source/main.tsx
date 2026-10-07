import React from "react";
import { createRoot } from "react-dom/client";
import { observer } from "mobx-react";
import { AgentConfigurationForm } from "../components/radar/agent-config-form";
import { RadarAgentConfigStore } from "../store/radar/agent-config.store";
import { agentEntry } from "../store/radar/__fixtures__/agent-config";
import "../styles/globals.css";
const key = "radar-agent-config-isolated-test";
const read = () => {
  const entry = JSON.parse(localStorage.getItem(key) || JSON.stringify(agentEntry));
  if (new URLSearchParams(location.search).has("readonly")) entry.can_edit = false;
  entry.object_options = [{id:"risk-1",title:"Licenciamento pode atrasar",type:"risk"}];
  return entry;
};
const store = new RadarAgentConfigStore("isolated-ui", {
  listAgentConfigurations: async () => [read()],
  getAgentConfiguration: async () => read(),
  updateAgentConfiguration: async (_, binding, payload) => {
    const entry = read();
    if (payload.expected_version !== entry.configuration.version) throw new Error("agent_config_stale");
    entry.configuration = {schema_version:"1.0", version:payload.expected_version+1, identity:payload.identity, role:payload.role, policies:payload.policies, permissions:payload.permissions};
    localStorage.setItem(key, JSON.stringify(entry));
    return entry;
  },
});
await store.load();
const App = observer(() => <main className="mx-auto flex w-full max-w-3xl flex-col gap-5 p-6"><h1 className="text-20 font-semibold">Agent configuration</h1><AgentConfigurationForm entry={store.entries[0]} store={store}/></main>);
createRoot(document.getElementById("root")!).render(<App/>);
