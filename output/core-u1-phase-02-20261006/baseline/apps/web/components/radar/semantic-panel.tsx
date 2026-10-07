import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
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
import { setToast } from "@plane/blocks/toast";
import type { CreateRadarRelation, RadarObject, RadarPropertyData, RadarRelation } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import { RadarPropertyEditor } from "./property-editor";
import { RadarRelationDialog } from "./relation-dialog";
import { semanticError, semanticLabel } from "./semantic-utils";

export const RadarSemanticPanel = observer(function RadarSemanticPanel({
  object,
  canWrite,
}: {
  object: RadarObject;
  canWrite: boolean;
}) {
  const store = useRadarStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<RadarRelation | null>(null);
  const properties = store.propertySnapshots.get(object.id)?.properties;
  const relations = store.relationSnapshots.get(object.id)?.relations;
  const stale = !store.propertiesFor(object.id) || !store.relationsFor(object.id);
  // Title/content writes and semantic writes share Object.version. Refresh invalidated snapshots.
  useEffect(() => {
    if (!stale || busy) return;
    let active = true;
    store.loadObjectSemantics(object.id).catch((cause: unknown) => {
      if (active) setError(semanticError(cause));
    });
    return () => {
      active = false;
    };
  }, [store, object.id, object.version, stale, busy]);
  const mutate = async (operation: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError(null);
    try {
      await operation();
      setToast({ type: "success", title: message });
      try {
        await store.loadObjectSemantics(object.id);
      } catch (cause) {
        setError(`Saved. Could not refresh: ${semanticError(cause)}`);
      }
    } finally {
      setBusy(false);
    }
  };
  const setProperty = (definition: string, value: RadarPropertyData) =>
    mutate(() => store.setProperty(object.id, definition, value), "Property saved");
  const removeProperty = (definition: string) =>
    mutate(() => store.removeProperty(object.id, definition), "Property cleared");
  const createRelation = (payload: CreateRadarRelation) =>
    mutate(() => store.createRelation(payload), "Relation added");
  const removeRelation = async () => {
    if (!removing) return;
    try {
      await mutate(() => store.removeRelation(removing.id), "Relation removed");
      setRemoving(null);
    } catch (cause) {
      setError(semanticError(cause));
    }
  };
  const renderRelation = (edge: RadarRelation, incoming: boolean) => {
    const otherId = incoming ? edge.source : edge.target;
    const other = store.objects.get(otherId);
    return (
      <li key={edge.id} className="flex flex-wrap items-center gap-2 rounded-md border border-subtle px-3 py-2 text-13">
        <span aria-hidden>{incoming ? "←" : "→"}</span>
        <span className="font-medium text-secondary">
          {semanticLabel(incoming ? edge.relation_type_detail.reverse_label : edge.relation_type_detail.forward_label)}
        </span>
        <Link
          href={`/${store.workspaceSlug}/radar/objects/${otherId}/`}
          className="min-w-0 flex-1 break-words text-accent-primary underline"
        >
          {other?.title ?? "Open related object"}
        </Link>
        {other && <span className="text-11 text-tertiary">{other.object_type_detail.name}</span>}
        {canWrite && (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Remove"
            aria-label={`Remove ${semanticLabel(edge.relation_type_detail.forward_label)} relation with ${other?.title ?? "object"}`}
            disabled={busy || stale}
            onClick={() => {
              setError(null);
              setRemoving(edge);
            }}
          />
        )}
      </li>
    );
  };
  return (
    <div className="mt-8 flex flex-col gap-6" aria-busy={busy || stale}>
      {!canWrite && <p className="text-13 text-secondary">Read-only workspace access.</p>}
      {error && (
        <div role="alert" className="text-13 text-danger-primary">
          {error}{" "}
          <button
            className="underline"
            disabled={busy}
            onClick={() => {
              setError(null);
              void store.loadObjectSemantics(object.id).catch((cause: unknown) => setError(semanticError(cause)));
            }}
          >
            Retry
          </button>
        </div>
      )}
      <section aria-labelledby="radar-properties-heading">
        <h2 id="radar-properties-heading" className="mb-3 text-16 font-semibold">
          Properties
        </h2>
        {!properties ? (
          <p role="status">Loading properties…</p>
        ) : properties.length === 0 ? (
          <p className="text-13 text-secondary">No properties configured for this type.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {properties.map((row) => (
              <RadarPropertyEditor
                key={row.definition.id}
                row={row}
                canWrite={canWrite}
                busy={busy || stale}
                onSave={setProperty}
                onRemove={removeProperty}
              />
            ))}
          </div>
        )}
      </section>
      <section aria-labelledby="radar-relations-heading">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id="radar-relations-heading" className="text-16 font-semibold">
            Relations
          </h2>
          {canWrite && (
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label="Add relation"
              disabled={busy || stale || !relations}
              onClick={() => setAdding(true)}
            />
          )}
        </div>
        {!relations ? (
          <p role="status">Loading relations…</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {relations.filter((edge) => edge.source === object.id).map((edge) => renderRelation(edge, false))}
          </ul>
        )}
        {relations && !relations.some((edge) => edge.source === object.id) && (
          <p className="text-13 text-secondary">No outgoing relations.</p>
        )}
      </section>
      <section aria-labelledby="radar-backlinks-heading">
        <h2 id="radar-backlinks-heading" className="mb-3 text-16 font-semibold">
          Backlinks
        </h2>
        {relations ? (
          <ul className="flex flex-col gap-2">
            {relations.filter((edge) => edge.target === object.id).map((edge) => renderRelation(edge, true))}
          </ul>
        ) : (
          <p role="status">Loading backlinks…</p>
        )}
        {relations && !relations.some((edge) => edge.target === object.id) && (
          <p className="text-13 text-secondary">No incoming relations.</p>
        )}
      </section>
      {adding && relations && (
        <RadarRelationDialog
          object={object}
          relations={relations}
          onCreate={createRelation}
          onClose={() => setAdding(false)}
        />
      )}
      {removing && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open && !busy) setRemoving(null);
          }}
        >
          <DialogContent size="md">
            <DialogMain>
              <DialogHeader>
                <DialogHeading>
                  <DialogTitle>Remove relation?</DialogTitle>
                </DialogHeading>
              </DialogHeader>
              <DialogBody>
                <p className="text-13">Remove this connection? Both objects will remain available.</p>
                {error && <p role="alert">{error}</p>}
              </DialogBody>
            </DialogMain>
            <DialogActions>
              <Button
                variant="secondary"
                size="md"
                stretch="auto"
                label="Cancel"
                disabled={busy}
                onClick={() => setRemoving(null)}
              />
              <Button
                variant="primary"
                size="md"
                stretch="auto"
                label={busy ? "Removing…" : "Remove relation"}
                disabled={busy}
                onClick={() => void removeRelation()}
              />
            </DialogActions>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
});
