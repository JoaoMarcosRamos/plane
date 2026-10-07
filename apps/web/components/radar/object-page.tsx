import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useUserPermissions } from "@/hooks/store/user";
import type { RadarObject } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import { RadarCollaborationPanel } from "./collaboration-panel";
import { RadarOperationalPanel } from "./operational-panel";
import { RadarNarrativeProperty, RadarSemanticPanel } from "./semantic-panel";
import { RadarNotesEditor } from "./notes-editor";
import { actorLabel } from "./actor-summary";
import { capacityReason } from "./capacity-text";
import { RadarSchemaReview, useRadarSchemaReview } from "./schema-review";
import { semanticError, semanticLabel } from "./semantic-utils";

/**
 * Title plus Object.content. The layout (C21) decides whether content is the principal narrative or
 * complementary notes; a narrative property is edited in its own slot, never in two inputs.
 */
const ObjectForm = observer(function ObjectForm({ object, canWrite }: { object: RadarObject; canWrite: boolean }) {
  const store = useRadarStore();
  const capacities = store.capacitiesFor(object.id);
  const layout = capacities?.presentation;
  const notes = layout?.content.role === "notes";
  const titleEditable = canWrite && !!capacities?.envelope.title.editable;
  const contentEditable = canWrite && !!capacities?.envelope.content.editable;
  const [title, setTitle] = useState(object.title);
  const [content, setContent] = useState(object.content);
  const [editorRevision, setEditorRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = title !== object.title || content !== object.content;
  const writable = (titleEditable || contentEditable) && dirty;
  // A <div>, not a <form>: the narrative property editor between title and notes is its own form.
  const save = async () => {
    if (!writable || saving || !title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const changes = {
        ...(title !== object.title ? { title: title.trim() } : {}),
        ...(content !== object.content ? { content } : {}),
      };
      const saved = await store.updateObject(object.id, changes);
      setTitle(saved.title);
      setContent(saved.content);
      setEditorRevision((value) => value + 1);
      setToast({ type: "success", title: "Object saved", message: "Changes persisted." });
    } catch (cause) {
      console.error("RADAR update failed", cause);
      setError(semanticError(cause));
    } finally {
      setSaving(false);
    }
  };
  const envelopeReason = capacities ? capacityReason(capacities.envelope.title.reason) : null;
  const contentEditor = (
    <div data-testid={notes ? "radar-content-notes" : "radar-content-narrative"}>
      <h2 className="mb-1 text-16 font-medium">
        {notes ? "Notes" : semanticLabel(layout?.narrative.label ?? "Content")}
      </h2>
      {notes && (
        <p className="mb-2 text-12 text-tertiary">
          Complementary notes. The main narrative is {semanticLabel(layout.narrative.label).toLowerCase()}.
          {layout.legacy_notes && " These notes were kept from earlier edits; nothing was copied or replaced."}
        </p>
      )}
      <RadarNotesEditor
        key={editorRevision}
        id={object.id}
        initialValue={content || "<p></p>"}
        onChange={setContent}
        editable={contentEditable && !saving}
      />
    </div>
  );
  return (
    <div className="flex flex-col gap-5">
      <p className="text-13 text-secondary">{object.object_type_detail.name}</p>
      <InputField
        id="radar-edit-title"
        label="Title"
        orientation="vertical"
        size="xl"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") void save();
        }}
        required
        maxLength={255}
        disabled={saving || !titleEditable}
      />
      {canWrite && capacities && !capacities.envelope.title.editable && envelopeReason && (
        <p className="text-12 text-tertiary">{envelopeReason}</p>
      )}
      {notes ? <RadarNarrativeProperty object={object} canWrite={canWrite} /> : contentEditor}
      {layout?.retired_references.length ? (
        <p className="text-12 text-tertiary" data-testid="radar-retired-references">
          Retired fields are no longer shown: {layout.retired_references.map(semanticLabel).join(", ")}.
        </p>
      ) : null}
      {notes && contentEditor}
      <dl className="grid grid-cols-[120px_1fr] gap-2 text-13" data-testid="radar-audit">
        <dt>Created by</dt>
        <dd data-testid="radar-created-by" title={object.created_actor?.source ?? undefined}>
          {actorLabel(object.created_actor, object.created_by)}
        </dd>
        <dt>Updated by</dt>
        <dd data-testid="radar-updated-by" title={object.updated_actor?.source ?? undefined}>
          {actorLabel(object.updated_actor, object.updated_by)}
        </dd>
        <dt>Version</dt>
        <dd data-testid="radar-version">{object.version}</dd>
      </dl>
      {error && <p role="alert">{error}</p>}
      <Button
        stretch="auto"
        variant="primary"
        size="md"
        type="button"
        label={saving ? "Saving…" : notes ? "Save title and notes" : "Save changes"}
        disabled={!writable || saving || !title.trim()}
        onClick={() => void save()}
      />
    </div>
  );
});

export const RadarObjectPage = observer(function RadarObjectPage({ objectId }: { objectId: string }) {
  const store = useRadarStore();
  const { allowPermissions } = useUserPermissions();
  const canWrite = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.WORKSPACE,
    store.workspaceSlug
  );
  const schemaReview = useRadarSchemaReview();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setStatus("loading");
    store
      .loadObjectPage(objectId)
      .then(() => {
        if (active) setStatus("ready");
        return undefined;
      })
      .catch((error: unknown) => {
        console.error("RADAR detail failed", error);
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [store, objectId, retry]);
  const object = store.objects.get(objectId);
  return (
    <div className="mx-auto w-full max-w-4xl overflow-auto p-6">
      <Link href={`/${store.workspaceSlug}/radar/objects/`} className="mb-5 inline-block text-13 underline">
        All objects
      </Link>
      {status === "loading" && <p role="status">Loading object…</p>}
      {status === "error" && (
        <div role="alert">
          Object unavailable.{" "}
          <button onClick={() => setRetry((value) => value + 1)} className="underline">
            Retry
          </button>
        </div>
      )}
      {status === "ready" && object && (
        <>
          <RadarSchemaReview pending={schemaReview.pending} onReview={schemaReview.review} />
          <ObjectForm key={object.id} object={object} canWrite={canWrite && schemaReview.canWrite} />
          <RadarSemanticPanel
            key={`semantic:${object.id}`}
            object={object}
            canWrite={canWrite && schemaReview.canWrite}
            needsSchemaReview={schemaReview.pending}
          />
          <RadarCollaborationPanel
            key={`collaboration:${object.id}`}
            objectId={object.id}
            objectVersion={object.version}
            canWrite={canWrite && store.canWrite}
          />
          <RadarOperationalPanel key={`operations:${object.id}`} objectId={object.id} objectVersion={object.version} />
        </>
      )}
    </div>
  );
});
