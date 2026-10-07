import { makeAutoObservable, runInAction } from "mobx";
import { RadarMutationIntents } from "./mutation-intents";
import type { RadarService } from "../../services/radar/radar.service";
import type {
  CreateRadarObject,
  RadarObject,
  RadarObjectCollection,
  RadarObjectSummary,
  RadarObjectQuery,
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
  RadarSchemaCatalog,
  RadarObjectCapacities,
  RadarCommandPreview,
  RadarCapabilityContract,
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
> &
  Partial<Pick<RadarService, "getSchema" | "getCapacities" | "previewCommand" | "executeCommand">>;

/** One instance per workspace; no reference to Plane's root, project or issue stores. */
export class RadarRootStore {
  schemaRevision = 0;
  authorityRevision = "";
  canWrite = true;
  schemaStatus: RadarSchemaCatalog["status"] = "uninitialized";
  private catalogRequest = 0;
  objectTypes: RadarObjectType[] = [];
  objects = new Map<string, RadarObject>();
  listIds: string[] = [];
  listCursor: string | null = null;
  private listRequest = 0;
  propertyDefinitions: RadarPropertyDefinition[] = [];
  relationTypes: RadarRelationType[] = [];
  capabilities: Record<string, RadarCapabilityContract> = {};
  propertySnapshots = new Map<string, RadarPropertySnapshot>();
  relationSnapshots = new Map<string, RadarRelationSnapshot>();
  capacitySnapshots = new Map<string, RadarObjectCapacities>();
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
    if (
      this.authorityRevision === "unavailable" ||
      (object.schema_revision ?? this.schemaRevision) < this.schemaRevision
    )
      return;
    if (!previous || previous.version <= object.version) this.objects.set(object.id, object);
  }
  private cacheSummary(summary: RadarObjectSummary) {
    const type = this.objectTypes.find((item) => item.id === summary.object_type) ?? summary.object_type_detail;
    if (!type) return;
    const previous = this.objects.get(summary.id);
    this.cache({
      ...summary,
      object_type_detail: type,
      content: summary.content ?? (previous?.version === summary.version ? previous.content : ""),
    });
  }
  async searchObjects(query: RadarObjectQuery) {
    const rows = await this.service.listObjects(this.workspaceSlug, query);
    if ((rows.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    if (
      this.authorityRevision === "unavailable" ||
      (rows.schema_revision ?? this.schemaRevision) !== this.schemaRevision
    )
      throw new Error("Workspace definitions changed. Search again.");
    return rows;
  }
  private async runMutation<Input, Result>(
    slot: string,
    payload: Input,
    contextFactory: () => RadarMutationContext,
    operation: (input: Input, context: RadarMutationContext) => Promise<Result>
  ): Promise<Result> {
    try {
      return await this.intentions.run(slot, payload, contextFactory, operation);
    } catch (cause) {
      const status = (cause as { response?: { status?: number } })?.response?.status;
      if (status === 409)
        await this.loadSchema().catch((error: unknown) => console.error("RADAR schema refresh failed", error));
      throw cause;
    }
  }
  private mutationContext(ids: string[]): RadarMutationContext {
    const expected_versions: Record<string, number> = {};
    for (const id of new Set(ids)) {
      const object = this.objects.get(id);
      if (!object) throw new Error("Load the object before editing it.");
      expected_versions[id] = object.version;
    }
    if (!this.canWrite) throw new Error("Your workspace permission changed. Refresh and review your access.");
    return { expected_versions, expected_schema_revision: this.schemaRevision };
  }
  private applyCatalog(catalog: RadarSchemaCatalog, request: number) {
    if (
      catalog.schema_revision < this.schemaRevision ||
      (catalog.schema_revision === this.schemaRevision && request !== this.catalogRequest)
    )
      return;
    if (catalog.schema_revision !== this.schemaRevision || catalog.authority_revision !== this.authorityRevision) {
      this.relations.clear();
      this.capacitySnapshots.clear();
    }
    this.schemaRevision = catalog.schema_revision;
    this.authorityRevision = catalog.authority_revision;
    this.canWrite = catalog.can_write && catalog.status !== "uninitialized";
    this.schemaStatus = catalog.status;
    this.objectTypes = catalog.object_types;
    this.propertyDefinitions = catalog.property_definitions;
    this.relationTypes = catalog.relation_types;
    this.capabilities = catalog.capabilities ?? {};
    for (const [id, object] of this.objects) {
      const type = catalog.object_types.find((item) => item.id === object.object_type);
      if (type) this.objects.set(id, { ...object, object_type_detail: type });
      else this.objects.delete(id);
    }
    this.listIds = this.listIds.filter((id) => this.objects.has(id));
  }
  async loadSchema() {
    // Production uses one atomically read catalog. The fallback supports existing injected clients.
    if (!this.service.getSchema) return;
    const request = ++this.catalogRequest;
    try {
      const catalog = await this.service.getSchema(this.workspaceSlug);
      runInAction(() => this.applyCatalog(catalog, request));
    } catch (cause) {
      const status = (cause as { response?: { status?: number } })?.response?.status;
      if (request === this.catalogRequest && (status === 401 || status === 403)) {
        runInAction(() => {
          this.canWrite = false;
          this.authorityRevision = "unavailable";
          this.objects.clear();
          this.listIds = [];
          this.listCursor = null;
          this.relations.clear();
          this.propertySnapshots.clear();
          this.relationSnapshots.clear();
          this.capacitySnapshots.clear();
          this.objectTypes = [];
          this.propertyDefinitions = [];
          this.relationTypes = [];
          this.listRequest++;
        });
      }
      throw cause;
    }
  }
  async loadTypes() {
    if (this.service.getSchema) return this.loadSchema();
    const types = await this.service.listObjectTypes(this.workspaceSlug);
    runInAction(() => {
      this.objectTypes = types;
    });
  }
  async loadList(query?: RadarObjectQuery, append = false) {
    const request = ++this.listRequest;
    const objects = await (query
      ? this.service.listObjects(this.workspaceSlug, query)
      : this.service.listObjects(this.workspaceSlug));
    if ((objects.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    runInAction(() => {
      if (
        this.authorityRevision === "unavailable" ||
        request !== this.listRequest ||
        (objects.schema_revision ?? this.schemaRevision) !== this.schemaRevision
      )
        return;
      objects.forEach((object) => this.cacheSummary(object));
      const ids = objects.filter((object) => this.objects.has(object.id)).map((object) => object.id);
      this.listIds = append ? Array.from(new Set([...this.listIds, ...ids])) : ids;
      this.listCursor = objects.next_cursor ?? null;
    });
  }
  async getObject(id: string) {
    const object = await this.service.getObject(this.workspaceSlug, id);
    runInAction(() => this.cache(object));
    return object;
  }
  async createObject(payload: CreateRadarObject) {
    const object = await this.runMutation(
      "createObject",
      payload,
      () => this.mutationContext([]),
      (input, context) => this.service.createObject(this.workspaceSlug, input, context)
    );
    runInAction(() => {
      this.cache(object);
      if (!this.listIds.includes(object.id)) this.listIds.unshift(object.id);
    });
    return object;
  }
  async updateObject(id: string, payload: UpdateRadarObject) {
    const object = await this.runMutation(
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
    return snapshot?.object.version === this.objects.get(id)?.version &&
      (snapshot?.schema_revision ?? 0) === this.schemaRevision
      ? snapshot?.properties
      : undefined;
  }
  relationsFor(id: string) {
    const snapshot = this.relationSnapshots.get(id);
    return snapshot?.object.version === this.objects.get(id)?.version &&
      (snapshot?.schema_revision ?? 0) === this.schemaRevision
      ? snapshot?.relations
      : undefined;
  }
  /** Actor-specific capacities for the cached Object version and schema revision, if current. */
  capacitiesFor(id: string) {
    const snapshot = this.capacitySnapshots.get(id);
    return snapshot?.object.version === this.objects.get(id)?.version &&
      snapshot?.schema_revision === this.schemaRevision
      ? snapshot
      : undefined;
  }
  async loadCapacities(id: string, relationIds?: string[]) {
    if (!this.service.getCapacities) return undefined;
    const snapshot = await (relationIds
      ? this.service.getCapacities(this.workspaceSlug, id, relationIds)
      : this.service.getCapacities(this.workspaceSlug, id));
    if (snapshot.schema_revision > this.schemaRevision) await this.loadSchema();
    runInAction(() => {
      if (this.authorityRevision === "unavailable" || snapshot.schema_revision !== this.schemaRevision) return;
      if ((this.objects.get(id)?.version ?? 0) > snapshot.object.version) return;
      const previous = this.capacitiesFor(id);
      this.capacitySnapshots.set(
        id,
        relationIds && previous
          ? { ...snapshot, relations: { ...previous.relations, ...snapshot.relations } }
          : snapshot
      );
    });
    return snapshot;
  }
  async previewCommand(name: string, input: Record<string, unknown>, reason: string): Promise<RadarCommandPreview> {
    if (!this.service.previewCommand) throw new Error("Command preview is unavailable.");
    return this.service.previewCommand(this.workspaceSlug, {
      command_name: name,
      command_version: 1,
      input,
      reason,
      expected_schema_revision: this.schemaRevision,
    });
  }
  /**
   * Execute a reviewed governed command. The page Object keeps the version whose snapshot the user is
   * looking at; every other dependency keeps the version shown in the reviewed preview. Any change
   * since then fails on the server as a conflict instead of being rebased silently.
   */
  async runCommand(objectId: string, name: string, input: Record<string, unknown>, preview: RadarCommandPreview) {
    const executeCommand = this.service.executeCommand;
    if (!executeCommand) throw new Error("Governed commands are unavailable.");
    const result = await this.runMutation(
      `command:${name}:${objectId}`,
      { name, input },
      () => {
        if (!this.canWrite) throw new Error("Your workspace permission changed. Refresh and review your access.");
        const viewed = this.objects.get(objectId)?.version;
        const expected_versions = {
          ...preview.expected_versions,
          ...(viewed !== undefined && objectId in preview.expected_versions ? { [objectId]: viewed } : {}),
        };
        return { expected_versions, expected_schema_revision: this.schemaRevision, reason: name };
      },
      (payload, context) => executeCommand.call(this.service, this.workspaceSlug, payload.name, payload.input, context)
    );
    await this.loadObjectSemantics(objectId);
    return result;
  }
  private cacheProperties(snapshot: RadarPropertySnapshot) {
    if (this.authorityRevision === "unavailable" || (snapshot.schema_revision ?? 0) !== this.schemaRevision) return;
    if ((this.objects.get(snapshot.object.id)?.version ?? 0) > snapshot.object.version) return;
    this.cache(snapshot.object);
    this.propertySnapshots.set(snapshot.object.id, snapshot);
  }
  async loadSemanticTypes() {
    if (this.service.getSchema) return this.loadSchema();
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
    if ((snapshot.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async initializeProperties(id: string) {
    const snapshot = await this.runMutation(
      `initializeProperties:${id}`,
      {},
      () => this.mutationContext([id]),
      (_input, context) => this.service.initializeProperties(this.workspaceSlug, id, context)
    );
    if ((snapshot.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async setProperty(id: string, definition: string, value: RadarPropertyData) {
    const snapshot = await this.runMutation(
      `property:${id}:${definition}`,
      { kind: "set", value },
      () => this.mutationContext([id]),
      (input, context) => this.service.setProperty(this.workspaceSlug, id, definition, input.value, context)
    );
    if ((snapshot.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async removeProperty(id: string, definition: string) {
    const snapshot = await this.runMutation(
      `property:${id}:${definition}`,
      { kind: "remove" },
      () => this.mutationContext([id]),
      (_input, context) => this.service.removeProperty(this.workspaceSlug, id, definition, context)
    );
    if ((snapshot.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    runInAction(() => this.cacheProperties(snapshot));
    return snapshot;
  }
  async loadObjectSemantics(id: string) {
    // Two scoped snapshots share an aggregate version; retry if a concurrent write crossed the reads.
    for (let attempt = 0; attempt < 3; attempt++) {
      // Retries must be sequential: each read compares against the latest cached aggregate version.
      // eslint-disable-next-line no-await-in-loop
      await Promise.all([this.loadProperties(id), this.loadRelations(id), this.loadCapacities(id)]);
      if (this.propertiesFor(id) && this.relationsFor(id) && (!this.service.getCapacities || this.capacitiesFor(id)))
        return;
    }
    throw new Error("Object changed while loading. Please refresh.");
  }
  async loadObjectPage(id: string) {
    if (this.service.getSchema) await this.loadSemanticTypes();
    else await Promise.all([this.loadTypes(), this.loadSemanticTypes()]);
    await this.loadObjectSemantics(id);
    // Concurrent reads may carry different aggregate versions.
    if (!this.propertiesFor(id) || !this.relationsFor(id) || (this.service.getCapacities && !this.capacitiesFor(id)))
      await this.loadObjectSemantics(id);
  }
  async loadRelations(id: string, cursor?: string) {
    const snapshot = await (cursor
      ? this.service.getRelations(this.workspaceSlug, id, cursor)
      : this.service.getRelations(this.workspaceSlug, id));
    if ((snapshot.schema_revision ?? 0) > this.schemaRevision) await this.loadSchema();
    runInAction(() => {
      if (this.authorityRevision === "unavailable" || (snapshot.schema_revision ?? 0) !== this.schemaRevision) return;
      if ((this.objects.get(id)?.version ?? 0) > snapshot.object.version) return;
      this.cache(snapshot.object);
      const previous = this.relationSnapshots.get(id);
      if (cursor && (previous?.next_cursor !== cursor || previous.object.version !== snapshot.object.version)) return;
      snapshot.endpoints?.forEach((endpoint) => this.cacheSummary(endpoint));
      this.relationSnapshots.set(
        id,
        cursor && previous
          ? {
              ...snapshot,
              relations: Array.from(
                new Map([...previous.relations, ...snapshot.relations].map((edge) => [edge.id, edge])).values()
              ),
            }
          : snapshot
      );
      snapshot.relations.forEach((relation) => this.relations.set(relation.id, relation));
    });
    if (cursor)
      await this.loadCapacities(
        id,
        snapshot.relations.map((edge) => edge.id)
      );
    return snapshot;
  }
  async createRelation(payload: CreateRadarRelation) {
    await Promise.all(
      [payload.source, payload.target].filter((id) => !this.propertySnapshots.has(id)).map((id) => this.getObject(id))
    );
    const result = await this.runMutation(
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
    await Promise.all(
      [relation.source, relation.target]
        .filter((endpoint) => !this.propertySnapshots.has(endpoint))
        .map((endpoint) => this.getObject(endpoint))
    );
    const result = await this.runMutation(
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
