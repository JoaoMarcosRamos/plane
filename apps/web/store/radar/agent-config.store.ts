import { makeAutoObservable, runInAction } from "mobx";
import type { RadarAgentConfigEntry, UpdateRadarAgentConfiguration } from "../../services/radar/agent-config.types";
import type { RadarService } from "../../services/radar/radar.service";

type AgentConfigClient = Pick<
  RadarService,
  "listAgentConfigurations" | "getAgentConfiguration" | "updateAgentConfiguration"
>;

/** Configuration cache is owned by one workspace, just like the Object store. */
export class RadarAgentConfigStore {
  entries: RadarAgentConfigEntry[] = [];
  constructor(
    readonly workspaceSlug: string,
    private readonly service: AgentConfigClient
  ) {
    makeAutoObservable<RadarAgentConfigStore, "service">(
      this,
      { workspaceSlug: false, service: false },
      { autoBind: true }
    );
  }
  private cache(entry: RadarAgentConfigEntry) {
    const index = this.entries.findIndex((item) => item.binding_id === entry.binding_id);
    if (index === -1) this.entries.push(entry);
    else this.entries[index] = entry;
  }
  async load() {
    const entries = await this.service.listAgentConfigurations(this.workspaceSlug);
    runInAction(() => {
      this.entries = entries;
    });
  }
  async refresh(bindingId: string) {
    const entry = await this.service.getAgentConfiguration(this.workspaceSlug, bindingId);
    runInAction(() => this.cache(entry));
    return entry;
  }
  async save(bindingId: string, payload: UpdateRadarAgentConfiguration) {
    const entry = await this.service.updateAgentConfiguration(this.workspaceSlug, bindingId, payload);
    runInAction(() => this.cache(entry));
    return entry;
  }
}
