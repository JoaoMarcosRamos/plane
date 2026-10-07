import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import type { RadarAttachment, RadarCollaborationCommand } from "@/services/radar/collaboration.types";
import { useRadarCollaborationStore } from "@/store/radar/provider";

type Edit = { id: string; kind: "comment" | "attachment"; value: string };

export const RadarCollaborationPanel = observer(function RadarCollaborationPanel({
  objectId,
  objectVersion,
  canWrite,
}: {
  objectId: string;
  objectVersion: number;
  canWrite: boolean;
}) {
  const store = useRadarCollaborationStore();
  const [draft, setDraft] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [removing, setRemoving] = useState<{ id: string; kind: "comment" | "attachment" } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    void store.load(objectId);
  }, [store, objectId, objectVersion]);
  const snapshot = store.snapshot?.object_id === objectId ? store.snapshot : null;
  const disabled = store.busy || store.loading;
  const writable = canWrite && snapshot?.can_write;
  const submitComment = async (event: React.FormEvent) => {
    event.preventDefault();
    setNotice(null);
    if (await store.command("AddComment", { object_id: objectId, body: draft.trim() })) {
      setDraft("");
      setNotice("Comment saved.");
    }
  };
  const submitUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setNotice(null);
    if (await store.upload(objectId, file)) {
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      setNotice("Attachment saved.");
    }
  };
  const saveEdit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!edit || !snapshot) return;
    const item = (edit.kind === "comment" ? snapshot.comments : snapshot.attachments).find(
      (candidate) => candidate.id === edit.id
    );
    if (!item?.can_edit) return;
    setNotice(null);
    if (
      await store.command(edit.kind === "comment" ? "EditComment" : "RenameAttachment", {
        object_id: objectId,
        item_id: edit.id,
        expected_revision: item.revision,
        ...(edit.kind === "comment" ? { body: edit.value.trim() } : { filename: edit.value.trim() }),
      })
    ) {
      setEdit(null);
      setNotice("Change saved.");
    }
  };
  const confirmRemove = async () => {
    if (!removing || !snapshot) return;
    const item = (removing.kind === "comment" ? snapshot.comments : snapshot.attachments).find(
      (candidate) => candidate.id === removing.id
    );
    if (!item?.can_delete) return;
    setNotice(null);
    const name: RadarCollaborationCommand = removing.kind === "comment" ? "DeleteComment" : "DeleteAttachment";
    if (await store.command(name, { object_id: objectId, item_id: item.id, expected_revision: item.revision })) {
      setRemoving(null);
      setEdit(null);
      setNotice("Item removed. Audit history retained.");
    }
  };
  const download = async (attachment: RadarAttachment) => {
    setNotice(null);
    const blob = await store.download(objectId, attachment.id);
    if (!blob) return;
    const link = document.createElement("a");
    const href = URL.createObjectURL(blob);
    link.href = href;
    link.download = attachment.filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  };
  return (
    <section
      aria-labelledby="radar-collaboration-heading"
      className="mt-8 flex flex-col gap-5 border-t border-subtle pt-6"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 id="radar-collaboration-heading" className="text-18 font-semibold">
          Collaboration
        </h2>
        <Button
          stretch="auto"
          label="Reload"
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() => {
            setNotice(null);
            void store.load(objectId);
          }}
        />
      </div>
      {store.loading && <p role="status">Loading collaboration…</p>}
      {store.busy && <p role="status">Processing…</p>}
      {store.error && <p role="alert">{store.error}</p>}
      {notice && <p role="status">{notice}</p>}
      {snapshot && (
        <>
          <div className="flex flex-col gap-3">
            <h3 className="text-16 font-medium">Comments</h3>
            {!snapshot.comments.length && <p className="text-13 text-secondary">No comments yet.</p>}
            {snapshot.comments.map((comment) => (
              <article key={comment.id} className="rounded border border-subtle p-3">
                <p className="text-12 text-secondary">
                  {comment.author} ·{" "}
                  <time dateTime={comment.created_at}>{new Date(comment.created_at).toLocaleString()}</time>
                  {comment.revision > 1 ? " · edited" : ""}
                </p>
                <p className="my-2 text-13 break-words whitespace-pre-wrap">{comment.body}</p>
                <div className="flex gap-2">
                  {writable && comment.can_edit && (
                    <Button
                      stretch="auto"
                      label="Edit comment"
                      size="sm"
                      variant="secondary"
                      disabled={disabled}
                      onClick={() => {
                        setEdit({ id: comment.id, kind: "comment", value: comment.body });
                        setRemoving(null);
                      }}
                    />
                  )}
                  {writable && comment.can_delete && (
                    <Button
                      stretch="auto"
                      label="Delete comment"
                      size="sm"
                      variant="secondary"
                      disabled={disabled}
                      onClick={() => {
                        setRemoving({ id: comment.id, kind: "comment" });
                        setEdit(null);
                      }}
                    />
                  )}
                </div>
              </article>
            ))}
            {writable && (
              <form onSubmit={submitComment} className="flex flex-col gap-2">
                <TextAreaField
                  id="radar-comment-draft"
                  label="New comment"
                  size="lg"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  maxLength={10000}
                  required
                  disabled={disabled}
                />
                <Button
                  stretch="auto"
                  type="submit"
                  label="Add comment"
                  variant="primary"
                  size="sm"
                  disabled={disabled || !draft.trim()}
                />
              </form>
            )}
          </div>
          <div className="flex flex-col gap-3">
            <h3 className="text-16 font-medium">Attachments</h3>
            <p className="text-13 text-secondary">
              Private supporting files, up to 2 MiB each. Files do not automatically become decision evidence.
            </p>
            {!snapshot.attachments.length && <p className="text-13 text-secondary">No attachments yet.</p>}
            {snapshot.attachments.map((attachment) => (
              <article key={attachment.id} className="rounded border border-subtle p-3">
                <p className="text-13 font-medium break-words">{attachment.filename}</p>
                <p className="text-12 text-secondary">
                  {attachment.author} · {attachment.size} bytes
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    stretch="auto"
                    label={`Download ${attachment.filename}`}
                    size="sm"
                    variant="secondary"
                    disabled={disabled}
                    onClick={() => void download(attachment)}
                  />
                  {writable && attachment.can_edit && (
                    <Button
                      stretch="auto"
                      label="Rename"
                      size="sm"
                      variant="secondary"
                      disabled={disabled}
                      onClick={() => {
                        setEdit({ id: attachment.id, kind: "attachment", value: attachment.filename });
                        setRemoving(null);
                      }}
                    />
                  )}
                  {writable && attachment.can_delete && (
                    <Button
                      stretch="auto"
                      label="Remove attachment"
                      size="sm"
                      variant="secondary"
                      disabled={disabled}
                      onClick={() => {
                        setRemoving({ id: attachment.id, kind: "attachment" });
                        setEdit(null);
                      }}
                    />
                  )}
                </div>
              </article>
            ))}
            {writable && (
              <form onSubmit={submitUpload} className="flex flex-col gap-2">
                <label htmlFor="radar-attachment-file" className="text-13 font-medium">
                  Supporting file
                </label>
                <input
                  id="radar-attachment-file"
                  ref={fileInput}
                  type="file"
                  disabled={disabled}
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  aria-describedby="radar-upload-help"
                />
                {file && <p className="text-12 break-words text-secondary">Selected: {file.name}</p>}
                <p id="radar-upload-help" className="text-12 text-secondary">
                  Choose a nonempty file. A failed request keeps your selection for retry.
                </p>
                <Button
                  stretch="auto"
                  type="submit"
                  label="Upload attachment"
                  variant="primary"
                  size="sm"
                  disabled={disabled || !file}
                />
              </form>
            )}
          </div>
          {edit && writable && (
            <form onSubmit={saveEdit} className="flex flex-col gap-2 rounded border border-subtle p-3">
              {edit.kind === "comment" ? (
                <TextAreaField
                  id="radar-comment-edit"
                  label="Edit comment"
                  size="lg"
                  value={edit.value}
                  onChange={(event) => setEdit({ ...edit, value: event.target.value })}
                  required
                  maxLength={10000}
                  disabled={disabled}
                />
              ) : (
                <InputField
                  id="radar-attachment-rename"
                  label="Filename"
                  size="md"
                  orientation="vertical"
                  value={edit.value}
                  onChange={(event) => setEdit({ ...edit, value: event.target.value })}
                  required
                  maxLength={255}
                  disabled={disabled}
                />
              )}
              <div className="flex gap-2">
                <Button
                  stretch="auto"
                  type="submit"
                  label="Save edit"
                  size="sm"
                  variant="primary"
                  disabled={disabled || !edit.value.trim()}
                />
                <Button
                  stretch="auto"
                  label="Cancel edit"
                  size="sm"
                  variant="secondary"
                  disabled={disabled}
                  onClick={() => setEdit(null)}
                />
              </div>
            </form>
          )}
          {removing && writable && (
            <div
              role="group"
              aria-label="Confirm removal"
              className="flex flex-col gap-2 rounded border border-subtle p-3"
            >
              <p className="text-13">Remove this {removing.kind}? Its history will remain in the audit.</p>
              <div className="flex gap-2">
                <Button
                  stretch="auto"
                  label="Confirm removal"
                  size="sm"
                  variant="primary"
                  disabled={disabled}
                  onClick={() => void confirmRemove()}
                />
                <Button
                  stretch="auto"
                  label="Cancel removal"
                  size="sm"
                  variant="secondary"
                  disabled={disabled}
                  onClick={() => setRemoving(null)}
                />
              </div>
            </div>
          )}
          <div className="flex flex-col gap-3">
            <h3 className="text-16 font-medium">Activity</h3>
            {!snapshot.activity.length && <p className="text-13 text-secondary">No recorded activity.</p>}
            <ol className="flex flex-col gap-3">
              {snapshot.activity.map((activity) => (
                <li key={activity.id} className="border-l border-subtle pl-3 text-13">
                  <p>
                    {activity.command_name.replace(/([a-z])([A-Z])/g, "$1 $2")} · {activity.outcome}
                  </p>
                  <p className="text-12 break-words text-secondary">
                    {activity.actor_type}: {activity.actor_id} ·{" "}
                    <time dateTime={activity.timestamp}>{new Date(activity.timestamp).toLocaleString()}</time>
                  </p>
                  <p className="text-12 break-words text-secondary">
                    {activity.reason} · {activity.source}
                  </p>
                </li>
              ))}
            </ol>
            {snapshot.activity_next && (
              <Button
                stretch="auto"
                label="Older activity"
                size="sm"
                variant="secondary"
                disabled={disabled}
                onClick={() => void store.moreActivity()}
              />
            )}
          </div>
        </>
      )}
    </section>
  );
});
