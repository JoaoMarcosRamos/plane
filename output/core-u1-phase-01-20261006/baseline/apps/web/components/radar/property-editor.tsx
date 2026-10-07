import { useEffect, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { MemberSelect } from "@/components/dropdowns/member/member-select";
import type { RadarObjectProperty, RadarPropertyData } from "@/services/radar/types";
import { RadarChoiceField } from "./choice-field";
import { propertyDraft, parsePropertyDraft, semanticError, semanticLabel } from "./semantic-utils";

export function RadarPropertyEditor({
  row,
  canWrite,
  busy,
  onSave,
  onRemove,
}: {
  row: RadarObjectProperty;
  canWrite: boolean;
  busy: boolean;
  onSave: (definition: string, value: RadarPropertyData) => Promise<void>;
  onRemove: (definition: string) => Promise<void>;
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
  const disabled = busy || saving || !canWrite;
  const updateDraft = (value: string) => {
    setDraft(value);
    setError(null);
  };
  const label = semanticLabel(definition.name);
  const id = `radar-property-${definition.key}`;
  const removable = !definition.is_required && definition.config.default === undefined && !!row.stored_value;
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
  let input;
  if (definition.value_type === "enum" || definition.value_type === "boolean") {
    const options =
      definition.value_type === "boolean"
        ? [
            { value: "true", label: "Yes" },
            { value: "false", label: "No" },
          ]
        : (definition.config.choices ?? []).map((value) => ({ value, label: semanticLabel(value) }));
    input = (
      <RadarChoiceField
        id={id}
        label={label}
        value={draft}
        options={options}
        onChange={updateDraft}
        disabled={disabled}
      />
    );
  } else if (definition.value_type === "user") {
    input = (
      <div className="flex flex-col gap-1.5">
        <span className="text-13 font-medium">{label}</span>
        <MemberSelect
          testId={id}
          variant="select-md"
          value={draft || null}
          onChange={updateDraft}
          disabled={disabled}
          clearable={false}
          placeholder="Select member"
        />
      </div>
    );
  } else if (definition.value_type === "string_list" || definition.value_type === "string") {
    input = (
      <TextAreaField
        id={id}
        label={label}
        value={draft}
        onChange={(event) => updateDraft(event.target.value)}
        disabled={disabled}
        size="lg"
        rows={definition.value_type === "string_list" ? 2 : 3}
        hint={definition.value_type === "string_list" ? "One item per line." : undefined}
      />
    );
  } else {
    const type = {
      number: "number",
      integer: "number",
      date: "date",
      datetime: "datetime-local",
      email: "email",
      uri: "url",
    }[definition.value_type];
    input = (
      <InputField
        id={id}
        label={label}
        size="lg"
        orientation="vertical"
        type={type}
        value={draft}
        onChange={(event) => updateDraft(event.target.value)}
        disabled={disabled}
        min={definition.config.min}
        max={definition.config.max}
        step={definition.value_type === "integer" ? 1 : "any"}
      />
    );
  }
  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-col gap-2 rounded-md border border-subtle p-3"
      data-testid={`property-${definition.key}`}
    >
      {input}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-11 text-tertiary">
          {!row.has_value ? "Not set" : !row.stored_value ? "Default" : "Saved"}
        </span>
        {canWrite && (
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
