export type RadarInvariant =
  | { kind: "ordered_dates"; first: string; second: string }
  | { kind: "product"; result: string; factors: string[] };

export type RadarLifecycleTransition = {
  from: string[];
  to: string;
  /** Registered capability that performs the transition; UpdateObject when omitted. */
  capability?: string;
  guard?: string;
  parameter?: string;
  stamp?: string;
};

export type RadarLifecycle = { property: string; initial: string; transitions: RadarLifecycleTransition[] };

/** Layout only (C21): never grants writes or removes guards. */
export type RadarPresentation = {
  narrative: string;
  sections: { key: string; label: string; properties: string[] }[];
};

/** Eligibility only: identity bindings and actor grants are provisioned separately. */
export type RadarRuntimeDescriptor =
  | { enabled: false }
  | {
      enabled: true;
      identity: { strategy: "dated_token_v1"; prefix: string };
      contexts: ("company" | "manager")[];
    };

export type RadarObjectType = {
  id: string;
  workspace: string;
  key: string;
  name: string;
  description: string;
  icon: string;
  is_system: boolean;
  is_active: boolean;
  rules?: {
    invariants?: RadarInvariant[];
    creation?: { capability: string };
    lifecycle?: RadarLifecycle;
    presentation?: RadarPresentation;
    runtime?: RadarRuntimeDescriptor;
  };
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
  schema_revision?: number;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  created_actor?: RadarActorSummary;
  updated_actor?: RadarActorSummary;
};

export type RadarObjectSummary = Omit<RadarObject, "content" | "object_type_detail"> & {
  content?: string;
  object_type_detail?: RadarObjectType;
};
export type RadarObjectQuery = {
  q?: string;
  object_type?: string;
  type_keys?: string;
  exclude?: string;
  capability?: string;
  relation_type?: string;
  object_id?: string;
  direction?: "outgoing" | "incoming";
  cursor?: string;
  limit?: number;
};
export type RadarObjectCollection = RadarObjectSummary[] & { schema_revision?: number; next_cursor?: string | null };

export type CreateRadarObject = {
  object_type: string;
  title: string;
  content?: string;
  properties?: Record<string, RadarPropertyData>;
  /** Composed-effect parameters of the type's declared creation capability. */
  parameters?: Record<string, unknown>;
};
export type UpdateRadarObject = { title?: string; content?: string };
export type RadarMutationContext = {
  expected_versions: Record<string, number>;
  expected_schema_revision?: number;
  idempotency_key?: string;
  reason?: string;
  approval_id?: string;
};
export type RadarPendingCommand = {
  status: "pending_approval";
  command_id: string;
  approval_id: string;
};

// Checked against the backend registry by test_core_u1_phase02.py.
export const RADAR_PROPERTY_KINDS = [
  "string",
  "string_list",
  "number",
  "integer",
  "boolean",
  "enum",
  "date",
  "datetime",
  "email",
  "uri",
  "user",
] as const;
export type RadarPropertyType = (typeof RADAR_PROPERTY_KINDS)[number];
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
export type RadarPropertySnapshot = {
  schema_revision?: number;
  object: RadarObject;
  properties: RadarObjectProperty[];
};
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
export type RadarRelationSnapshot = {
  schema_revision?: number;
  object: RadarObject;
  relations: RadarRelation[];
  endpoints?: RadarObjectSummary[];
  next_cursor?: string | null;
};
export type RadarRelationMutation = { relation: RadarRelation; objects: RadarObject[] };

export type RadarSchemaCatalog = {
  status: "uninitialized" | "installed" | "legacy";
  schema_revision: number;
  package_version: string | null;
  authority_revision: string;
  can_write: boolean;
  object_types: RadarObjectType[];
  property_definitions: RadarPropertyDefinition[];
  relation_types: RadarRelationType[];
  capabilities?: Record<string, RadarCapabilityContract>;
  transition_guards?: Record<
    string,
    { capability: string; human_only: boolean; types: string[]; dynamic_references: boolean }
  >;
};

export const RADAR_CAPABILITY_VALUE_TYPES = [
  "uuid",
  "datetime",
  "boolean",
  "integer",
  "number",
  "string",
  "json",
  "object",
  "array",
] as const;

export type RadarCapabilityField = {
  type: (typeof RADAR_CAPABILITY_VALUE_TYPES)[number];
  required: boolean;
  nullable: boolean;
  choices?: string[];
  default?: unknown;
  fields?: Record<string, RadarCapabilityField>;
  items?: RadarCapabilityField;
  additional_properties?: RadarCapabilityField;
  min_value?: number;
  max_value?: number;
  min_length?: number;
  max_length?: number;
  allow_blank?: boolean;
  allow_empty?: boolean;
  /** Object reference hint; the server still enforces the referenced type. */
  object_types?: string[];
};

export type RadarCapabilityContract = {
  name: string;
  command_version: 1;
  input: Record<string, RadarCapabilityField>;
  object_references: string[];
  dynamic_references: boolean;
  target_field: string | null;
  target_types: string[];
  policy: {
    human_only: boolean;
    conditional_human_only: boolean;
    conditional_review: boolean;
    agent_review_required: true;
    independent_reviewer: true;
    guards: "executable_handler";
  };
  planner: "transactional_effects_v1";
  transport: "command_envelope" | "multipart_upload";
  creation?: {
    types: string[];
    parameters: Record<string, RadarCapabilityField>;
    property_fields: string[];
    required_properties: string[];
    initial_states: string[];
  } | null;
  lifecycle?: { types: string[]; parameter: string | null; parameter_choices: string[] } | null;
  object_action?: string | null;
};

export type RadarEffectPlan = {
  contract: "transactional_effects_v1";
  preview_only: true;
  dependencies: Record<string, number>;
  required_versions: Record<string, number>;
  changes: { model: string; id: string; before: Record<string, unknown> | null; after: Record<string, unknown> }[];
  events: { event_type: string; payload: Record<string, unknown> }[];
  payloads: { attachment_id: string; size: number; sha256: string }[];
  authority: { object_types: string[]; fields: string[]; commands: string[]; human_only: boolean };
};

export type RadarCommandPreviewInput = {
  command_name: string;
  command_version: 1;
  input: Record<string, unknown>;
  reason: string;
  expected_schema_revision: number;
  evidence_ids?: string[];
};

export type RadarCommandPreview = {
  schema_revision: number;
  expected_versions: Record<string, number>;
  requires_review: boolean;
  effect_plan: RadarEffectPlan;
};

/** Server-computed, actor-specific capacities (C20). Advisory: commands revalidate every write. */
export type RadarCapacityReason =
  | "read_only_access"
  | "invalid_metadata"
  | "derived"
  | "lifecycle_state"
  | "lifecycle_stamp"
  | "measurement"
  | "decision_taken"
  | "evidence_in_use"
  | "mandatory_relation"
  | "approval_history"
  | "completion_evidence"
  | "decision_evidence"
  | "runtime_context"
  | "requires_input"
  | "not_declared_from_state"
  | (string & {});

export type RadarLayout = {
  source: "presentation" | "fallback" | "invalid_metadata";
  diagnostic: string | null;
  retired_references: string[];
  narrative: { field: string; label: string };
  content: { role: "narrative" | "notes"; label: string };
  sections: { key: string; label: string; properties: string[] }[];
  legacy_notes: boolean;
};
export type RadarFieldCapacity = {
  editable: boolean;
  removable: boolean;
  reason: RadarCapacityReason | null;
  options: string[] | null;
  governed_by: string[];
};
export type RadarTransitionCapacity = {
  to: string;
  capability: string;
  guard: string | null;
  parameter: string | null;
  stamp: string | null;
  human_only: boolean;
  available: boolean;
  reason: RadarCapacityReason | null;
  detail: string | null;
  requires_review: boolean;
};
export type RadarActionCapacity = {
  capability: string;
  target_field: string;
  prefill: Record<string, string>;
  transition: { to: string; stamp: string | null } | null;
  human_only: boolean;
  available: boolean;
  reason: RadarCapacityReason | null;
  detail: string | null;
  requires_review: boolean;
};
export type RadarObjectCapacities = {
  schema_revision: number;
  object: { id: string; version: number; object_type: string };
  can_write: boolean;
  metadata_errors: { section: string; detail: string }[];
  presentation: RadarLayout;
  envelope: Record<"title" | "content", { editable: boolean; reason: RadarCapacityReason | null }>;
  state: { property: string; current: string; initial: string; terminal: boolean } | null;
  fields: Record<string, RadarFieldCapacity>;
  transitions: RadarTransitionCapacity[];
  actions: RadarActionCapacity[];
  relations: Record<string, { removable: boolean; reason: RadarCapacityReason | null; requires_review: boolean }>;
};

export type RadarCommandResult = {
  command_id: string;
  status: "executed" | "noop" | "pending_approval";
  created_ids: string[];
  affected_ids: string[];
  versions_after: Record<string, number>;
  data: Record<string, unknown>;
};
