import { makeAutoObservable, runInAction } from "mobx";
import { v4 as uuidv4 } from "uuid";
import type { RadarService } from "../../services/radar/radar.service";
import type { RadarAgentConfigEntry } from "../../services/radar/agent-config.types";
import type { RiskProposal, RiskQueue, RiskResolution } from "../../services/radar/risk-review.types";

type RiskClient = Pick<
  RadarService,
  "listAgentConfigurations" | "listRiskReviews" | "startRiskReview" | "prepareRiskReview" | "resolveRiskProposal"
>;

export class RadarRiskReviewStore {
  entries: RadarAgentConfigEntry[] = [];
  queue: RiskQueue = { runs: [], proposals: [] };
  activeRunId: string | null = null;
  statuses: Record<string, string> = {};
  private intention: { payload: string; key: string } | null = null;
  private focusedProposalId: string | undefined;
  constructor(
    readonly workspaceSlug: string,
    private readonly service: RiskClient
  ) {
    makeAutoObservable<RadarRiskReviewStore, "service" | "intention">(
      this,
      { workspaceSlug: false, service: false, intention: false },
      { autoBind: true }
    );
  }
  async load(proposalId = this.focusedProposalId) {
    this.focusedProposalId = proposalId;
    const [entries, queue] = await Promise.all([
      this.service.listAgentConfigurations(this.workspaceSlug),
      proposalId
        ? this.service.listRiskReviews(this.workspaceSlug, proposalId)
        : this.service.listRiskReviews(this.workspaceSlug),
    ]);
    runInAction(() => {
      this.entries = entries;
      this.queue = queue;
    });
  }
  async start(bindingId: string, rootIds: string[]) {
    // oxlint-disable-next-line unicorn/no-array-sort -- The project targets ES2022; sort only a copy.
    const payload = JSON.stringify([bindingId, [...rootIds].sort()]);
    if (this.intention?.payload !== payload) this.intention = { payload, key: uuidv4() };
    const result = await this.service.startRiskReview(this.workspaceSlug, bindingId, rootIds, this.intention.key);
    this.intention = null;
    runInAction(() => {
      this.activeRunId = result.run_id;
      this.statuses[result.run_id] = result.status;
    });
    await this.load();
    return result;
  }
  async check(runId: string) {
    const result = await this.service.prepareRiskReview(this.workspaceSlug, runId);
    runInAction(() => {
      this.statuses[runId] = result.status;
      if (!["queued", "running"].includes(result.status)) this.activeRunId = null;
    });
    if (result.status === "completed") await this.load();
    return result;
  }
  async resolve(proposal: RiskProposal, resolution: Omit<RiskResolution, "intent_hash">) {
    const result = await this.service.resolveRiskProposal(this.workspaceSlug, proposal.id, {
      ...resolution,
      intent_hash: proposal.intent_hash,
    });
    await this.load();
    return result;
  }
}
