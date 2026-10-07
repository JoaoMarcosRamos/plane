import type { RiskContext, RiskProposal, RiskQueue } from "../../../services/radar/risk-review.types";

export const riskContext: RiskContext = {
  objects: [
    {
      id: "risk",
      version: 1,
      type: "risk",
      title: "Licenciamento pode atrasar",
      content: "A licença pode atrasar",
      properties: {},
    },
    {
      id: "objective",
      version: 1,
      type: "objective",
      title: "Implantar Governança de IA",
      content: "Depende da licença",
      properties: {},
    },
  ],
  relations: [],
  truncated: false,
};
export const riskProposal: RiskProposal = {
  id: "proposal",
  run_id: "run",
  ordinal: 0,
  component: "relation",
  revision: 1,
  previous_id: null,
  status: "pending_approval",
  intent_hash: "a".repeat(64),
  command_name: "LinkObjects",
  input: { source_id: "risk", target_id: "objective", relation_type_id: "threatens" },
  expected_versions: { risk: 1, objective: 1 },
  reviewed_context: riskContext,
  suggestion: {
    explanation: "A licença pode ameaçar a implantação.",
    suggested_relation: { source_id: "risk", target_id: "objective", relation: "threatens" },
    suggested_action: null,
    confidence: 0.8,
    evidence: [
      { object_id: "risk", version: 1, field: "title", quote: "Licenciamento pode atrasar" },
      { object_id: "objective", version: 1, field: "content", quote: "Depende da licença" },
    ],
    context_used: [],
  },
  preview: { preview_only: true, changes: [], events: [] },
  result: { status: "pending_approval", created_ids: [], provenance_id: "trace", data: {} },
  approval: { status: "pending", rationale: "", expires_at: "2026-10-05T12:00:00Z" },
};
export const riskQueue: RiskQueue = {
  runs: [
    {
      run_id: "run",
      binding_id: "binding",
      created_at: "2026-10-05T11:00:00Z",
      context: riskContext,
      result: { summary: "Possible licensing threat", suggestions: [riskProposal.suggestion] },
    },
  ],
  proposals: [riskProposal],
};
