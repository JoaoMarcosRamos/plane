import { makeAutoObservable, runInAction } from "mobx";
import type { RadarService } from "../../services/radar/radar.service";
import type {
  RadarOperationalSnapshot,
  RadarOperationalEntry,
  RadarOperationalKind,
} from "../../services/radar/operational.types";

/** Read-only, per-session history. Paging never mutates or loads the workspace catalog. */
export class RadarOperationalStore {
  snapshot: RadarOperationalSnapshot | null = null;
  entries: RadarOperationalEntry[] = [];
  cursor: string | null = null;
  kind: RadarOperationalKind | undefined;
  loading = false;
  error: string | null = null;
  private request = 0;
  private objectId = "";
  constructor(
    readonly workspaceSlug: string,
    private readonly service: Pick<RadarService, "getOperations" | "getOperationalHistory">
  ) {
    makeAutoObservable<RadarOperationalStore, "service">(
      this,
      { workspaceSlug: false, service: false },
      { autoBind: true }
    );
  }
  clear() {
    this.request++;
    this.snapshot = null;
    this.entries = [];
    this.cursor = null;
    this.loading = false;
  }
  invalidate() {
    this.clear();
    this.error = "Não foi possível atualizar o Object. O histórico anterior foi descartado.";
  }
  async load(objectId: string, version: number, schemaRevision: number, timezone: string, kind?: RadarOperationalKind) {
    this.clear();
    const request = ++this.request;
    this.objectId = objectId;
    this.kind = kind;
    this.loading = true;
    this.error = null;
    try {
      const [snapshot, history] = await Promise.all([
        this.service.getOperations(this.workspaceSlug, objectId, timezone),
        this.service.getOperationalHistory(this.workspaceSlug, objectId, { kind, limit: 20 }),
      ]);
      if (request !== this.request) return;
      if (
        snapshot.object_id !== objectId ||
        history.object_id !== objectId ||
        snapshot.object_version < version ||
        snapshot.schema_revision < schemaRevision ||
        snapshot.object_version !== history.object_version ||
        snapshot.schema_revision !== history.schema_revision
      )
        throw new Error("Operational snapshots changed during loading.");
      runInAction(() => {
        this.snapshot = snapshot;
        this.entries = history.items;
        this.cursor = history.next_cursor;
      });
    } catch (cause) {
      if (request !== this.request) return;
      console.error("Unable to load operational history", cause);
      runInAction(() => {
        this.error = "Não foi possível carregar um histórico atual. Atualize o Object e tente novamente.";
      });
    } finally {
      if (request === this.request)
        runInAction(() => {
          this.loading = false;
        });
    }
  }
  async loadMore() {
    if (this.loading || !this.cursor || !this.snapshot) return;
    const request = ++this.request;
    const snapshot = this.snapshot;
    this.loading = true;
    this.error = null;
    try {
      const history = await this.service.getOperationalHistory(this.workspaceSlug, this.objectId, {
        kind: this.kind,
        cursor: this.cursor,
        limit: 20,
      });
      if (request !== this.request) return;
      if (
        history.object_id !== snapshot.object_id ||
        history.object_version !== snapshot.object_version ||
        history.schema_revision !== snapshot.schema_revision
      )
        throw new Error("History changed while paging.");
      runInAction(() => {
        const known = new Set(this.entries.map((entry) => entry.id));
        this.entries.push(...history.items.filter((entry) => !known.has(entry.id)));
        this.cursor = history.next_cursor;
      });
    } catch (cause) {
      if (request !== this.request) return;
      console.error("Unable to page operational history", cause);
      runInAction(() => {
        this.snapshot = null;
        this.entries = [];
        this.cursor = null;
        this.error = "O histórico mudou ou o acesso não está disponível. Atualize o Object.";
      });
    } finally {
      if (request === this.request)
        runInAction(() => {
          this.loading = false;
        });
    }
  }
}
