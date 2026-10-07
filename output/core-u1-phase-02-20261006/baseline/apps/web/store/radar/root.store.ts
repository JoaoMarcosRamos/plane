import { makeAutoObservable, runInAction } from "mobx";
import { RadarMutationIntents } from "./mutation-intents";
import type { RadarService } from "../../services/radar/radar.service";
import type {
  CreateRadarObject,
  RadarObject,
  RadarObjectType,
  UpdateRadarObject,
  RadarPropertyDefinition,
  RadarPropertyData,
  RadarPropertySnapshot,
  RadarRelationType,
  RadarRelationSnapshot,
  CreateRadarRelation,
  RadarRelation,
  RadarMutationContext,
} from "../../services/radar/types";

export type RadarClient = Pick<
  RadarService,
  | "listObjectTypes"
  | "listObjects"
  | "getObject"
  | "createObject"
  | "updateObject"
  | "listPropertyDefinitions"
  | "getProperties"
  | "initializeProperties"
  | "setProperty"
  | "removeProperty"
  | "listRelationTypes"
  | "getRelations"
  | "createRelation"
  | "removeRelation"
>;

/** One instance per workspace; no reference to Plane's root, project or issue stores. */
export class RadarRootStore {
  objectTypes: RadarObjectType[] = [];
  objects = new Map<string, RadarObject>();
  listIds: string[] = [];
  propertyDefinitions: RadarPropertyDefinition[] = [];
  relationTypes: RadarRelationType[] = [];
  propertySnapshots = new Map<string, RadarPropertySnapshot>();
  relationSnapshots = new Map<string, RadarRelationSnapshot>();
  relations = new Map<string, RadarRelation>();
  private readonly intentions = new RadarMutationIntents();
  constructor(
    readonly workspaceSlug: string,
    private readonly service: RadarClient
  ) {
    makeAutoObservable<RadarRootStore, "service" | "intentions">(
      this,
      { workspaceSlug: false, service: false, intentions: false },
      { autoBind: true }
    );
  }
  get listedObjects() {
    return this.listIds.map((id) => this.objects.get(id)).filter((item): item is RadarObject => !!item);
  }
  private cache(object: RadarObject) {
    const previous = this.objects.get(object.id);
    if (!previous || previous.version <= object.version) this.objects.set(object.id, object);
  }
  private mutationContext(ids: string[]): RadarMutationContext {
    const expected_versions: Record<string, number> = {};
    for (const id of new Set(ids)) {
      const object = this.objects.get(id);
      if (!object) throw new Error("Load the object before editing it.");
      expected_versions[id] = object.version;
    }
    return { expected_versions };
  }
  async loadTypes() {
    const types = await this.service.listObjectTypes(this.workspaceSlug);
    runInAction(() => {
      this.objectTypes = types;
    });
  }
  async loadList() {
    const objects = await this.service.listObjects(this.workspaceSlug);
    runInAction(() => {
      objects.forEach((object) => this.cache(object));
      this.listIds = objects.map((object) => object.id);
    });
  }
  async getObject(id: string) {
    const object = await this.service.getObject(this.workspaceSlug, id);
    runInAction(() => this.cache(object));
    return object;
  }
  async createObject(payload: CreateRadarObject) {
    const object = await this.intentions.run(
      "createObject",
      payload,
      () => ({ expected_versions: {} }),
      (input, context) => this.service.createObject(this.workspaceSlug, input, context)
    );
    runInAction(() => {
      this.cache(object);
      if (!this.listIds.includes(object.id)) this.listIds.unshift(object.id);
    });
    return object;
  }
  async updateObject(id: string, payload: UpdateRadarObject) {
    const object = await this.intentions.run(
      `updateObject:${id}`,
      payload,
      () => this.mutationContext([id]),
      (input, context) => this.service.updateObject(this.workspaceSlug, id, input, context)
    );
    runInAction(() => this.cache(object));
    return object;
  }
  propertiesFor(id: string) {
    const snapshot = this.propertySnapshots.get(id);
    return snapshot?.object.version === this.objects.get(id)?.version ? snapshot?.properties : undefined;
  }
  relationsFor(id: string) {
    const snapshot = this.relationSnapshots.get(id);
    return snapshot?.object.version === this.objects.get(id)?.version ? snapshot?.relations : undefined;
  }
  private cacheProperties(snapshot: RadarPropertySnapshot) {
    if ((this.objects.get(snapshot.object.id)?.version ?? 0) > snapshot.object.version) return;
    this.cache(snapshot.object);
    this.propertySnapshots.set(snapshot.object.id, snapshot);
  }
  async loadSemanticTypes() {
    const [definitions, relations] = await Promise.all([
      this.service.listPropertyDefinitions(this.workspaceSlug),
      this.service.listRelationTypes(this.workspaceSlug),
    ]);
    runInAction(() => {
      this.propertyDefinitions = definitions;
      this.relationTypes = relations;
    });
  }
  async loadProperties(id: string) {
    const snapshot = await this.service.getProperties(this.workspaceSlug, id);
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async initializeProperties(id: string) {
    const snapshot = await this.intentions.run(
      `initializeProperties:${id}`,
      {},
      () => this.mutationContext([id]),
      (_input, context) => this.service.initializeProperties(this.workspaceSlug, id, context)
    );
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async setProperty(id: string, definition: string, value: RadarPropertyData) {
    const snapshot = await this.intentions.run(
      `property:${id}:${definition}`,
      { kind: "set", value },
      () => this.mutationContext([id]),
      (input, context) => this.service.setProperty(this.workspaceSlug, id, definition, input.value, context)
    );
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async removeProperty(id: string, definition: string) {
    const snapshot = await this.intentions.run(
      `property:${id}:${definition}`,
      { kind: "remove" },
      () => this.mutationContext([id]),
      (_input, context) => this.service.removeProperty(this.workspaceSlug, id, definition, context)
    );
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async loadObjectSemantics(id: string) {
    // Two scoped snapshots share an aggregate version; retry if a concurrent write crossed the reads.
    for (let attempt = 0; attempt < 3; attempt++) {
      // Retries must be sequential: each read compares against the latest cached aggregate version.
      // eslint-disable-next-line no-await-in-loop
      await Promise.all([this.loadProperties(id), this.loadRelations(id)]);
      if (this.propertiesFor(id) && this.relationsFor(id)) return;
    }
    throw new Error("Object changed while loading. Please refresh.");
  }
  async loadObjectPage(id: string) {
    await Promise.all([this.loadObjectSemantics(id), this.loadSemanticTypes(), this.loadList()]);
    // A list fetched concurrently may carry a newer aggregate version.
    if (!this.propertiesFor(id) || !this.relationsFor(id)) await this.loadObjectSemantics(id);
  }
  async loadRelations(id: string) {
    const snapshot = await this.service.getRelations(this.workspaceSlug, id);
    runInAction(() => {
      if ((this.objects.get(id)?.version ?? 0) > snapshot.object.version) return;
      this.cache(snapshot.object);
      this.relationSnapshots.set(id, snapshot);
      snapshot.relations.forEach((relation) => this.relations.set(relation.id, relation));
    });
    return snapshot;
  }
  async createRelation(payload: CreateRadarRelation) {
    const result = await this.intentions.run(
      `createRelation:${payload.source}`,
      payload,
      () => this.mutationContext([payload.source, payload.target]),
      (input, context) => this.service.createRelation(this.workspaceSlug, input, context)
    );
    runInAction(() => {
      result.objects.forEach((object) => this.cache(object));
      this.relations.set(result.relation.id, result.relation);
    });
    return result;
  }
  async removeRelation(id: string) {
    const relation = this.relations.get(id);
    if (!relation) throw new Error("Load the relation before removing it.");
    const result = await this.intentions.run(
      `removeRelation:${id}`,
      {},
      () => this.mutationContext([relation.source, relation.target]),
      (_input, context) => this.service.removeRelation(this.workspaceSlug, id, context)
    );
    runInAction(() => {
      result.objects.forEach((object) => this.cache(object));
      this.relations.delete(id);
    });
    return result;
  }

  /** Call only after a pending command has been reviewed; resubmit its original input. */
  resumePendingMutation(approvalId: string) {
    this.intentions.resume(approvalId);
  }
}
