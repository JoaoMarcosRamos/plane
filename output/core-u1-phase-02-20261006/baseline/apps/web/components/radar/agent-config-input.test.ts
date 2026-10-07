import { describe, expect, it } from "vitest";
import { agentEntry } from "../../store/radar/__fixtures__/agent-config";
import { configLines, configUpdate } from "./agent-config-input";

describe("agent config form serialization", () => {
  it("normalizes text lists and carries the exact reviewed version", () => {
    const config = structuredClone(agentEntry.configuration);
    config.identity.name = " Copilot ";
    config.policies.guidelines = [" Explain uncertainty ", "", " Ask for evidence"];
    config.permissions.fields = ["title", " "];
    const data = configUpdate(config);
    expect(data.expected_version).toBe(1);
    expect(data.identity.name).toBe("Copilot");
    expect(data.policies.guidelines).toEqual(["Explain uncertainty", "Ask for evidence"]);
    expect(data.permissions.fields).toEqual(["title"]);
    expect(config.identity.name).toBe(" Copilot ");
    expect(data).not.toHaveProperty("schema_version");
  });
  it("distinguishes all authorized Objects from an empty Object selection", () => {
    const config = structuredClone(agentEntry.configuration);
    expect(configUpdate(config).permissions.object_ids).toBeNull();
    config.permissions.object_ids = [];
    expect(configUpdate(config).permissions.object_ids).toEqual([]);
    expect(configLines("\n title \ncontent\n")).toEqual(["title", "content"]);
  });
  it("rejects empty required identity and role names", () => {
    const config = structuredClone(agentEntry.configuration);
    config.role.name = "  ";
    expect(() => configUpdate(config)).toThrow("Enter an identity name and a role name");
  });
});
