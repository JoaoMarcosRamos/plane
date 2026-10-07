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
import { capacityReason } from "./capacity-text";
import { RadarObjectActions } from "./object-actions";
import { RadarPropertyEditor } from "./property-editor";
import { propertySections } from "./property-sections";
import { RadarRelationDialog } from "./relation-dialog";
import { semanticError, semanticLabel } from "./semantic-utils";

/** Saves one property through its command and refreshes the shared semantic snapshots. */
function useSemanticMutation(object: RadarObject, canWrite: boolean) {
  const store = useRadarStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stale = !store.propertiesFor(object.id) || !store.relationsFor(object.id) || !store.capacitiesFor(object.id);
  const mutate = async (operation: () => Promise<unknown>, message: string) => {
    if (!canWrite || stale) throw new Error("Refresh and review the current workspace definitions before saving.");
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
  return { store, busy, error, setError, stale, mutate };
}

/** The type's principal narrative when it is a property (C21); content is then labelled as notes. */
export const RadarNarrativeProperty = observer(function RadarNarrativeProperty({
  object,
  canWrite,
}: {
  object: RadarObject;
  canWrite: boolean;
}) {
  const { store, busy, error, stale, mutate } = useSemanticMutation(object, canWrite);
  const capacities = store.capacitiesFor(object.id);
  const field = capacities?.presentation.narrative.field;
  const row = store.propertiesFor(object.id)?.find((item) => item.definition.key === field);
  if (!capacities || !row) return null;
  return (
    <div data-testid="radar-narrative-property">
      <RadarPropertyEditor
        row={row}
        canWrite={canWrite}
        busy={busy || stale}
        capacity={capacities.fields[row.definition.key]}
        wide
        onSave={(definition, value) =>
          mutate(() => store.setProperty(object.id, definition, value), `${semanticLabel(row.definition.name)} saved`)
        }
        onRemove={(definition) =>
          mutate(() => store.removeProperty(object.id, definition), `${semanticLabel(row.definition.name)} cleared`)
        }
      />
      {error && (
        <p role="alert" className="text-13 text-danger-primary">
          {error}
        </p>
      )}
    </div>
  );
});

export const RadarSemanticPanel = observer(function RadarSemanticPanel({
  object,
  canWrite,
  needsSchemaReview = false,
}: {
  object: RadarObject;
  canWrite: boolean;
  needsSchemaReview?: boolean;
}) {
  const { store, busy, error, setError, stale, mutate } = useSemanticMutation(object, canWrite);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<RadarRelation | null>(null);
  const properties = store.propertySnapshots.get(object.id)?.properties;
  const relations = store.relationSnapshots.get(object.id)?.relations;
  const capacities = store.capacitiesFor(object.id);
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
  }, [store, object.id, object.version, stale, busy, setError]);
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
    const capacity = capacities?.relations[edge.id];
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
        {canWrite && capacity?.removable && (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={capacity.requires_review ? "Request removal" : "Remove"}
            aria-label={`Remove ${semanticLabel(edge.relation_type_detail.forward_label)} relation with ${other?.title ?? "object"}`}
            disabled={busy || stale}
            onClick={() => {
              setError(null);
              setRemoving(edge);
            }}
          />
        )}
        {canWrite && capacity && !capacity.removable && (
          <span className="text-11 text-tertiary" data-testid={`relation-${edge.id}-reason`}>
            {capacityReason(capacity.reason)}
          </span>
        )}
      </li>
    );
  };
  return (
    <div className="mt-8 flex flex-col gap-6" aria-busy={busy || stale}>
      {!canWrite && (
        <p className="text-13 text-secondary">
          {needsSchemaReview ? "Review the workspace changes before saving." : "Read-only workspace access."}
        </p>
      )}
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
      {capacities?.metadata_errors.length ? (
        <div role="alert" className="text-13 text-danger-primary" data-testid="radar-metadata-errors">
          This type&apos;s workspace configuration is invalid. Editing is unavailable until an admin fixes it.
          <ul className="list-disc pl-5">
            {capacities.metadata_errors.map((item) => (
              <li key={item.section}>{item.detail}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {capacities && (
        <RadarObjectActions object={object} capacities={capacities} disabled={!canWrite || busy || stale} />
      )}
      {!properties ? (
        <p role="status">Loading properties…</p>
      ) : properties.length === 0 ? (
        <section aria-labelledby="radar-properties-heading">
          <h2 id="radar-properties-heading" className="mb-3 text-16 font-semibold">
            Properties
          </h2>
          <p className="text-13 text-secondary">No properties configured for this type.</p>
        </section>
      ) : (
        propertySections(properties, capacities?.presentation).map((section) => (
          <section
            key={section.key}
            aria-labelledby={`radar-section-${section.key}`}
            data-testid={`radar-section-${section.key}`}
          >
            <h2 id={`radar-section-${section.key}`} className="mb-3 text-16 font-semibold">
              {section.label}
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {section.rows.map((row) => (
                <RadarPropertyEditor
                  key={row.definition.id}
                  row={row}
                  canWrite={canWrite}
                  busy={busy || stale}
                  capacity={capacities?.fields[row.definition.key]}
                  onSave={setProperty}
                  onRemove={removeProperty}
                />
              ))}
            </div>
          </section>
        ))
      )}
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
      {store.relationSnapshots.get(object.id)?.next_cursor && (
        <Button
          label="More relations"
          variant="secondary"
          size="sm"
          stretch="auto"
          disabled={busy || stale}
          onClick={() => {
            void store
              .loadRelations(object.id, store.relationSnapshots.get(object.id)?.next_cursor ?? undefined)
              .catch((cause: unknown) => setError(semanticError(cause)));
          }}
        />
      )}
      {adding && relations && (
        <RadarRelationDialog object={object} onCreate={createRelation} onClose={() => setAdding(false)} />
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
