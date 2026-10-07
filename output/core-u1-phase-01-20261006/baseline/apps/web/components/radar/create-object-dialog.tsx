import { useState } from "react";
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
import { creationFields, creationProperties } from "./create-object-input";
import { semanticError, semanticLabel } from "./semantic-utils";

export const RadarCreateObjectDialog = observer(function RadarCreateObjectDialog({ onClose }: { onClose: () => void }) {
  const store = useRadarStore();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [properties, setProperties] = useState<Record<string, string>>({});
  const [typeId, setTypeId] = useState(store.objectTypes.find((type) => type.key === "objective")?.id ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedType = store.objectTypes.find((type) => type.id === typeId) ?? null;
  const fields = creationFields(selectedType?.key ?? "");
  const ready = !!selectedType && !!title.trim() && fields.every((key) => !!properties[key]?.trim());
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving || !selectedType || !ready) return;
    setSaving(true);
    setError(null);
    try {
      const object = await store.createObject({
        object_type: selectedType.id,
        title: title.trim(),
        properties: creationProperties(selectedType.key, properties),
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
                <div>
                  <span className="text-13 font-medium">Type</span>
                  <Select<RadarObjectType>
                    getValues={() => store.objectTypes}
                    value={selectedType}
                    onChange={(id) => setTypeId(id ?? "")}
                    getOptionValue={(type) => type.id}
                    getOptionLabel={(type) => type.name}
                    showSearch={false}
                    pinSelected={false}
                  >
                    <Select.Trigger variant="select-md">
                      <span>{selectedType?.name ?? "Select a type"}</span>
                    </Select.Trigger>
                  </Select>
                </div>
                {fields.map((key) => (
                  <InputField
                    key={key}
                    id={`radar-create-${key}`}
                    label={semanticLabel(key)}
                    orientation="vertical"
                    size="xl"
                    value={properties[key] ?? ""}
                    onChange={(event) => setProperties((draft) => ({ ...draft, [key]: event.target.value }))}
                    required
                    disabled={saving}
                  />
                ))}
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
