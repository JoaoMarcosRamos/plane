export type RiskContext = {
  objects: {
    id: string;
    version: number;
    type: string;
    title: string;
    content: string;
    properties: Record<string, unknown>;
  }[];
  relations: { id: string; source: string; target: string; type: string }[];
  truncated: boolean;
};
export type RiskSuggestion = {
  explanation: string;
  suggested_relation: { source_id: string; target_id: string; relation: "threatens" };
  suggested_action: { title: string; description: string; next_step: string; mitigates_risk_id: string } | null;
  confidence: number;
  evidence: { object_id: string; version: number; field: string; quote: string }[];
  context_used: string[];
};
export type RiskReviewOutput = { summary: string; suggestions: RiskSuggestion[] };
export type RiskCommandInput = {
  source_id?: string;
  target_id?: string;
  relation_type_id?: string;
  title?: string;
  description?: string;
  next_step?: string;
  mitigates_risk_ids?: string[];
  executor_person_ids?: string[];
};
export type RiskProposal = {
  id: string;
  run_id: string;
  ordinal: number;
  component: "relation" | "action";
  revision: number;
  previous_id: string | null;
  status: "pending_approval" | "rejected" | "executed" | "noop";
  intent_hash: string;
  suggestion: RiskSuggestion;
  command_name: "LinkObjects" | "CreateAction";
  input: RiskCommandInput;
  expected_versions: Record<string, number>;
  reviewed_context: RiskContext;
  preview: { preview_only: true; changes: unknown[]; events: unknown[] } | null;
  result: { status: string; created_ids: string[]; provenance_id: string; data: Record<string, unknown> };
  approval: { status: string; rationale: string; expires_at: string };
};
export type RiskRun = {
  run_id: string;
  binding_id: string;
  created_at: string;
  result: RiskReviewOutput | null;
  context: RiskContext;
};
export type RiskQueue = { runs: RiskRun[]; proposals: RiskProposal[] };
export type RiskRunStatus = {
  run_id: string;
  status: string;
  error?: string | null;
  result?: RiskReviewOutput;
  proposals?: RiskProposal[];
};
export type RiskResolution = {
  decision: "accept" | "edit" | "reject";
  rationale: string;
  intent_hash: string;
  edited_input?: RiskCommandInput;
};
