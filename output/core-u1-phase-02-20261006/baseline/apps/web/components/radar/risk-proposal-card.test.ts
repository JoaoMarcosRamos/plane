import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RadarRiskReviewStore } from "../../store/radar/risk-review.store";
import { riskProposal, riskContext, riskQueue } from "../../store/radar/__fixtures__/risk-review";
import { RiskProposalCard } from "./risk-proposal-card";

const store = () =>
  new RadarRiskReviewStore("team", {
    listAgentConfigurations: vi.fn().mockResolvedValue([]),
    listRiskReviews: vi.fn().mockResolvedValue(structuredClone(riskQueue)),
    startRiskReview: vi.fn(),
    prepareRiskReview: vi.fn(),
    resolveRiskProposal: vi.fn(),
  });

describe("human Risk Review card", () => {
  it("renders evidence, confidence and Accept/Edit/Reject from the real observable store", async () => {
    const cache = store();
    await cache.load();
    const html = renderToStaticMarkup(
      createElement(RiskProposalCard, {
        proposal: cache.queue.proposals[0],
        context: cache.queue.runs[0].context,
        store: cache,
      })
    );
    for (const text of [
      "Accept",
      "Edit",
      "Reject",
      "Inference",
      "Confidence 80%",
      "Evidence and context used",
      "Licenciamento pode atrasar",
      "Implantar Governança de IA",
      "Depende da licença",
      "Each suggestion is approved separately",
      "Review feedback / rationale",
    ])
      expect(html).toContain(text);
    expect(html).toContain("disabled");
  });
  it("closed rejection shows feedback and no action buttons", () => {
    const proposal = {
      ...riskProposal,
      status: "rejected" as const,
      approval: { ...riskProposal.approval, rationale: "Wrong dependency" },
    };
    const html = renderToStaticMarkup(
      createElement(RiskProposalCard, { proposal, context: riskContext, store: store() })
    );
    expect(html).toContain("Wrong dependency");
    expect(html).not.toContain(">Accept<");
    expect(html).not.toContain(">Reject<");
  });
  it("edited proposal keeps historical citations and shows refreshed versions", () => {
    const proposal = {
      ...riskProposal,
      previous_id: "original",
      revision: 2,
      reviewed_context: { ...riskContext, objects: riskContext.objects.map((o) => ({ ...o, version: 2 })) },
    };
    const html = renderToStaticMarkup(
      createElement(RiskProposalCard, { proposal, context: riskContext, store: store() })
    );
    expect(html).toContain("Human edited proposal");
    expect(html).toContain("version 2");
    expect(html).toContain("version 1");
  });
  it("reports applied action and links its actual command result", () => {
    const proposal = {
      ...riskProposal,
      component: "action" as const,
      status: "executed" as const,
      result: { ...riskProposal.result, data: { object: { id: "new-action" } } },
    };
    const html = renderToStaticMarkup(
      createElement(RiskProposalCard, { proposal, context: riskContext, store: store() })
    );
    expect(html).toContain("Applied successfully");
    expect(html).toContain("/team/radar/objects/new-action");
  });
});
