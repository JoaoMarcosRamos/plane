import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useSearchParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { CheckboxField } from "@makeplane/propel/components/checkbox-field";
import { RadarService } from "@/services/radar/radar.service";
import { RadarRiskReviewStore } from "@/store/radar/risk-review.store";
import { useRadarStore } from "@/store/radar/provider";
import { RadarChoiceField } from "./choice-field";
import { RiskProposalCard } from "./risk-proposal-card";
import { riskReviewError } from "./risk-review-error";

export const RadarRiskReview = observer(function RadarRiskReview() {
  const searchParams = useSearchParams();
  const proposalId = searchParams.get("proposal") ?? undefined;
  const { workspaceSlug } = useRadarStore();
  const [store] = useState(() => new RadarRiskReviewStore(workspaceSlug, new RadarService()));
  const [bindingId, setBindingId] = useState("");
  const [roots, setRoots] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      await store.load(proposalId);
      setLoaded(true);
    } catch (cause) {
      setError(riskReviewError(cause));
    }
  }, [store, proposalId]);
  useEffect(() => {
    if (loaded && proposalId)
      document.getElementById(`risk-proposal-${proposalId}`)?.scrollIntoView({ block: "center" });
  }, [loaded, proposalId]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!store.activeRunId) return;
    const runId = store.activeRunId;
    let stopped = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await store.check(runId);
        if (!stopped && ["queued", "running"].includes(result.status) && ++attempts < 60)
          timer = setTimeout(() => void poll(), 2000);
      } catch (cause) {
        if (!stopped) setError(riskReviewError(cause));
      }
    };
    timer = setTimeout(() => void poll(), 500);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [store, store.activeRunId]);
  const entry = store.entries.find((item) => item.binding_id === bindingId);
  const permitted =
    entry?.effective_permissions.commands.includes("LinkObjects") &&
    entry.effective_permissions.commands.includes("CreateAction");
  const start = async () => {
    if (busy || !bindingId || !roots.length) return;
    setBusy(true);
    setError(null);
    try {
      await store.start(bindingId, roots);
    } catch (cause) {
      setError(riskReviewError(cause));
    } finally {
      setBusy(false);
    }
  };
  const check = async (runId: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await store.check(runId);
      if (["queued", "running"].includes(result.status)) store.activeRunId = runId;
    } catch (cause) {
      setError(riskReviewError(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 p-6">
      <header>
        <h1 className="text-20 font-semibold">Risk Review</h1>
        <p className="text-13 text-secondary">
          Review possible threats to Objectives and Projects. Suggestions require your approval.
        </p>
      </header>
      {error && (
        <div>
          <p role="alert" className="text-danger-primary">
            {error}
          </p>
          <Button size="sm" stretch="auto" label="Reload reviews" variant="secondary" onClick={() => void load()} />
        </div>
      )}
      {!loaded && !error && <p role="status">Loading reviews…</p>}
      {loaded && !store.entries.length && (
        <p>No agent is linked to your account. A workspace administrator can provision one.</p>
      )}
      {store.entries.length > 0 && (
        <div className="flex flex-col gap-3 rounded-lg border border-subtle p-4">
          <RadarChoiceField
            id="risk-review-agent"
            label="Agent"
            value={bindingId}
            options={store.entries.map((item) => ({ value: item.binding_id, label: item.configuration.identity.name }))}
            onChange={(value) => {
              setBindingId(value);
              setRoots([]);
            }}
            disabled={busy}
          />
          {entry && (
            <>
              <p className="text-13">Select up to 10 context Objects, including a Risk and an Objective or Project.</p>
              <div className="grid max-h-64 gap-2 overflow-auto">
                {entry.object_options.map((item) => (
                  <CheckboxField
                    size="lg"
                    key={item.id}
                    label={`${item.title || item.type} (${item.type})`}
                    checked={roots.includes(item.id)}
                    onCheckedChange={(checked) =>
                      setRoots((current) => (checked ? [...current, item.id] : current.filter((id) => id !== item.id)))
                    }
                    disabled={busy || (!roots.includes(item.id) && roots.length >= 10)}
                  />
                ))}
              </div>
              {entry.objects_truncated && (
                <p>The Object selection list is limited. Refine the agent scope to find other Objects.</p>
              )}
              {!permitted && (
                <p>
                  This agent needs permission to suggest relations and Actions. Update its administrative grant and
                  configuration.
                </p>
              )}
            </>
          )}
          <Button
            size="sm"
            stretch="auto"
            variant="primary"
            label={busy ? "Starting review…" : "Run Risk Review"}
            onClick={() => void start()}
            disabled={busy || !roots.length || !permitted}
          />
        </div>
      )}
      {store.queue.runs.map((run) => (
        <section key={run.run_id} className="flex flex-col gap-3" aria-label="Risk Review run">
          <h2 className="font-semibold">Review · {new Date(run.created_at).toLocaleString()}</h2>
          {run.result ? (
            <>
              <p>{run.result.summary}</p>
              {run.result.suggestions.length === 0 && (
                <p>No supported threats were identified in the supplied context.</p>
              )}
              {run.context.truncated && (
                <p className="text-13 text-secondary">Context was truncated. Some threats may be missing.</p>
              )}
              {store.queue.proposals
                .filter((p) => p.run_id === run.run_id)
                .map((proposal) => (
                  <RiskProposalCard key={proposal.id} proposal={proposal} context={run.context} store={store} />
                ))}
            </>
          ) : (
            <>
              <p role="status">{store.statuses[run.run_id] ?? "Result not loaded"}</p>
              <Button
                size="sm"
                stretch="auto"
                label="Check review"
                variant="secondary"
                disabled={busy}
                onClick={() => void check(run.run_id)}
              />
              {["failed", "unknown", "cancelled"].includes(store.statuses[run.run_id]) && (
                <p>Review did not complete. Start a new review with current context.</p>
              )}
            </>
          )}
        </section>
      ))}
      {loaded && store.queue.runs.length === 0 && (
        <p>{proposalId ? "This suggestion is no longer available under your permissions." : "No Risk Reviews yet."}</p>
      )}
    </div>
  );
});
