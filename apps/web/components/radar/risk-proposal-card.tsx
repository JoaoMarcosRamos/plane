import { useState } from "react";
import { toJS } from "mobx";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import type { RiskProposal, RiskContext, RiskCommandInput } from "@/services/radar/risk-review.types";
import type { RadarRiskReviewStore } from "@/store/radar/risk-review.store";
import { RadarChoiceField } from "./choice-field";
import { semanticLabel } from "./semantic-utils";
import { riskReviewError } from "./risk-review-error";

export function RiskProposalCard({
  proposal,
  context,
  store,
}: {
  proposal: RiskProposal;
  context: RiskContext;
  store: RadarRiskReviewStore;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<RiskCommandInput>(() => structuredClone(toJS(proposal.input)));
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const object = (id?: string) => context.objects.find((item) => item.id === id);
  const name = (id?: string) => object(id)?.title || object(id)?.type || "Object";
  const url = (id: string) => `/${encodeURIComponent(store.workspaceSlug)}/radar/objects/${encodeURIComponent(id)}`;
  const decide = async (decision: "accept" | "edit" | "reject") => {
    if (busy || !rationale.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await store.resolve(proposal, { decision, rationale, ...(decision === "edit" ? { edited_input: draft } : {}) });
    } catch (cause) {
      setError(riskReviewError(cause));
    } finally {
      setBusy(false);
    }
  };
  const createdObject = proposal.result.data.object;
  const createdObjectId =
    createdObject && typeof createdObject === "object" && "id" in createdObject && typeof createdObject.id === "string"
      ? createdObject.id
      : null;
  const pending = proposal.status === "pending_approval";
  return (
    <article
      id={`risk-proposal-${proposal.id}`}
      className="flex flex-col gap-3 rounded-lg border border-subtle p-4"
      aria-label={`Review ${proposal.component}`}
    >
      <div className="flex justify-between">
        <h3 className="font-semibold">
          {proposal.component === "relation" ? "Suggested relation" : "Suggested action"}
        </h3>
        <span>
          {proposal.status === "pending_approval"
            ? "Awaiting review"
            : proposal.status === "rejected"
              ? "Rejected / replaced"
              : "Applied"}{" "}
          · revision {proposal.revision}
        </span>
      </div>
      <p>{proposal.suggestion.explanation}</p>
      <p className="text-13 text-secondary">
        {proposal.previous_id ? "Original inference" : "Inference"} · Confidence{" "}
        {Math.round(proposal.suggestion.confidence * 100)}%
      </p>
      {proposal.component === "relation" ? (
        <p>
          <a href={url(proposal.input.source_id!)} className="underline">
            {name(proposal.input.source_id)}
          </a>{" "}
          → threatens →{" "}
          <a href={url(proposal.input.target_id!)} className="underline">
            {name(proposal.input.target_id)}
          </a>
        </p>
      ) : (
        <div>
          <strong>{proposal.input.title}</strong>
          <p>{proposal.input.description}</p>
          <p>Next step: {proposal.input.next_step}</p>
          <p>Mitigates: {name(proposal.input.mitigates_risk_ids?.[0])}</p>
        </div>
      )}
      <details>
        <summary>Evidence and context used</summary>
        <ul className="flex flex-col gap-2 pt-2">
          {proposal.suggestion.evidence.map((evidence) => (
            <li key={`${evidence.object_id}:${evidence.field}:${evidence.quote}`}>
              <a href={url(evidence.object_id)} className="underline">
                {name(evidence.object_id)}
              </a>{" "}
              · version {evidence.version} · {evidence.field}
              <blockquote className="border-l-2 pl-3">{evidence.quote}</blockquote>
            </li>
          ))}
        </ul>
        {proposal.suggestion.context_used.map((id) => {
          const edge = context.relations.find((item) => item.id === id);
          return (
            edge && (
              <p key={id}>
                {name(edge.source)} → {edge.type} → {name(edge.target)}
              </p>
            )
          );
        })}
        <p className="mt-2 text-13 text-secondary">
          {context.truncated
            ? "The supplied context was truncated; this review may be incomplete."
            : "This review uses only the supplied context."}
        </p>
      </details>
      {proposal.previous_id && (
        <details>
          <summary>Human edited proposal · refreshed context</summary>
          {proposal.reviewed_context.objects.map((obj) => (
            <div key={obj.id} className="mt-2">
              <strong>
                {obj.title || obj.type} · version {obj.version}
              </strong>
              <p>{obj.content}</p>
              <dl className="grid grid-cols-[120px_1fr] gap-2 text-13">
                {Object.entries(obj.properties).map(([key, value]) => (
                  <div key={key} className="contents">
                    <dt>{semanticLabel(key)}</dt>
                    <dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </details>
      )}
      {pending && (
        <>
          <p className="text-13 text-secondary">
            Preview:{" "}
            {proposal.component === "relation" ? "link the two Objects" : "create an Action and link its mitigation"}.
            Each suggestion is approved separately. Editing saves a new preview for approval.
          </p>
          {editing && (
            <div className="flex flex-col gap-3 rounded border border-subtle p-3">
              {proposal.component === "relation" ? (
                <RadarChoiceField
                  id={`target-${proposal.id}`}
                  label="Threatened Objective / Project"
                  value={draft.target_id ?? ""}
                  options={context.objects
                    .filter((o) => ["objective", "project"].includes(o.type))
                    .map((o) => ({ value: o.id, label: o.title || o.type }))}
                  onChange={(target_id) => setDraft({ ...draft, target_id })}
                  disabled={busy}
                />
              ) : (
                <>
                  <InputField
                    size="md"
                    orientation="vertical"
                    label="Action title"
                    value={draft.title ?? ""}
                    onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                    disabled={busy}
                  />
                  <TextAreaField
                    size="lg"
                    label="Description"
                    value={draft.description ?? ""}
                    onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                    disabled={busy}
                  />
                  <InputField
                    size="md"
                    orientation="vertical"
                    label="Next step"
                    value={draft.next_step ?? ""}
                    onChange={(event) => setDraft({ ...draft, next_step: event.target.value })}
                    disabled={busy}
                  />
                </>
              )}
            </div>
          )}
          <TextAreaField
            size="lg"
            label="Review feedback / rationale"
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            disabled={busy}
            placeholder="Record why you accept, edit or reject this suggestion."
          />
          <div className="flex gap-2">
            {editing ? (
              <>
                <Button
                  size="sm"
                  stretch="auto"
                  variant="primary"
                  label="Save edited proposal"
                  onClick={() => void decide("edit")}
                  disabled={busy || !rationale.trim()}
                />
                <Button
                  size="sm"
                  stretch="auto"
                  label="Cancel edit"
                  variant="secondary"
                  onClick={() => setEditing(false)}
                  disabled={busy}
                />
              </>
            ) : (
              <>
                <Button
                  size="sm"
                  stretch="auto"
                  variant="primary"
                  label="Accept"
                  onClick={() => void decide("accept")}
                  disabled={busy || !rationale.trim()}
                />
                <Button
                  size="sm"
                  stretch="auto"
                  label="Edit"
                  variant="secondary"
                  onClick={() => setEditing(true)}
                  disabled={busy}
                />
                <Button
                  size="sm"
                  stretch="auto"
                  label="Reject"
                  variant="secondary"
                  onClick={() => void decide("reject")}
                  disabled={busy || !rationale.trim()}
                />
              </>
            )}
          </div>
        </>
      )}
      {!pending && <p className="text-13 text-secondary">Review feedback: {proposal.approval.rationale}</p>}
      {proposal.status === "executed" && (
        <p role="status">
          Applied successfully.{" "}
          {proposal.component === "action" && createdObjectId && (
            <a className="underline" href={url(createdObjectId!)}>
              Open Action
            </a>
          )}
        </p>
      )}
      {error && (
        <p role="alert" className="text-danger-primary">
          {error}
        </p>
      )}
    </article>
  );
}
