import { useState } from "react";
import { observer } from "mobx-react";
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
import type { CreateRadarRelation, RadarObject } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import { RadarChoiceField } from "./choice-field";
import { RadarSchemaReview, useRadarSchemaReview } from "./schema-review";
import { RadarObjectPicker } from "./object-picker";
import { semanticError, semanticLabel } from "./semantic-utils";
import type { RelationDirection } from "./semantic-utils";

export const RadarRelationDialog = observer(function RadarRelationDialog({
  object,
  onCreate,
  onClose,
}: {
  object: RadarObject;
  onCreate: (payload: CreateRadarRelation) => Promise<void>;
  onClose: () => void;
}) {
  const store = useRadarStore();
  const schemaReview = useRadarSchemaReview();
  const [direction, setDirection] = useState<RelationDirection>("outgoing");
  const [kindId, setKindId] = useState("");
  const [otherId, setOtherId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const kinds = store.relationTypes.filter((kind) => {
    const keys = direction === "outgoing" ? kind.source_types : kind.target_types;
    return kind.is_active && (keys.includes("*") || keys.includes(object.object_type_detail.key));
  });
  const kind = kinds.find((item) => item.id === kindId);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!schemaReview.canWrite || !kind || !otherId || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate({
        relation_type: kind.id,
        source: direction === "outgoing" ? object.id : otherId,
        target: direction === "outgoing" ? otherId : object.id,
      });
      onClose();
    } catch (cause) {
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
                <DialogTitle>Add relation</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <RadarSchemaReview pending={schemaReview.pending} onReview={schemaReview.review} />
              <div className="flex flex-col gap-4">
                <p className="text-13 text-secondary">{object.title}</p>
                <RadarChoiceField
                  id="radar-relation-direction"
                  label="Direction"
                  value={direction}
                  disabled={saving}
                  options={[
                    { value: "outgoing", label: "From this object" },
                    { value: "incoming", label: "To this object (backlink)" },
                  ]}
                  onChange={(value) => {
                    setDirection(value === "incoming" ? "incoming" : "outgoing");
                    setKindId("");
                    setOtherId("");
                  }}
                />
                <RadarChoiceField
                  id="radar-relation-type"
                  label="Relation"
                  value={kind?.id ?? ""}
                  disabled={saving || !kinds.length}
                  options={kinds.map((item) => ({
                    value: item.id,
                    label: semanticLabel(direction === "outgoing" ? item.forward_label : item.reverse_label),
                  }))}
                  onChange={(value) => {
                    setKindId(value);
                    setOtherId("");
                  }}
                />
                {kind && (
                  <RadarObjectPicker
                    key={`${kind.id}:${direction}:${store.schemaRevision}`}
                    id="radar-relation-object"
                    label="Related object"
                    value={otherId}
                    onChange={(value) => setOtherId(Array.isArray(value) ? (value[0] ?? "") : value)}
                    query={{ relation_type: kind.id, object_id: object.id, direction }}
                    disabled={saving}
                  />
                )}
                {!kinds.length && (
                  <p role="status" className="text-13 text-secondary">
                    No available relations in this direction. Create a compatible object or remove an existing relation
                    first.
                  </p>
                )}
                {kind && <p className="text-13 text-secondary">{kind.description}</p>}
                {error && (
                  <p role="alert" className="text-13 text-danger-primary">
                    {error}
                  </p>
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label="Cancel" onClick={onClose} disabled={saving} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              label={saving ? "Adding…" : "Add relation"}
              disabled={saving || !schemaReview.canWrite || !kind || !otherId}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
