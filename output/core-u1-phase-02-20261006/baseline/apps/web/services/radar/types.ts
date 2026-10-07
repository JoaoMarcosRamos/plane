export type RadarInvariant =
  | { kind: "ordered_dates"; first: string; second: string }
  | { kind: "product"; result: string; factors: string[] };

export type RadarObjectType = {
  id: string;
  workspace: string;
  key: string;
  name: string;
  description: string;
  icon: string;
  is_system: boolean;
  is_active: boolean;
  rules?: { invariants?: RadarInvariant[] };
};

export type RadarActorSummary = {
  actor_type: "human" | "agent" | "system" | "integration" | "unknown";
  actor_id: string | null;
  display_name: string | null;
  user_status: "available" | "deleted" | "unknown" | "not_applicable";
  source: string | null;
  timestamp: string;
  provenance_id: string | null;
};

export type RadarObject = {
  id: string;
  workspace: string;
  object_type: string;
  object_type_detail: RadarObjectType;
  title: string;
  content: string;
  version: number;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  created_actor?: RadarActorSummary;
  updated_actor?: RadarActorSummary;
};

export type CreateRadarObject = {
  object_type: string;
  title: string;
  content?: string;
  properties?: Record<string, RadarPropertyData>;
};
export type UpdateRadarObject = { title?: string; content?: string };
export type RadarMutationContext = {
  expected_versions: Record<string, number>;
  idempotency_key?: string;
  reason?: string;
  approval_id?: string;
};
export type RadarPendingCommand = {
  status: "pending_approval";
  command_id: string;
  approval_id: string;
};

export type RadarPropertyType =
  | "string"
  | "string_list"
  | "number"
  | "integer"
  | "boolean"
  | "enum"
  | "date"
  | "datetime"
  | "email"
  | "uri"
  | "user";
export type RadarPropertyData = string | number | boolean | string[];
export type RadarPropertyDefinition = {
  id: string;
  workspace: string;
  object_type: string;
  key: string;
  name: string;
  value_type: RadarPropertyType;
  config: { default?: RadarPropertyData; min?: number; max?: number; choices?: string[]; terminal?: string[] };
  is_required: boolean;
  is_system: boolean;
  is_active: boolean;
};
export type RadarPropertyValue = {
  id: string;
  workspace: string;
  object: string;
  definition: string;
  value: RadarPropertyData;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};
export type RadarObjectProperty = {
  definition: RadarPropertyDefinition;
  stored_value: RadarPropertyValue | null;
  value: RadarPropertyData | null;
  has_value: boolean;
};
export type RadarPropertySnapshot = { object: RadarObject; properties: RadarObjectProperty[] };
export type RadarRelationType = {
  id: string;
  workspace: string;
  key: string;
  forward_label: string;
  reverse_label: string;
  description: string;
  source_types: string[];
  target_types: string[];
  allowed_pairs: [string, string][];
  cardinality: "0..1" | "0..n" | "1..1";
  allow_self: boolean;
  is_system: boolean;
  is_active: boolean;
};
export type RadarRelation = {
  id: string;
  workspace: string;
  relation_type: string;
  relation_type_detail: RadarRelationType;
  source: string;
  target: string;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};
export type CreateRadarRelation = { relation_type: string; source: string; target: string };
export type RadarRelationSnapshot = { object: RadarObject; relations: RadarRelation[] };
export type RadarRelationMutation = { relation: RadarRelation; objects: RadarObject[] };
