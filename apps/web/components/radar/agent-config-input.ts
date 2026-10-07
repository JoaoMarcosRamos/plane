import type { RadarAgentConfiguration, UpdateRadarAgentConfiguration } from "../../services/radar/agent-config.types";

export const configLines = (text: string): string[] =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export function configUpdate(configuration: RadarAgentConfiguration): UpdateRadarAgentConfiguration {
  if (!configuration.identity.name.trim() || !configuration.role.name.trim())
    throw new Error("Enter an identity name and a role name.");
  return {
    expected_version: configuration.version,
    identity: { ...configuration.identity, name: configuration.identity.name.trim() },
    role: { ...configuration.role, name: configuration.role.name.trim() },
    policies: {
      ...configuration.policies,
      guidelines: configLines(configuration.policies.guidelines.join("\n")),
      require_human_approval: true,
      read_only: true,
    },
    permissions: {
      ...configuration.permissions,
      commands: [...configuration.permissions.commands],
      object_types: configLines(configuration.permissions.object_types.join("\n")),
      fields: configLines(configuration.permissions.fields.join("\n")),
      object_ids: configuration.permissions.object_ids === null ? null : [...configuration.permissions.object_ids],
    },
  };
}
