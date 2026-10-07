import { describe, expect, it, vi } from "vitest";
import { RadarRiskReviewStore } from "./risk-review.store";
import { riskProposal, riskQueue } from "./__fixtures__/risk-review";

const client = () => ({
  listAgentConfigurations: vi.fn().mockResolvedValue([]),
  listRiskReviews: vi.fn().mockResolvedValue(structuredClone(riskQueue)),
  startRiskReview: vi.fn().mockResolvedValue({ run_id: "run", status: "queued" }),
  prepareRiskReview: vi.fn().mockResolvedValue({ run_id: "run", status: "completed" }),
  resolveRiskProposal: vi.fn().mockResolvedValue(structuredClone(riskProposal)),
});

describe("Risk Review human loop", () => {
  it("keeps the Today proposal in scope after a human resolution", async () => {
    const api = client();
    const store = new RadarRiskReviewStore("workspace", api);
    await store.load("proposal");
    await store.resolve(riskProposal, { decision: "reject", rationale: "Reviewed" });
    expect(api.listRiskReviews).toHaveBeenNthCalledWith(1, "workspace", "proposal");
    expect(api.listRiskReviews).toHaveBeenNthCalledWith(2, "workspace", "proposal");
  });
  it("loading saved suggestions never accepts or runs commands", async () => {
    const api = client();
    const store = new RadarRiskReviewStore("workspace", api);
    await store.load();
    expect(store.queue.proposals[0].suggestion.evidence).toHaveLength(2);
    expect(api.resolveRiskProposal).not.toHaveBeenCalled();
    expect(api.startRiskReview).not.toHaveBeenCalled();
  });
  it("retries the same run intention after a lost response", async () => {
    const api = client();
    api.startRiskReview.mockRejectedValueOnce(new Error("lost"));
    const store = new RadarRiskReviewStore("workspace", api);
    await expect(store.start("binding", ["risk", "objective"])).rejects.toThrow("lost");
    await store.start("binding", ["objective", "risk"]);
    expect(api.startRiskReview.mock.calls[0][3]).toBe(api.startRiskReview.mock.calls[1][3]);
    expect(store.activeRunId).toBe("run");
    await store.check("run");
    expect(store.activeRunId).toBeNull();
  });
  it.each(["accept", "reject", "edit"] as const)("%s sends the saved hash and human feedback", async (decision) => {
    const api = client();
    const store = new RadarRiskReviewStore("workspace", api);
    await store.resolve(riskProposal, {
      decision,
      rationale: "Reviewed",
      ...(decision === "edit" ? { edited_input: { ...riskProposal.input, target_id: "project" } } : {}),
    });
    expect(api.resolveRiskProposal).toHaveBeenCalledWith("workspace", "proposal", {
      decision,
      rationale: "Reviewed",
      intent_hash: riskProposal.intent_hash,
      ...(decision === "edit" ? { edited_input: { ...riskProposal.input, target_id: "project" } } : {}),
    });
    expect(api.listRiskReviews).toHaveBeenCalledTimes(1);
  });
  it("failed resolution preserves the saved proposal for retry", async () => {
    const api = client();
    api.resolveRiskProposal.mockRejectedValue(new Error("revision_conflict"));
    const store = new RadarRiskReviewStore("workspace", api);
    await store.load();
    await expect(
      store.resolve(store.queue.proposals[0], { decision: "accept", rationale: "Reviewed" })
    ).rejects.toThrow("revision_conflict");
    expect(store.queue.proposals[0].status).toBe("pending_approval");
  });
});
