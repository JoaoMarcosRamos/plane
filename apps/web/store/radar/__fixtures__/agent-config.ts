import type { RadarAgentConfigEntry } from "../../../services/radar/agent-config.types";

export const agentEntry: RadarAgentConfigEntry = {
  binding_id: "binding",
  agent_id: "agent",
  context: "company:test",
  can_edit: true,
  configuration: {
    schema_version: "1.0",
    version: 1,
    identity: { name: "Copilot", soul: "Ask for evidence" },
    role: { name: "Analyst", purpose: "Assess risks" },
    policies: { guidelines: ["Explain uncertainty"], read_only: true, require_human_approval: true },
    permissions: { commands: ["LinkObjects"], object_types: ["risk"], fields: ["title"], object_ids: null },
  },
  grant_ceiling: { commands: ["LinkObjects"], object_types: ["*"], fields: ["*"] },
  effective_permissions: { commands: ["LinkObjects"], object_types: ["risk"], fields: ["title"], object_ids: null },
  object_options: [],
  objects_truncated: false,
};
