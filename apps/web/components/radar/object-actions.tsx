import { useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { setToast } from "@plane/blocks/toast";
import { RadarApprovalPendingError } from "@/services/radar/radar.service";
import type { RadarCommandPreview, RadarObject, RadarObjectCapacities } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import { contractInput } from "./capability-form";
import type { RadarFormDrafts } from "./capability-form";
import { RadarContractField } from "./contract-field";
import { governedActions } from "./governed-actions";
import type { RadarGovernedAction } from "./governed-actions";
import { semanticError, semanticLabel } from "./semantic-utils";

const ActionCard = observer(function ActionCard({
  object,
  action,
  disabled,
}: {
  object: RadarObject;
  action: RadarGovernedAction;
  disabled: boolean;
}) {
  const store = useRadarStore();
  const [drafts, setDrafts] = useState<RadarFormDrafts>({});
  const [preview, setPreview] = useState<{ input: Record<string, unknown>; plan: RadarCommandPreview } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const blocked = disabled || busy || !action.available;
  const review = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const input = contractInput(action.fields, drafts, action.base);
      setPreview({ input, plan: await store.previewCommand(action.capability, input, action.title) });
    } catch (cause) {
      setError(semanticError(cause));
    } finally {
      setBusy(false);
    }
  };
  const confirm = async () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      await store.runCommand(object.id, action.capability, preview.input, preview.plan);
      setPreview(null);
      setDrafts({});
      setToast({ type: "success", title: action.title, message: "Done." });
    } catch (cause) {
      if (cause instanceof RadarApprovalPendingError) {
        setPreview(null);
        setMessage("Sent for human review. Nothing has changed yet.");
      } else setError(semanticError(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="flex flex-col gap-2 rounded-md border border-subtle p-3" data-testid={`radar-action-${action.key}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-13 font-medium">{action.title}</span>
        {action.humanOnly && <span className="text-11 text-tertiary">Human decision</span>}
      </div>
      {action.reason && (
        <p className={`text-11 ${action.metadataProblem ? "text-danger-primary" : "text-tertiary"}`}>{action.reason}</p>
      )}
      {action.available &&
        action.fields.map((field) => (
          <RadarContractField
            key={field.key}
            id={`radar-action-${action.capability}-${field.key}`}
            field={field}
            value={drafts[field.key] ?? (field.kind === "objects" ? [] : "")}
            onChange={(value) => {
              setDrafts((current) => ({ ...current, [field.key]: value }));
              setPreview(null);
            }}
            objects={store.listedObjects}
            exclude={object.id}
            disabled={blocked}
          />
        ))}
      {preview && (
        <div className="rounded-md bg-layer-1 p-2 text-12" data-testid="radar-action-preview" role="status">
          <p>
            Changes: {preview.plan.effect_plan.authority.fields.map(semanticLabel).join(", ") || "no field changes"}.
          </p>
          <p>
            {preview.plan.requires_review
              ? "Requires an independent human review before it takes effect."
              : "Takes effect immediately."}
          </p>
        </div>
      )}
      {message && <p className="text-13 text-secondary">{message}</p>}
      {error && (
        <p role="alert" className="text-13 text-danger-primary">
          {error}
        </p>
      )}
      {action.available && (
        <div className="flex gap-2">
          {preview ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label="Edit"
                disabled={busy}
                onClick={() => setPreview(null)}
              />
              <Button
                variant="primary"
                size="sm"
                stretch="auto"
                label={busy ? "Applying…" : "Confirm"}
                aria-label={`Confirm ${action.title}`}
                disabled={blocked}
                onClick={() => void confirm()}
              />
            </>
          ) : (
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label={busy ? "Reviewing…" : "Review"}
              aria-label={`Review ${action.title}`}
              disabled={blocked}
              onClick={() => void review()}
            />
          )}
        </div>
      )}
    </li>
  );
});

export const RadarObjectActions = observer(function RadarObjectActions({
  object,
  capacities,
  disabled,
}: {
  object: RadarObject;
  capacities: RadarObjectCapacities;
  disabled: boolean;
}) {
  const store = useRadarStore();
  const actions = governedActions(object, capacities, store.capabilities);
  if (!actions.length) return null;
  return (
    <section aria-labelledby="radar-actions-heading">
      <h2 id="radar-actions-heading" className="mb-3 text-16 font-semibold">
        Actions
      </h2>
      <ul className="flex flex-col gap-2">
        {actions.map((action) => (
          <ActionCard key={action.key} object={object} action={action} disabled={disabled} />
        ))}
      </ul>
    </section>
  );
});
