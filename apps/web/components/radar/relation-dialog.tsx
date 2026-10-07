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
import type { CreateRadarRelation, RadarObject, RadarRelation } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import { RadarChoiceField } from "./choice-field";
import { RadarSchemaReview, useRadarSchemaReview } from "./schema-review";
import { relationCandidates, semanticError, semanticLabel } from "./semantic-utils";
import type { RelationDirection } from "./semantic-utils";

export const RadarRelationDialog = observer(function RadarRelationDialog({
  object,
  relations,
  onCreate,
  onClose,
}: {
  object: RadarObject;
  relations: RadarRelation[];
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
  const kinds = store.relationTypes.filter(
    (kind) => relationCandidates(kind, object, store.listedObjects, direction, relations).length > 0
  );
  const kind = kinds.find((item) => item.id === kindId);
  const candidates = kind ? relationCandidates(kind, object, store.listedObjects, direction, relations) : [];
  const other = candidates.find((item) => item.id === otherId);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!schemaReview.canWrite || !kind || !other || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate({
        relation_type: kind.id,
        source: direction === "outgoing" ? object.id : other.id,
        target: direction === "outgoing" ? other.id : object.id,
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
                <RadarChoiceField
                  id="radar-relation-object"
                  label="Related object"
                  value={other?.id ?? ""}
                  disabled={saving || !kind}
                  options={candidates.map((item) => ({
                    value: item.id,
                    label: `${item.object_type_detail.name} · ${item.title}`,
                  }))}
                  onChange={setOtherId}
                />
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
              disabled={saving || !schemaReview.canWrite || !kind || !other}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
