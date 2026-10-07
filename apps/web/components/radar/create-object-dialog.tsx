import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useRouter } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import type { RadarObjectType } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import type { RadarFormDrafts } from "./capability-form";
import { RadarContractField } from "./contract-field";
import { creationForm, creationPayload, initialDrafts } from "./create-object-input";
import { RadarPropertyInput } from "./property-input";
import { RadarSchemaReview, useRadarSchemaReview } from "./schema-review";
import { semanticError, semanticLabel } from "./semantic-utils";

/** Creation composed from the selected type's definitions and declared creation capability (C03). */
export const RadarCreateObjectDialog = observer(function RadarCreateObjectDialog({ onClose }: { onClose: () => void }) {
  const store = useRadarStore();
  const router = useRouter();
  const schemaReview = useRadarSchemaReview();
  const [title, setTitle] = useState("");
  const [typeId, setTypeId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [parameters, setParameters] = useState<RadarFormDrafts>({});
  const [showOptional, setShowOptional] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedType = store.objectTypes.find((type) => type.id === typeId) ?? null;
  // Recomputed from the current catalog: a schema change re-renders the fields and requires review.
  const form = useMemo(
    () =>
      selectedType
        ? creationForm(selectedType, store.propertyDefinitions, store.relationTypes, store.capabilities)
        : null,
    [selectedType, store.propertyDefinitions, store.relationTypes, store.capabilities]
  );
  const values = form ? { ...initialDrafts(form), ...drafts } : {};
  const ready =
    schemaReview.canWrite &&
    !!form?.available &&
    !!title.trim() &&
    form.required.every((item) => !!values[item.key]?.trim()) &&
    form.parameters.every(
      (field) =>
        !field.required || (Array.isArray(parameters[field.key]) ? parameters[field.key].length : parameters[field.key])
    );
  const selectType = (id: string | null) => {
    setTypeId(id ?? "");
    setDrafts({});
    setParameters({});
    setShowOptional(false);
    setError(null);
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving || !form || !ready) return;
    setSaving(true);
    setError(null);
    try {
      const payload = creationPayload(form, values, parameters);
      const object = await store.createObject({
        object_type: form.type.id,
        title: title.trim(),
        properties: payload.properties,
        ...(Object.keys(payload.parameters).length ? { parameters: payload.parameters } : {}),
      });
      onClose();
      router.push(`/${store.workspaceSlug}/radar/objects/${object.id}/`);
      setToast({ type: "success", title: "Object created", message: object.title });
    } catch (cause) {
      console.error("RADAR create failed", cause);
      setError(semanticError(cause));
      setSaving(false);
    }
  };
  const propertyField = (key: string) => {
    const definition = form?.required.concat(form.optional).find((item) => item.key === key);
    if (!definition) return null;
    const required = form?.required.includes(definition);
    return (
      <RadarPropertyInput
        key={definition.key}
        definition={definition}
        id={`radar-create-${definition.key}`}
        label={required ? semanticLabel(definition.name) : `${semanticLabel(definition.name)} (optional)`}
        value={values[definition.key] ?? ""}
        onChange={(value) => setDrafts((current) => ({ ...current, [definition.key]: value }))}
        disabled={saving}
      />
    );
  };
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>Create object</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-4">
                <RadarSchemaReview pending={schemaReview.pending} onReview={schemaReview.review} />
                <div>
                  <span className="text-13 font-medium">Type</span>
                  <Select<RadarObjectType>
                    getValues={() => store.objectTypes}
                    value={selectedType}
                    onChange={selectType}
                    getOptionValue={(type) => type.id}
                    getOptionLabel={(type) => type.name}
                    showSearch={false}
                    pinSelected={false}
                  >
                    <Select.Trigger variant="select-md">
                      <span data-testid="radar-create-type">{selectedType?.name ?? "Select a type"}</span>
                    </Select.Trigger>
                  </Select>
                </div>
                <InputField
                  id="radar-object-title"
                  label="Title"
                  orientation="vertical"
                  size="xl"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  maxLength={255}
                  required
                  disabled={saving}
                />
                {form && !form.available && (
                  <p role="alert" className="text-13 text-danger-primary">
                    This type&apos;s creation capability is unavailable. Ask a workspace admin to review it.
                  </p>
                )}
                {form?.initialState && (
                  <p className="text-12 text-tertiary" data-testid="radar-create-initial-state">
                    Starts as {semanticLabel(form.initialState.value)}. Later changes follow the type&apos;s lifecycle.
                  </p>
                )}
                {form?.required.map((item) => propertyField(item.key))}
                {form?.parameters.map((field) => (
                  <RadarContractField
                    key={field.key}
                    id={`radar-create-parameter-${field.key}`}
                    field={field}
                    value={parameters[field.key] ?? (field.kind === "objects" ? [] : "")}
                    onChange={(value) => setParameters((current) => ({ ...current, [field.key]: value }))}
                    disabled={saving}
                  />
                ))}
                {form && form.optional.length > 0 && (
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label={showOptional ? "Hide optional fields" : `Optional fields (${form.optional.length})`}
                    onClick={() => setShowOptional((value) => !value)}
                    disabled={saving}
                  />
                )}
                {showOptional && form?.optional.map((item) => propertyField(item.key))}
                {form && form.mandatoryRelations.length > 0 && (
                  <p className="text-12 text-tertiary" data-testid="radar-create-required-relations">
                    Link a required{" "}
                    {form.mandatoryRelations.map((kind) => semanticLabel(kind.forward_label)).join(", ")} relation
                    before changing its status or binding it to the runtime.
                  </p>
                )}
                {error && (
                  <p role="alert" className="text-13 text-danger-primary">
                    {error}
                  </p>
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button stretch="auto" variant="secondary" size="md" label="Cancel" onClick={onClose} disabled={saving} />
            <Button
              stretch="auto"
              variant="primary"
              size="md"
              type="submit"
              label={saving ? "Creating…" : "Create"}
              disabled={saving || !ready}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
