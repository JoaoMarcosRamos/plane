import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RadarAgentConfigStore } from "../../store/radar/agent-config.store";
import { agentEntry } from "../../store/radar/__fixtures__/agent-config";
import { AgentConfigurationForm } from "./agent-config-form";

describe("structured agent configuration form", () => {
  it("renders all four blocks from the real MobX cache without cloning a Proxy", async () => {
    const store = new RadarAgentConfigStore("team", {
      listAgentConfigurations: vi.fn().mockResolvedValue([structuredClone(agentEntry)]),
      getAgentConfiguration: vi.fn(),
      updateAgentConfiguration: vi.fn(),
    });
    await store.load();
    const html = renderToStaticMarkup(createElement(AgentConfigurationForm, { entry: store.entries[0], store }));
    for (const label of [
      "Identity / Soul",
      "Role",
      "Policies",
      "Permissions",
      "Save configuration",
      "Ask for evidence",
    ])
      expect(html).toContain(label);
  });
  it("shows saved configuration with disabled fields and no save action for a viewer", () => {
    const entry = { ...structuredClone(agentEntry), can_edit: false };
    const store = new RadarAgentConfigStore("team", {
      listAgentConfigurations: vi.fn(),
      getAgentConfiguration: vi.fn(),
      updateAgentConfiguration: vi.fn(),
    });
    const html = renderToStaticMarkup(createElement(AgentConfigurationForm, { entry, store }));
    expect(html).toContain("disabled");
    expect(html).toContain("A workspace administrator can edit this configuration.");
    expect(html).not.toContain("Save configuration");
    expect(html).toContain("Reload saved configuration");
  });
});
