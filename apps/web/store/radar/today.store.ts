import { makeAutoObservable, runInAction } from "mobx";
import type { RadarService } from "../../services/radar/radar.service";
import type { RadarTodayQueue } from "../../services/radar/today.types";

export class RadarTodayStore {
  queue: RadarTodayQueue | null = null;
  loading = false;
  error: string | null = null;
  constructor(
    readonly workspaceSlug: string,
    private readonly service: Pick<RadarService, "getToday">,
    readonly timezone: string
  ) {
    makeAutoObservable<RadarTodayStore, "service">(
      this,
      { workspaceSlug: false, service: false, timezone: false },
      { autoBind: true }
    );
  }
  async load() {
    if (this.loading) return;
    this.loading = true;
    this.error = null;
    // Hide stale approvals during reload and after a failed request.
    this.queue = null;
    try {
      const queue = await this.service.getToday(this.workspaceSlug, this.timezone);
      runInAction(() => {
        this.queue = queue;
      });
    } catch (cause) {
      console.error("Unable to load RADAR Today", cause);
      runInAction(() => {
        this.error = "Não foi possível carregar a atenção de hoje. Tente novamente.";
      });
    } finally {
      runInAction(() => {
        this.loading = false;
      });
    }
  }
}
