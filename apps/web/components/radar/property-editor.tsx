import { useEffect, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import type { RadarFieldCapacity, RadarObjectProperty, RadarPropertyData } from "@/services/radar/types";
import { capacityReason, isMetadataProblem } from "./capacity-text";
import { RadarPropertyInput } from "./property-input";
import { propertyDraft, parsePropertyDraft, semanticError, semanticLabel } from "./semantic-utils";

export function RadarPropertyEditor({
  row,
  canWrite,
  busy,
  onSave,
  onRemove,
  capacity,
  wide = false,
}: {
  row: RadarObjectProperty;
  canWrite: boolean;
  busy: boolean;
  onSave: (definition: string, value: RadarPropertyData) => Promise<void>;
  onRemove: (definition: string) => Promise<void>;
  /** Server-computed capacity for this actor; without it the editor stays read-only. */
  capacity?: RadarFieldCapacity;
  wide?: boolean;
}) {
  const definition = row.definition;
  const savedDraft = propertyDraft(definition, row.value);
  const [draft, setDraft] = useState(savedDraft);
  const [baseline, setBaseline] = useState(savedDraft);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Refresh pristine inputs; keep another field's unsaved draft through a semantic mutation.
  useEffect(() => {
    setDraft((current) => (current === baseline ? savedDraft : current));
    setBaseline(savedDraft);
  }, [savedDraft, baseline]);
  const editable = canWrite && !!capacity?.editable;
  const disabled = busy || saving || !editable;
  const reason = capacity ? capacityReason(capacity.reason, capacity.governed_by) : "Loading your capacities…";
  const updateDraft = (value: string) => {
    setDraft(value);
    setError(null);
  };
  const label = semanticLabel(definition.name);
  const id = `radar-property-${definition.key}`;
  const removable = editable && !!capacity?.removable;
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (disabled) return;
    setError(null);
    setSaving(true);
    try {
      const value = parsePropertyDraft(definition, draft);
      await onSave(definition.id, value);
      setDraft(propertyDraft(definition, value));
      setBaseline(propertyDraft(definition, value));
    } catch (cause) {
      setError(semanticError(cause));
    } finally {
      setSaving(false);
    }
  };
  const remove = async () => {
    if (disabled) return;
    setSaving(true);
    setError(null);
    try {
      await onRemove(definition.id);
      setDraft("");
      setBaseline("");
    } catch (cause) {
      setError(semanticError(cause));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form
      onSubmit={submit}
      noValidate
      className={`flex flex-col gap-2 rounded-md border border-subtle p-3 ${wide ? "sm:col-span-2" : ""}`}
      data-testid={`property-${definition.key}`}
      data-editable={editable}
    >
      <RadarPropertyInput
        definition={definition}
        id={id}
        label={label}
        value={draft}
        onChange={updateDraft}
        disabled={disabled}
        options={capacity?.options}
        rows={wide ? 5 : undefined}
      />
      {canWrite && !editable && reason && (
        <p
          className={`text-11 ${capacity && isMetadataProblem(capacity.reason) ? "text-danger-primary" : "text-tertiary"}`}
          data-testid={`property-${definition.key}-reason`}
        >
          {reason}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-11 text-tertiary">
          {!row.has_value ? "Not set" : !row.stored_value ? "Default" : "Saved"}
        </span>
        {editable && (
          <div className="flex gap-2">
            {removable && (
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label="Clear"
                aria-label={`Clear ${label}`}
                disabled={disabled}
                onClick={() => void remove()}
              />
            )}
            <Button
              type="submit"
              variant="primary"
              size="sm"
              stretch="auto"
              label={saving ? "Saving…" : "Save"}
              aria-label={`Save ${label}`}
              disabled={disabled || (draft === savedDraft && row.has_value)}
            />
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="text-13 text-danger-primary">
          {error}
        </p>
      )}
    </form>
  );
}
