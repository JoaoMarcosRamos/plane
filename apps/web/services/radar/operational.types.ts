export type RadarOperationalKind = "delegation" | "review" | "measurement";
export type RadarDeadline = {
  source: "due_at" | "due_date" | "conflict" | null;
  timezone: string;
  conflict: boolean;
  overdue: boolean;
  due_date: string | null;
  due_at: string | null;
  effective_at: string | null;
  effective_date: string | null;
};
export type RadarOperationalEntry = {
  id: string;
  kind: RadarOperationalKind;
  schema_version: number;
  object_version: number | null;
  occurred_at: string | null;
  recorded_at: string;
  actor_type: "human" | "agent" | "system" | "integration" | "unknown";
  actor_id: string | null;
  origin: "command" | "legacy";
  source_record_id: string | null;
  source_provenance_id: string | null;
  provenance_id: string | null;
  command_id: string | null;
  payload: Record<string, unknown>;
};
export type RadarOperationalSnapshot = {
  object_id: string;
  object_version: number;
  schema_revision: number;
  schema_version: number;
  migration_required: boolean;
  deadline: RadarDeadline | null;
  executors: string[];
  origins: Record<string, { entry_id: string; origin: string; provenance_id: string | null }>;
  operation_data: Record<string, Record<string, unknown>>;
};
export type RadarOperationalHistory = {
  object_id: string;
  object_version: number;
  schema_revision: number;
  items: RadarOperationalEntry[];
  next_cursor: string | null;
};
