export type RadarAgentPermissions = {
  commands: string[];
  object_types: string[];
  fields: string[];
  object_ids: string[] | null;
};

export type RadarAgentConfiguration = {
  schema_version: "1.0";
  version: number;
  identity: { name: string; soul: string };
  role: { name: string; purpose: string };
  policies: { guidelines: string[]; require_human_approval: true; read_only: true };
  permissions: RadarAgentPermissions;
};

export type RadarAgentConfigEntry = {
  binding_id: string;
  agent_id: string;
  context: string;
  can_edit: boolean;
  configuration: RadarAgentConfiguration;
  effective_permissions: RadarAgentPermissions;
  grant_ceiling: Pick<RadarAgentPermissions, "commands" | "object_types" | "fields">;
  object_options: { id: string; title: string; type: string }[];
  objects_truncated: boolean;
};

export type UpdateRadarAgentConfiguration = Pick<
  RadarAgentConfiguration,
  "identity" | "role" | "policies" | "permissions"
> & { expected_version: number };
