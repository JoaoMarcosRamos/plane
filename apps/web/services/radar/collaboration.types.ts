export type RadarCollaborationItem = {
  id: string;
  revision: number;
  created_by: string | null;
  author: string;
  created_at: string;
  updated_at: string;
  created_provenance_id: string;
  last_provenance_id: string;
  can_edit: boolean;
  can_delete: boolean;
};
export type RadarComment = RadarCollaborationItem & { body: string };
export type RadarAttachment = RadarCollaborationItem & { filename: string; size: number; sha256: string };
export type RadarActivity = {
  id: string;
  command_id: string;
  command_name: string;
  actor_type: string;
  actor_id: string;
  timestamp: string;
  reason: string;
  source: string;
  outcome: string;
  correlation_id: string;
};
export type RadarCollaborationSnapshot = {
  object_id: string;
  object_version: number;
  can_write: boolean;
  comments: RadarComment[];
  attachments: RadarAttachment[];
  activity: RadarActivity[];
  activity_next: string | null;
};
export type RadarCollaborationCommand =
  | "AddComment"
  | "EditComment"
  | "DeleteComment"
  | "RenameAttachment"
  | "DeleteAttachment";
export type RadarCollaborationInput = {
  object_id: string;
  item_id?: string;
  expected_revision?: number;
  body?: string;
  filename?: string;
};
export type RadarCollaborationResult = { status: "executed" | "noop"; command_id: string; provenance_id: string };
