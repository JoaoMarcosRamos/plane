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
import { RadarSemanticPanel } from "./semantic-panel";
import { RadarNotesEditor } from "./notes-editor";

const ObjectForm = observer(function ObjectForm({ object, canWrite }: { object: RadarObject; canWrite: boolean }) {
  const store = useRadarStore();
  const [title, setTitle] = useState(object.title);
  const [content, setContent] = useState(object.content);
  const [editorRevision, setEditorRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = title !== object.title || content !== object.content;
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving || !dirty || !title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await store.updateObject(object.id, { title: title.trim(), content });
      setTitle(saved.title);
      setContent(saved.content);
      setEditorRevision((value) => value + 1);
      setToast({ type: "success", title: "Object saved", message: "Changes persisted." });
    } catch (cause) {
      console.error("RADAR update failed", cause);
      setError("Could not save object. Check your membership and try again.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <form onSubmit={save} className="flex flex-col gap-5">
      <p className="text-13 text-secondary">{object.object_type_detail.name}</p>
      <InputField
        id="radar-edit-title"
        label="Title"
        orientation="vertical"
        size="xl"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        required
        maxLength={255}
        disabled={saving || !canWrite}
      />
      <div>
        <h2 className="mb-2 text-16 font-medium">Content</h2>
        <RadarNotesEditor
          key={editorRevision}
          id={object.id}
          initialValue={content || "<p></p>"}
          onChange={setContent}
          editable={canWrite && !saving}
        />
      </div>
      <dl className="grid grid-cols-[120px_1fr] gap-2 text-13" data-testid="radar-audit">
        <dt>Created by</dt>
        <dd data-testid="radar-created-by">{object.created_by ?? "Deleted user"}</dd>
        <dt>Updated by</dt>
        <dd data-testid="radar-updated-by">{object.updated_by ?? "Deleted user"}</dd>
        <dt>Version</dt>
        <dd data-testid="radar-version">{object.version}</dd>
      </dl>
      {error && <p role="alert">{error}</p>}
      <Button
        stretch="auto"
        variant="primary"
        size="md"
        type="submit"
        label={saving ? "Saving…" : "Save changes"}
        disabled={!canWrite || saving || !dirty || !title.trim()}
      />
    </form>
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
          <ObjectForm key={object.id} object={object} canWrite={canWrite} />
          <RadarSemanticPanel key={`semantic:${object.id}`} object={object} canWrite={canWrite} />
          <RadarCollaborationPanel
            key={`collaboration:${object.id}`}
            objectId={object.id}
            objectVersion={object.version}
            canWrite={canWrite}
          />
        </>
      )}
    </div>
  );
});
