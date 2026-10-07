import { describe, expect, it, vi } from "vitest";
import { RadarAgentConfigStore } from "./agent-config.store";
import { agentEntry } from "./__fixtures__/agent-config";
import { configUpdate } from "../../components/radar/agent-config-input";

const service = () => ({
  listAgentConfigurations: vi.fn().mockResolvedValue([structuredClone(agentEntry)]),
  getAgentConfiguration: vi.fn().mockResolvedValue(structuredClone(agentEntry)),
  updateAgentConfiguration: vi.fn().mockResolvedValue({
    ...structuredClone(agentEntry),
    configuration: { ...structuredClone(agentEntry.configuration), version: 2 },
  }),
});

describe("workspace-scoped agent configuration", () => {
  it("loads and saves the reviewed version, then refreshes from persistence", async () => {
    const client = service();
    const store = new RadarAgentConfigStore("team", client);
    await store.load();
    const data = configUpdate(agentEntry.configuration);
    await store.save("binding", data);
    expect(client.updateAgentConfiguration).toHaveBeenCalledWith("team", "binding", data);
    expect(store.entries[0].configuration.version).toBe(2);
    client.getAgentConfiguration.mockResolvedValue({ ...agentEntry, can_edit: false });
    await store.refresh("binding");
    expect(store.entries[0].can_edit).toBe(false);
  });
  it("keeps saved configuration unchanged when a write fails", async () => {
    const client = service();
    const store = new RadarAgentConfigStore("team", client);
    await store.load();
    client.updateAgentConfiguration.mockRejectedValue(new Error("agent_config_stale"));
    await expect(store.save("binding", configUpdate(agentEntry.configuration))).rejects.toThrow("agent_config_stale");
    expect(store.entries[0].configuration.version).toBe(1);
    expect(store.entries[0].configuration.identity.name).toBe("Copilot");
  });
  it("keeps two workspace caches independent and clears revoked bindings on reload", async () => {
    const client = service();
    const first = new RadarAgentConfigStore("first", client);
    const second = new RadarAgentConfigStore("second", client);
    await first.load();
    expect(second.entries).toEqual([]);
    client.listAgentConfigurations.mockResolvedValue([]);
    await first.load();
    expect(first.entries).toEqual([]);
    expect(client.listAgentConfigurations).toHaveBeenLastCalledWith("first");
  });
});
