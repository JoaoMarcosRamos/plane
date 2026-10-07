import { makeAutoObservable, runInAction } from "mobx";
import { v4 as uuidv4 } from "uuid";
import type { RadarService } from "../../services/radar/radar.service";
import type { RadarMutationContext } from "../../services/radar/types";
import type {
  RadarCollaborationSnapshot,
  RadarCollaborationCommand,
  RadarCollaborationInput,
} from "../../services/radar/collaboration.types";

type Client = Pick<
  RadarService,
  "getCollaboration" | "collaborationCommand" | "uploadObjectAttachment" | "downloadObjectAttachment"
>;
function statusOf(cause: unknown): number | undefined {
  return (cause as { response?: { status?: number } })?.response?.status;
}
export function collaborationError(cause: unknown): string {
  const status = statusOf(cause);
  if (status === 409) return "This item or Object changed. Reload and review before trying again.";
  if (status === 403) return "Your current membership or authorship does not permit this action.";
  if (status === 404) return "This Object or collaboration item is no longer available.";
  if (status === 400) return "Check the text, filename and file size (nonempty, at most 2 MiB).";
  return "Could not complete the request. Retry the same action to check its result.";
}

/** Scoped separately from semantic state: comments never modify decision approval versions. */
export class RadarCollaborationStore {
  snapshot: RadarCollaborationSnapshot | null = null;
  loading = false;
  busy = false;
  error: string | null = null;
  private generation = 0;
  private objectId: string | null = null;
  private intention: { signature: string; file?: File; context: RadarMutationContext } | null = null;
  constructor(
    readonly workspaceSlug: string,
    private readonly service: Client
  ) {
    makeAutoObservable<RadarCollaborationStore, "service" | "generation" | "intention" | "objectId">(
      this,
      { workspaceSlug: false, service: false, generation: false, objectId: false, intention: false },
      { autoBind: true }
    );
  }
  async load(id: string): Promise<boolean> {
    this.objectId = id;
    const generation = ++this.generation;
    this.loading = true;
    this.snapshot = null;
    this.error = null;
    try {
      const snapshot = await this.service.getCollaboration(this.workspaceSlug, id);
      if (generation !== this.generation) return false;
      runInAction(() => {
        this.snapshot = snapshot;
      });
      return true;
    } catch (cause) {
      console.error("RADAR collaboration load failed", cause);
      if (generation === this.generation)
        runInAction(() => {
          this.error = collaborationError(cause);
        });
      return false;
    } finally {
      if (generation === this.generation)
        runInAction(() => {
          this.loading = false;
        });
    }
  }
  private context(signature: string, file?: File): RadarMutationContext {
    if (this.intention?.signature === signature && this.intention.file === file) return this.intention.context;
    if (!this.snapshot?.can_write) throw new Error("Load writable collaboration before editing.");
    const context = {
      expected_versions: { [this.snapshot.object_id]: this.snapshot.object_version },
      idempotency_key: uuidv4(),
    };
    this.intention = { signature, file, context };
    return context;
  }
  private async mutate(
    id: string,
    operation: (context: RadarMutationContext) => Promise<unknown>,
    signature: string,
    file?: File
  ) {
    if (this.busy || this.loading || this.snapshot?.object_id !== id || !this.snapshot.can_write) return false;
    this.busy = true;
    this.error = null;
    try {
      const context = this.context(signature, file);
      await operation(context);
      this.intention = null;
      if (this.objectId !== id) return true;
      const loaded = await this.load(id);
      if (!loaded)
        runInAction(() => {
          this.error = "Change saved. Reload to see the current collaboration.";
        });
      return true;
    } catch (cause) {
      console.error("RADAR collaboration mutation failed", cause);
      // An explicit server rejection is safe to revise; uncertain transport errors retain the exact intention.
      if ([400, 403, 404, 409].includes(statusOf(cause) ?? 0)) this.intention = null;
      if (this.objectId !== id) return false;
      runInAction(() => {
        this.error = collaborationError(cause);
        if ([403, 404, 409].includes(statusOf(cause) ?? 0)) this.snapshot = null;
      });
      return false;
    } finally {
      runInAction(() => {
        this.busy = false;
      });
    }
  }
  async command(name: RadarCollaborationCommand, input: RadarCollaborationInput) {
    return this.mutate(
      input.object_id,
      (context) => this.service.collaborationCommand(this.workspaceSlug, name, input, context),
      JSON.stringify({ name, input })
    );
  }
  async upload(id: string, file: File) {
    if (file.size === 0 || file.size > 2 * 1024 * 1024) {
      this.error = "Choose a nonempty file no larger than 2 MiB.";
      return false;
    }
    return this.mutate(
      id,
      (context) => this.service.uploadObjectAttachment(this.workspaceSlug, id, file, context),
      `upload:${id}`,
      file
    );
  }
  async download(id: string, attachmentId: string): Promise<Blob | null> {
    if (this.busy) return null;
    this.busy = true;
    this.error = null;
    try {
      return await this.service.downloadObjectAttachment(this.workspaceSlug, id, attachmentId);
    } catch (cause) {
      console.error("RADAR attachment download failed", cause);
      runInAction(() => {
        this.error = collaborationError(cause);
      });
      return null;
    } finally {
      runInAction(() => {
        this.busy = false;
      });
    }
  }
  async moreActivity() {
    const snapshot = this.snapshot;
    if (!snapshot?.activity_next || this.busy || this.loading) return;
    const generation = this.generation;
    this.busy = true;
    try {
      const page = await this.service.getCollaboration(this.workspaceSlug, snapshot.object_id, snapshot.activity_next);
      if (generation !== this.generation || this.snapshot !== snapshot) return;
      runInAction(() => {
        const seen = new Set(snapshot.activity.map((item) => item.id));
        snapshot.activity.push(...page.activity.filter((item) => !seen.has(item.id)));
        snapshot.activity_next = page.activity_next;
      });
    } catch (cause) {
      console.error("RADAR activity pagination failed", cause);
      runInAction(() => {
        this.error = collaborationError(cause);
      });
    } finally {
      runInAction(() => {
        this.busy = false;
      });
    }
  }
}
