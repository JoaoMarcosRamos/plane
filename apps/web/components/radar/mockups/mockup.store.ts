/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import { makeAutoObservable, toJS } from "mobx";
import type {
  TMockEvidence,
  TMockInboxEntry,
  TMockItem,
  TMockKind,
  TMockNow,
  TMockPerson,
  TMockPriority,
  TMockProject,
  TMockRecord,
  TMockStatus,
  TMockSuggestion,
  TMockWeekResult,
} from "./mock-data";
import {
  ME_ID,
  MOCK_INBOX,
  MOCK_ITEMS,
  MOCK_NOW,
  MOCK_PEOPLE,
  MOCK_PROJECTS,
  MOCK_RITUAL_MARKS,
  MOCK_WEEK_RESULTS,
  mockNow,
  resetMockNow,
  setMockNow,
} from "./mock-data";
import type { TCaptureGuess, TRitualMarks, TStatusMove, TVerbKey } from "./interaction-model";
import {
  STALL_CAUSES,
  STATUS_LABEL,
  addDays,
  approvalBlockers,
  buildHoje,
  closeDayQueue,
  dayMonth,
  diffDays,
  isOpen,
  nextMonday,
  parseCapture,
  pendingInforms,
  ritualFor,
  sinceLastReview,
  statusMove,
  suggestFollowUp,
} from "./interaction-model";
import type { TDelta, TEntity, TUndoState } from "./undo";
import { diffStates, isEmptyDelta, revertDelta } from "./undo";

export type TRejectReason = "ja_sabia" | "redundante" | "incorreta" | "fora_de_hora";

export const REJECT_REASONS: { key: TRejectReason; label: string }[] = [
  { key: "ja_sabia", label: "Já sabia" },
  { key: "redundante", label: "Redundante" },
  { key: "incorreta", label: "Incorreta" },
  { key: "fora_de_hora", label: "Não é o momento" },
];

export const REFUSE_REASONS = ["Não é comigo", "Fora das prioridades", "Duplicado", "Sem informação suficiente"];

const INITIAL_STATUS: Record<TMockKind, TMockStatus> = {
  action: "todo",
  decision: "proposed",
  risk: "identified",
  issue: "inbox",
};

export type TVerbInput = {
  note?: string;
  personId?: string;
  date?: string | null;
  followUp?: string | null;
  autonomy?: string;
  /** Concluding with evidence that is already attached to the item. */
  evidenceId?: string;
};

/** Demonstration scenarios: what the screens do while loading, on error, with partial data or read only. */
export type TScenario = "normal" | "loading" | "error" | "partial" | "readonly";

export type TDemo = {
  scenario: TScenario;
  /** The next batch capture loses its second line once, to show the partial failure and a clean retry. */
  failBatchLine: boolean;
  /** The next mitigation action fails once to be created, to show that the two proposals are independent. */
  failMitigation: boolean;
  /** The agent cannot run: reviewing risks reports it instead of inventing a result. */
  agentDown: boolean;
};

const DEMO_DEFAULTS: TDemo = { scenario: "normal", failBatchLine: false, failMitigation: false, agentDown: false };

export type TOnboardingOverride = Partial<Pick<TCaptureGuess, "kind" | "due" | "personIds" | "projectId">>;

export type TOnboardingResult = {
  status: "created" | "failed";
  where?: "item" | "inbox";
  id?: string;
  error?: string;
};

export type TOnboardingRow = { key: string; text: string; guess: TCaptureGuess; result?: TOnboardingResult };

type TOnboarding = {
  path: "vault" | "blank" | null;
  contextConfirmed: boolean;
  draft: string;
  overrides: Record<string, TOnboardingOverride>;
  results: Record<string, TOnboardingResult>;
  prefsSaved: boolean;
};

const freshOnboarding = (path: TOnboarding["path"] = null): TOnboarding => ({
  path,
  contextConfirmed: false,
  draft: "",
  overrides: {},
  results: {},
  prefsSaved: false,
});

let sequence = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${++sequence}`;
const lineKey = (text: string) => text.trim().toLowerCase().replace(/\s+/g, " ");

/** Local, in-memory state for the mockups. Nothing reaches the RADAR API, and nothing is sent to anyone. */
export class RadarMockupStore {
  meId = ME_ID;
  people: TMockPerson[] = structuredClone(MOCK_PEOPLE);
  projects: TMockProject[] = structuredClone(MOCK_PROJECTS);
  items: TMockItem[] = structuredClone(MOCK_ITEMS);
  inbox: TMockInboxEntry[] = structuredClone(MOCK_INBOX);
  references: TMockInboxEntry[] = [];
  weekResults: TMockWeekResult[] = structuredClone(MOCK_WEEK_RESULTS);
  feedback: { id: string; entryId: string; reason: string }[] = [];
  /** The pilot diary, written by the "O método está ajudando?" questions. */
  diary: { at: string; answers: string[] }[] = [];
  /** The one reference for date, time and zone. */
  now: TMockNow = { ...MOCK_NOW };
  /** Last time each ritual was completed: opening and closing the day, and the weekly review. */
  marks: TRitualMarks = { ...MOCK_RITUAL_MARKS };
  sinceDismissed = false;
  /** Today's focus belongs to a day: another day, another choice. */
  focus: { date: string | null; ids: string[] } = { date: null, ids: [] };
  tomorrowFirst: { id: string | null; on: string | null } = { id: null, on: null };
  ritual: "abrir" | "fechar" | null = null;
  openItemId: string | null = null;
  /** Verb to open in the item panel, when a row hands off to it. */
  pendingVerb: { key: TVerbKey; personId?: string } | null = null;
  captureOpen = false;
  /** "Comece com a sua semana real" (Guia §01): Hoje starts empty in the pilot. */
  firstUse = false;
  /** Preferences, not calendar entries: the mockup never books anything. */
  ritualTimes = { abrir: "08:30", fechar: "17:30", semanal: "sex 16:00" };
  onboarding: TOnboarding = freshOnboarding();
  /** Intent of each captured line → what it became, so a retry never creates the same thing twice. */
  intents: Record<string, { where: "item" | "inbox"; id: string }> = {};
  demo: TDemo = { ...DEMO_DEFAULTS };
  /** Writes the open item into the address bar; set by the shell. */
  private urlWriter: ((id: string | null) => void) | null = null;

  constructor(options: { now?: Partial<TMockNow> } = {}) {
    resetMockNow();
    setMockNow(options.now ?? {});
    this.now = { ...mockNow() };
    makeAutoObservable<RadarMockupStore, "urlWriter">(this, { urlWriter: false }, { autoBind: true });
  }

  // ------------------------------------------------------------ the clock

  /** Moves the single reference for date and time; every screen reads it from here. */
  setNow(patch: Partial<TMockNow>) {
    setMockNow(patch);
    this.now = { ...mockNow() };
  }

  get today() {
    return this.now.date;
  }

  private stamp() {
    return `${this.now.date}T${this.now.time}:00${this.now.tz}`;
  }

  // ------------------------------------------------------------ lookups

  person(id: string) {
    return this.people.find((person) => person.id === id);
  }

  personName(id: string) {
    if (id === "radar") return "RADAR";
    if (id === this.meId) return "você";
    return this.person(id)?.display_name ?? "alguém";
  }

  project(id: string | null) {
    return id ? this.projects.find((project) => project.id === id) : undefined;
  }

  item(id: string | null) {
    return id ? this.items.find((item) => item.id === id) : undefined;
  }

  get openItem() {
    return this.item(this.openItemId);
  }

  get readOnly() {
    return this.demo.scenario === "readonly";
  }

  /** False while Hoje cannot be trusted to list everything: it is loading, failed or came back partial. */
  get complete() {
    return this.demo.scenario === "normal" || this.demo.scenario === "readonly";
  }

  get hojeMine() {
    void this.now.date;
    return buildHoje(this.items, this.meId, this.personName);
  }

  get hojeTeam() {
    void this.now.date;
    return buildHoje(this.items, null, this.personName);
  }

  /** "Atenção": today's focus on top, then the alerts. The tab count is exactly the rows that need you. */
  get atencao() {
    const focusIds = this.focus.date === this.now.date ? this.focus.ids : [];
    const focused = focusIds.map((id) => this.item(id)).filter((item): item is TMockItem => !!item);
    const focusOpen = focused.filter((item) => isOpen(item.status));
    const focusDone = focused.filter((item) => !isOpen(item.status));
    const alerts = this.hojeMine.attention.filter((entry) => !focusIds.includes(entry.item.id));
    return { focusOpen, focusDone, alerts, count: focusOpen.length + alerts.length };
  }

  get focusItems() {
    return this.atencao.focusOpen.concat(this.atencao.focusDone);
  }

  /** Whether the item is one of today's focus: yesterday's focus does not count. */
  isFocus(id: string) {
    return this.focus.date === this.now.date && this.focus.ids.includes(id);
  }

  get hasFocusToday() {
    return this.focus.date === this.now.date && this.focus.ids.length > 0;
  }

  get visibleInbox() {
    void this.now.date;
    return this.inbox.filter((entry) => !entry.reviewOn || diffDays(entry.reviewOn) <= 0);
  }

  get scheduledInbox() {
    void this.now.date;
    return this.inbox.filter((entry) => entry.reviewOn && diffDays(entry.reviewOn) > 0);
  }

  get inboxCount() {
    return this.visibleInbox.length;
  }

  get closeDay() {
    void this.now.date;
    return closeDayQueue(this.items, this.meId);
  }

  /** The most recent review of any kind, for "Você não revisa desde…". */
  get lastReview() {
    return [this.marks.openedOn, this.marks.closedOn, this.marks.weeklyOn]
      .filter((date): date is string => !!date)
      .sort()
      .at(-1);
  }

  get since() {
    void this.now.date;
    return sinceLastReview(this.items, this.meId, this.lastReview ?? addDays(this.now.date, -7));
  }

  /** The ritual to offer now, from the preferred times and what was already done. */
  get ritualNow() {
    return ritualFor(this.now, this.ritualTimes, this.marks);
  }

  get tomorrowFirstItem() {
    return this.item(this.tomorrowFirst.id);
  }

  itemsOfProject(projectId: string) {
    return this.items.filter((item) => item.projectId === projectId);
  }

  // ------------------------------------------------------------ navigation state

  /** The shell registers how to write the open item into the URL; without it (tests) the store keeps it itself. */
  bindUrl(writer: ((id: string | null) => void) | null) {
    this.urlWriter = writer;
  }

  private requestOpen(id: string | null) {
    if (this.urlWriter) this.urlWriter(id);
    else this.syncOpenItem(id);
  }

  /** The URL is the source of truth for the open item: link, reload and Back all arrive here. */
  syncOpenItem(id: string | null) {
    if (this.openItemId === id) return;
    this.openItemId = id;
    if (!id) this.pendingVerb = null;
  }

  openItemById(id: string, verb?: { key: TVerbKey; personId?: string }) {
    this.pendingVerb = verb ?? null;
    this.requestOpen(id);
  }

  takePendingVerb() {
    const verb = this.pendingVerb;
    this.pendingVerb = null;
    return verb;
  }

  closeItem() {
    this.pendingVerb = null;
    this.requestOpen(null);
  }

  setCaptureOpen(open: boolean) {
    if (open && this.readOnly) return;
    this.captureOpen = open;
  }

  setRitual(ritual: "abrir" | "fechar" | null) {
    this.ritual = ritual;
  }

  dismissSince() {
    this.sinceDismissed = true;
  }

  // ------------------------------------------------------------ demonstration controls (never part of the product)

  setScenario(scenario: TScenario) {
    this.demo.scenario = scenario;
  }

  toggleDemo(flag: "failBatchLine" | "failMitigation" | "agentDown") {
    this.demo[flag] = !this.demo[flag];
  }

  /** Jump to the end of the day, or to the next morning, to show rituals and focus changing with the clock. */
  advanceClock(to: "evening" | "nextDay") {
    if (to === "evening") this.setNow({ time: this.ritualTimes.fechar });
    else this.setNow({ date: addDays(this.now.date, 1), time: this.ritualTimes.abrir });
  }

  // ------------------------------------------------------------ undo by effect: only what the action changed

  private undoState(): TUndoState {
    return structuredClone({
      collections: {
        items: toJS(this.items),
        inbox: toJS(this.inbox),
        references: toJS(this.references),
        weekResults: toJS(this.weekResults),
        feedback: toJS(this.feedback),
      },
      values: { focus: toJS(this.focus), tomorrowFirst: toJS(this.tomorrowFirst) },
    }) as unknown as TUndoState;
  }

  /**
   * Runs `change` and records what it did. `undo` reverses those effects only, against the state of that
   * moment: anything done afterwards, even on the same item, stays. `changed` is false when nothing happened.
   */
  track(change: () => void) {
    const before = this.undoState();
    change();
    const delta = diffStates(before, this.undoState());
    return { changed: !isEmptyDelta(delta), undo: () => this.undo(delta) };
  }

  undo(delta: TDelta) {
    const result = revertDelta(this.undoState(), delta, (collection, entity: TEntity) => {
      // The history is never erased: undoing is one more thing that happened.
      if (collection !== "items") return;
      const activity = Array.isArray(entity.activity) ? (entity.activity as TMockItem["activity"]) : [];
      entity.activity = [
        ...activity,
        { id: nextId("ac"), at: this.stamp(), actorId: this.meId, text: "desfez uma alteração" },
      ];
    });
    const { collections, values } = result.state;
    this.items = collections.items as unknown as TMockItem[];
    this.inbox = collections.inbox as unknown as TMockInboxEntry[];
    this.references = collections.references as unknown as TMockInboxEntry[];
    this.weekResults = collections.weekResults as unknown as TMockWeekResult[];
    this.feedback = collections.feedback as unknown as RadarMockupStore["feedback"];
    this.focus = values.focus as RadarMockupStore["focus"];
    this.tomorrowFirst = values.tomorrowFirst as RadarMockupStore["tomorrowFirst"];
    return { reverted: result.reverted, conflicts: result.conflicts };
  }

  // ------------------------------------------------------------ first use (Guia básico §01)

  /**
   * What the pilot sees on day one. With the vault: people and projects imported, nothing else. Without it:
   * only you. This is a demonstration control; in the product, starting only opens the onboarding and never
   * clears what already exists.
   */
  startFresh(options: { vault?: boolean } = {}) {
    const vault = options.vault ?? true;
    this.items = [];
    this.inbox = [];
    this.references = [];
    this.weekResults = [];
    this.feedback = [];
    this.focus = { date: null, ids: [] };
    this.tomorrowFirst = { id: null, on: null };
    this.marks = { openedOn: null, closedOn: null, weeklyOn: null };
    this.people = vault ? structuredClone(MOCK_PEOPLE) : structuredClone(MOCK_PEOPLE).filter((p) => p.id === this.meId);
    this.projects = vault ? structuredClone(MOCK_PROJECTS) : [];
    this.intents = {};
    this.onboarding = freshOnboarding(vault ? "vault" : "blank");
    this.sinceDismissed = true;
    this.firstUse = true;
    this.pendingVerb = null;
    this.requestOpen(null);
  }

  resetSample() {
    this.people = structuredClone(MOCK_PEOPLE);
    this.projects = structuredClone(MOCK_PROJECTS);
    this.items = structuredClone(MOCK_ITEMS);
    this.inbox = structuredClone(MOCK_INBOX);
    this.references = [];
    this.weekResults = structuredClone(MOCK_WEEK_RESULTS);
    this.feedback = [];
    this.focus = { date: null, ids: [] };
    this.tomorrowFirst = { id: null, on: null };
    this.marks = { ...MOCK_RITUAL_MARKS };
    this.intents = {};
    this.onboarding = freshOnboarding();
    this.demo = { ...DEMO_DEFAULTS };
    this.sinceDismissed = false;
    this.firstUse = false;
    resetMockNow();
    this.now = { ...mockNow() };
    this.pendingVerb = null;
    this.requestOpen(null);
  }

  finishFirstUse() {
    this.firstUse = false;
    // Choosing the week's results was the week's planning: the weekly review is not due on the first day.
    if (!this.marks.weeklyOn) this.marks.weeklyOn = this.now.date;
  }

  confirmContext() {
    this.onboarding.contextConfirmed = true;
  }

  /** Without a vault the context starts empty: projects and people are added by name, nothing is invented. */
  addProject(title: string) {
    const name = title.trim();
    if (!name) return;
    const identifier = name
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-zA-Z]/g, "")
      .slice(0, 3)
      .toUpperCase();
    this.projects.push({
      id: nextId("pr"),
      identifier: identifier || "PRJ",
      title: name,
      objective: "a confirmar",
      ownerId: this.meId,
      status: "active",
      due: null,
      keywords: name
        .toLowerCase()
        .split(/\s+/)
        .filter((word) => word.length > 3),
      result: { statement: name, criterion: "a confirmar" },
    });
  }

  addPerson(name: string, affiliation: TMockPerson["affiliation"], organization?: string) {
    const full = name.trim();
    if (!full) return;
    this.people.push({
      id: nextId("p"),
      name: full,
      display_name: full.split(/\s+/)[0],
      role: "a confirmar",
      affiliation,
      organization: organization?.trim() || undefined,
    });
  }

  addWeekResult(title: string, howWeKnow: string) {
    if (this.weekResults.length >= 3 || !title.trim()) return;
    this.weekResults.push({
      id: nextId("wr"),
      title: title.trim(),
      // Empty stays empty: "a confirmar" is shown as a gap, not filled with a guess.
      howWeKnow: howWeKnow.trim(),
      projectId: null,
      state: "open",
    });
  }

  setWeekResultHow(id: string, howWeKnow: string) {
    const result = this.weekResults.find((candidate) => candidate.id === id);
    if (result) result.howWeKnow = howWeKnow.trim();
  }

  removeWeekResult(id: string) {
    this.weekResults = this.weekResults.filter((result) => result.id !== id);
  }

  setRitualTime(ritual: "abrir" | "fechar" | "semanal", value: string) {
    this.ritualTimes[ritual] = value;
    this.onboarding.prefsSaved = false;
  }

  savePreferences() {
    this.onboarding.prefsSaved = true;
  }

  setDraft(text: string) {
    this.onboarding.draft = text;
  }

  /** The lines of the draft, each with what the RADAR guessed, what the manager corrected and how it went. */
  get onboardingRows(): TOnboardingRow[] {
    void this.now.date;
    const seen = new Set<string>();
    const rows: TOnboardingRow[] = [];
    this.onboarding.draft
      .split("\n")
      .map((line) => line.replace(/^[-•*]\s*/, "").trim())
      .filter(Boolean)
      .forEach((text) => {
        const key = lineKey(text);
        if (seen.has(key)) return;
        seen.add(key);
        const guess = {
          ...parseCapture(text, this.people, this.projects, this.meId),
          ...this.onboarding.overrides[key],
        };
        rows.push({ key, text, guess, result: this.onboarding.results[key] });
      });
    return rows;
  }

  correctRow(key: string, patch: TOnboardingOverride) {
    this.onboarding.overrides[key] = { ...this.onboarding.overrides[key], ...patch };
  }

  /**
   * Turns the draft lines into work, one by one. Each line has a stable intent: a line already created is
   * skipped, so retrying after a partial failure never duplicates anything. Returns what happened per line.
   */
  organizeDraft() {
    if (this.readOnly) return [];
    let attempted = 0;
    return this.onboardingRows.map((row) => {
      if (this.intents[row.key]) {
        this.onboarding.results[row.key] = { status: "created", ...this.intents[row.key] };
        return { key: row.key, ...this.onboarding.results[row.key] };
      }
      attempted += 1;
      if (this.demo.failBatchLine && attempted === 2) {
        this.demo.failBatchLine = false;
        this.onboarding.results[row.key] = {
          status: "failed",
          error: "Não foi possível criar agora. Nada foi criado; tente de novo sem medo de duplicar.",
        };
        return { key: row.key, ...this.onboarding.results[row.key] };
      }
      const created = this.capture(row.guess);
      this.intents[row.key] = created;
      this.onboarding.results[row.key] = { status: "created", ...created };
      return { key: row.key, ...this.onboarding.results[row.key] };
    });
  }

  /** Several pending items at once, one per line: each is captured, never turned into a form. */
  captureMany(text: string) {
    this.setDraft(text);
    return this.organizeDraft();
  }

  // ------------------------------------------------------------ inline edits (§10)

  private log(item: TMockItem, text: string, actorId = this.meId) {
    item.activity.push({ id: nextId("ac"), at: this.stamp(), actorId, text });
  }

  setPriority(id: string, priority: TMockPriority) {
    const item = this.item(id);
    if (item && !this.readOnly) item.priority = priority;
  }

  setDue(id: string, due: string | null) {
    const item = this.item(id);
    if (!item || item.due === due || this.readOnly) return;
    // Reassign rather than push: MobX stores an observable copy of a newly assigned array.
    if (item.due && due) item.previousDues = [...(item.previousDues ?? []), { from: item.due, to: due }];
    item.due = due;
    this.log(item, due ? `mudou o prazo para ${dayMonth(due)}` : "removeu o prazo");
  }

  /** Two sources disagree on the due date: the manager picks the one that stands. */
  resolveDueConflict(id: string, date: string) {
    const item = this.item(id);
    if (!item?.dueConflict || this.readOnly) return;
    const chosen = item.dueConflict.sources.find((source) => source.date === date);
    item.due = date;
    item.dueConflict = undefined;
    this.log(item, `resolveu a divergência de prazos: vale ${dayMonth(date)}${chosen ? ` (${chosen.label})` : ""}`);
  }

  setFollowUp(id: string, followUp: string | null) {
    const item = this.item(id);
    if (!item || this.readOnly) return;
    item.followUp = followUp;
    this.log(item, followUp ? `marcou o retorno para ${dayMonth(followUp)}` : "removeu o retorno");
  }

  setText(id: string, field: "deliverable" | "nextStep" | "autonomy" | "blockedReason", value: string) {
    const item = this.item(id);
    if (!item || this.readOnly) return;
    item[field] = value.trim() || undefined;
  }

  setOwner(id: string, personId: string) {
    const item = this.item(id);
    if (item && !this.readOnly) item.ownerId = personId;
  }

  setWith(id: string, personIds: string[]) {
    const item = this.item(id);
    if (!item || this.readOnly) return;
    const added = personIds.filter((personId) => !item.withIds.includes(personId));
    item.withIds = personIds;
    // A new executor has not agreed to anything yet.
    if (added.length) item.confirmation = { state: "pending" };
  }

  setInvolved(id: string, field: "consultIds" | "informIds", personIds: string[]) {
    const item = this.item(id);
    if (item && !this.readOnly) item[field] = personIds;
  }

  setProject(id: string, projectId: string | null) {
    const item = this.item(id);
    if (item && !this.readOnly) item.projectId = projectId;
  }

  /**
   * A change of state from the selector or the board. It follows the same rules as the buttons: it either
   * happens, or it is handed to the step it needs (evidence, reason, examination), or it is refused.
   */
  moveStatus(id: string, to: TMockStatus): TStatusMove {
    const item = this.item(id);
    if (!item) return { kind: "refused", reason: "Item não encontrado." };
    if (this.readOnly) return { kind: "refused", reason: "Seu acesso é somente leitura." };
    const move = statusMove(item, to);
    if (move.kind !== "direct") return move;
    if (move.via) this.run(id, move.via);
    else {
      item.status = to;
      this.log(item, `mudou o estado para ${STATUS_LABEL[to].toLowerCase()}`);
    }
    return move;
  }

  // ------------------------------------------------------------ business verbs (§11): one gesture, several effects

  private evidenceFor(note: string): TMockEvidence {
    return { id: nextId("ev"), label: note, addedBy: this.meId, at: this.stamp() };
  }

  private record(item: TMockItem, kind: TMockRecord["kind"], personId: string, note?: string) {
    item.records = [
      ...(item.records ?? []),
      { id: nextId("r"), kind, personId, by: this.meId, at: this.stamp(), ...(note ? { note } : {}) },
    ];
  }

  /** Returns false when the verb did not apply: the conditions were not met, or access is read only. */
  run(id: string, verb: TVerbKey, input: TVerbInput = {}): boolean {
    const item = this.item(id);
    if (!item || this.readOnly) return false;
    const note = input.note?.trim();
    switch (verb) {
      case "approve": {
        if (approvalBlockers(item, this.meId, this.people).length) return false;
        item.status = "decided";
        item.approval = undefined;
        this.log(item, note ? `aprovou: “${note}”` : "aprovou");
        this.items
          .filter((other) => other.dependsOnIds.includes(item.id))
          .forEach((other) => this.log(other, `decisão “${item.title}” aprovada`, "radar"));
        break;
      }
      case "send_back":
        // The Core has no "rejected" decision: sending it back keeps it proposed, with the reason.
        if (!note) return false;
        item.approval = { state: "returned", by: this.meId, at: this.stamp(), reason: note };
        this.log(item, `devolveu a proposta para ajuste: “${note}”`);
        break;
      case "request_approval": {
        if (!input.personId) return false;
        item.approval = { state: "requested", approverId: input.personId, requestedBy: this.meId, at: this.stamp() };
        this.log(item, `pediu a aprovação de ${this.personName(input.personId)}`);
        break;
      }
      case "attach_evidence":
        if (!note) return false;
        item.evidence = [...item.evidence, this.evidenceFor(note)];
        this.log(item, `anexou a evidência “${note}”`);
        break;
      case "complete": {
        // Concluding is recording valid evidence: new, or one already attached to the item.
        const existing = item.evidence.find((evidence) => evidence.id === input.evidenceId);
        if (!note && !existing) return false;
        if (note) item.evidence = [...item.evidence, this.evidenceFor(note)];
        item.outcome = note ?? existing?.label;
        item.status = item.kind === "risk" ? "closed" : "done";
        this.log(item, item.deliverable ? "concluiu conforme o combinado" : "concluiu");
        break;
      }
      case "start":
      case "resume":
      case "unblock":
        item.status = "in_progress";
        item.blockedReason = undefined;
        this.log(
          item,
          verb === "start" ? "iniciou" : verb === "resume" ? "retomou" : note ? `desbloqueou: “${note}”` : "desbloqueou"
        );
        break;
      case "postpone": {
        // With two sources for the date, postponing would pick a side silently: resolve first.
        if (item.dueConflict) return false;
        const to = input.date ?? nextMonday(item.due && item.due > this.now.date ? item.due : this.now.date);
        if (item.due) item.previousDues = [...(item.previousDues ?? []), { from: item.due, to, reason: note }];
        item.due = to;
        this.log(item, `adiou para ${dayMonth(to)}${note ? `: “${note}”` : ""}`);
        break;
      }
      case "delegate":
        if (!input.personId) return false;
        item.withIds = [input.personId];
        if (input.date !== undefined) item.due = input.date;
        item.followUp = input.followUp ?? suggestFollowUp(item.due);
        item.confirmation = { state: "pending" };
        if (input.autonomy?.trim()) item.autonomy = input.autonomy.trim();
        if (item.status === "todo") item.status = "in_progress";
        this.log(item, `delegou a ${this.personName(input.personId)}, retorno ${dayMonth(item.followUp)}`);
        break;
      case "nudge": {
        // A recorded fact: the manager says they followed up. The prepared message is copied separately.
        const personId = input.personId ?? item.withIds[0];
        item.followUp = addDays(this.now.date, 1);
        this.record(item, "nudge", personId, note);
        this.log(item, `registrou que cobrou ${this.personName(personId)}; novo retorno amanhã`);
        break;
      }
      case "confirm": {
        // Recorded by the manager: there is no channel for the executor to confirm yet, and it is not theirs to claim.
        const personId = input.personId ?? item.withIds[0];
        item.confirmation = { state: "confirmed", at: this.now.date, recordedBy: this.meId };
        this.record(item, "confirmation", personId, note);
        this.log(item, `registrou que ${this.person(personId)?.display_name ?? "o executor"} confirmou o combinado`);
        break;
      }
      case "block":
        item.status = "blocked";
        item.blockedReason = note || undefined;
        this.log(item, note ? `marcou como bloqueado: “${note}”` : "marcou como bloqueado");
        break;
      case "consult":
        if (!input.personId) return false;
        item.consultedIds = [...(item.consultedIds ?? []), input.personId];
        this.record(item, "consult", input.personId, note);
        this.log(item, `registrou que consultou ${this.personName(input.personId)}${note ? `: “${note}”` : ""}`);
        break;
      case "inform": {
        const targets = input.personId ? [input.personId] : pendingInforms(item);
        if (!targets.length) return false;
        item.informedIds = [...(item.informedIds ?? []), ...targets];
        targets.forEach((personId) => this.record(item, "inform", personId, note));
        this.log(item, `registrou que comunicou ${targets.map(this.personName).join(", ")}`);
        break;
      }
      case "ask":
        this.log(item, `pediu mais informações${note ? `: “${note}”` : ""}`);
        break;
      case "review":
        item.due = addDays(this.now.date, 7);
        this.log(item, note ? `revisou: “${note}”` : "revisou, sem mudanças");
        break;
      case "accept_risk":
        // Accepted is not closed: the risk keeps a follow-up date until someone closes it.
        item.status = "accepted";
        item.due = addDays(this.now.date, 30);
        this.log(item, note ? `aceitou o risco: “${note}”` : "aceitou o risco");
        break;
      case "mitigate": {
        const action = this.addItem({
          kind: "action",
          title: note || `Mitigar: ${item.title}`,
          projectId: item.projectId,
          due: addDays(this.now.date, 7),
          withIds: [],
        });
        if (item.status === "identified" || item.status === "monitoring") item.status = "mitigating";
        this.log(item, `criou a ação de mitigação “${action.title}”`);
        break;
      }
      case "decide":
        return false;
    }
    return true;
  }

  // ------------------------------------------------------------ rituals (Guia básico §05)

  setFocus(ids: string[]) {
    this.focus = { date: this.now.date, ids: ids.slice(0, 3) };
  }

  setTomorrowFirst(id: string | null) {
    this.tomorrowFirst = { id, on: this.now.date };
  }

  /** "Começar o dia": the day is opened, and the focus is for today only. */
  completeOpenDay(focusIds: string[]) {
    this.setFocus(focusIds);
    this.marks.openedOn = this.now.date;
  }

  completeCloseDay(tomorrowId: string | null) {
    this.setTomorrowFirst(tomorrowId);
    this.marks.closedOn = this.now.date;
  }

  saveWeeklyReview(input: {
    states: Record<string, TMockWeekResult["state"]>;
    next: { title: string; howWeKnow: string; projectId: string | null }[];
    answers: string[];
  }) {
    this.weekResults = input.next.slice(0, 3).map((result, index) => ({
      id: nextId(`wr${index}`),
      ...result,
      state: "open" as const,
    }));
    this.diary.push({ at: this.stamp(), answers: input.answers });
    this.marks.weeklyOn = this.now.date;
    this.sinceDismissed = true;
  }

  setWeekResultState(id: string, state: TMockWeekResult["state"]) {
    const result = this.weekResults.find((candidate) => candidate.id === id);
    if (result) result.state = state;
  }

  // ------------------------------------------------------------ capture and inbox (§8, §15, Guia §04)

  addItem(input: {
    kind: TMockKind;
    title: string;
    projectId: string | null;
    due: string | null;
    withIds: string[];
    riskScore?: number;
    context?: string;
    followUp?: string | null;
    priority?: TMockPriority;
  }) {
    const item: TMockItem = {
      id: nextId("it"),
      kind: input.kind,
      title: input.title,
      status: INITIAL_STATUS[input.kind],
      priority: input.priority ?? "medium",
      projectId: input.projectId,
      ownerId: this.meId,
      withIds: input.withIds,
      due: input.due,
      riskScore: input.riskScore,
      context: input.context ?? "",
      dependsOnIds: [],
      evidence: [],
      activity: [],
      followUp: input.withIds.length ? (input.followUp ?? suggestFollowUp(input.due)) : (input.followUp ?? null),
      confirmation: input.withIds.length ? { state: "pending" } : undefined,
      authorId: input.kind === "decision" ? this.meId : undefined,
    };
    this.log(item, "criou");
    this.items.push(item);
    // Return the observable copy MobX stored, so later mutations are tracked.
    return this.items[this.items.length - 1];
  }

  /** Recognized text becomes an item; anything else waits in the Inbox. */
  capture(guess: TCaptureGuess): { where: "item" | "inbox"; id: string } {
    if (guess.kind && guess.kind !== "issue") {
      const item = this.addItem({ ...guess, kind: guess.kind, withIds: guess.personIds });
      return { where: "item", id: item.id };
    }
    const entry: TMockInboxEntry = {
      id: nextId("in"),
      source: "captura",
      title: guess.title,
      detail: "agora",
      receivedAt: this.stamp(),
    };
    this.inbox.unshift(entry);
    return { where: "inbox", id: entry.id };
  }

  private takeEntry(entryId: string) {
    const entry = this.inbox.find((candidate) => candidate.id === entryId);
    this.inbox = this.inbox.filter((candidate) => candidate.id !== entryId);
    return entry;
  }

  /** "Intervir": grave impact in course; it becomes today's critical work. */
  intervene(entryId: string) {
    const entry = this.takeEntry(entryId);
    if (!entry) return;
    return this.addItem({
      kind: "action",
      title: entry.title,
      projectId: null,
      due: this.now.date,
      withIds: [],
      priority: "urgent",
    });
  }

  /** "Assumir": do it, delegate it, decide it, or treat it as a risk. */
  assume(entryId: string, as: "fazer" | "delegar" | "decidir" | "risco") {
    const entry = this.takeEntry(entryId);
    if (!entry) return;
    const kind: TMockKind = as === "decidir" ? "decision" : as === "risco" ? "risk" : "action";
    const item = this.addItem({ kind, title: entry.title, projectId: null, due: null, withIds: [] });
    this.openItemById(item.id, as === "delegar" ? { key: "delegate" } : undefined);
    return item;
  }

  scheduleEntry(entryId: string, date: string) {
    const entry = this.inbox.find((candidate) => candidate.id === entryId);
    if (entry) entry.reviewOn = date;
  }

  keepAsReference(entryId: string) {
    const entry = this.takeEntry(entryId);
    if (entry) this.references.push(entry);
  }

  refuse(entryId: string, reason: string) {
    if (this.takeEntry(entryId)) this.feedback.push({ id: nextId("fb"), entryId, reason });
  }

  /**
   * The agent's proposals are reviewed one by one: the link between existing objects and the mitigation
   * action are two decisions, so accepting both is two steps and one can fail while the other stands.
   */
  private suggestionOf(entryId: string): TMockSuggestion | undefined {
    return this.inbox.find((candidate) => candidate.id === entryId)?.suggestion;
  }

  private closeEntryIfResolved(entryId: string) {
    const suggestion = this.suggestionOf(entryId);
    if (!suggestion) return;
    const open = [suggestion.relation, suggestion.mitigation].filter(
      (part) => part && (part.state === "pending" || part.state === "failed")
    );
    if (!open.length) this.takeEntry(entryId);
  }

  acceptSuggestionPart(entryId: string, part: "relation" | "mitigation"): { ok: boolean; error?: string } {
    const suggestion = this.suggestionOf(entryId);
    if (!suggestion || this.readOnly) return { ok: false, error: "Sem permissão para decidir esta proposta." };
    if (part === "relation" && suggestion.relation) {
      const risk = this.item(suggestion.relation.riskId);
      if (!risk) {
        suggestion.relation.state = "failed";
        suggestion.relation.error = "O risco não existe mais.";
        return { ok: false, error: suggestion.relation.error };
      }
      risk.threatensIds = [...(risk.threatensIds ?? []), suggestion.relation.targetProjectId];
      this.log(
        risk,
        `aceitou a proposta do RADAR: o risco ameaça ${this.project(suggestion.relation.targetProjectId)?.title ?? "o projeto"}`
      );
      suggestion.relation.state = "accepted";
      suggestion.relation.error = undefined;
    }
    if (part === "mitigation" && suggestion.mitigation) {
      if (this.demo.failMitigation) {
        this.demo.failMitigation = false;
        suggestion.mitigation.state = "failed";
        suggestion.mitigation.error = "Não foi possível criar a ação agora. Nada foi criado; tente de novo.";
        return { ok: false, error: suggestion.mitigation.error };
      }
      this.addItem({
        kind: "action",
        title: suggestion.mitigation.title,
        projectId: suggestion.projectId,
        due: suggestion.mitigation.due,
        withIds: [suggestion.mitigation.withId],
      });
      suggestion.mitigation.state = "accepted";
      suggestion.mitigation.error = undefined;
      const risk = this.item(suggestion.relation?.riskId ?? null);
      if (risk && (risk.status === "identified" || risk.status === "monitoring")) risk.status = "mitigating";
    }
    this.closeEntryIfResolved(entryId);
    return { ok: true };
  }

  rejectSuggestionPart(entryId: string, part: "relation" | "mitigation", reason: TRejectReason) {
    const suggestion = this.suggestionOf(entryId);
    const target = part === "relation" ? suggestion?.relation : suggestion?.mitigation;
    if (!suggestion || !target || this.readOnly) return;
    target.state = "rejected";
    target.error = undefined;
    this.feedback.push({ id: nextId("fb"), entryId: `${entryId}:${part}`, reason });
    this.closeEntryIfResolved(entryId);
  }

  /** Editing a proposal creates a new version of it, kept with who edited and when. */
  editSuggestion(
    entryId: string,
    patch: { explanation?: string; mitigationTitle?: string; mitigationDue?: string; mitigationWithId?: string }
  ) {
    const suggestion = this.suggestionOf(entryId);
    if (!suggestion || this.readOnly) return;
    if (patch.explanation !== undefined) suggestion.explanation = patch.explanation.trim();
    if (suggestion.mitigation) {
      if (patch.mitigationTitle !== undefined) suggestion.mitigation.title = patch.mitigationTitle.trim();
      if (patch.mitigationDue !== undefined) suggestion.mitigation.due = patch.mitigationDue;
      if (patch.mitigationWithId !== undefined) suggestion.mitigation.withId = patch.mitigationWithId;
    }
    suggestion.version = (suggestion.version ?? 1) + 1;
    suggestion.editedAt = this.stamp();
  }

  ignoreEntry(entryId: string) {
    this.takeEntry(entryId);
  }

  // ------------------------------------------------------------ projects

  /** "Projeto travado" (Metodologia fluxo 3): the diagnosis becomes an unblocking combinado with owner and date. */
  unstallProject(projectId: string, cause: (typeof STALL_CAUSES)[number]["key"]) {
    const project = this.project(projectId);
    const label = STALL_CAUSES.find((candidate) => candidate.key === cause)?.label ?? "";
    if (!project || this.readOnly) return;
    const item = this.addItem({
      kind: "action",
      title: `Destravar ${project.title}: ${label.toLowerCase()}`,
      projectId,
      due: addDays(this.now.date, 2),
      withIds: [],
      priority: "high",
    });
    item.nextStep = "Definir quem resolve e até quando";
    return item;
  }

  /**
   * Mock agent run on a project's risks (§16): it proposes linking a risk to another project, which lands in
   * the Inbox for review. With the agent unavailable it says so instead of producing a result.
   */
  reviewProjectRisks(projectId: string): { ok: boolean; error?: string } {
    const project = this.project(projectId);
    if (!project || this.readOnly) return { ok: false, error: "Sem permissão para pedir a revisão." };
    if (this.demo.agentDown)
      return { ok: false, error: "O agente não está disponível agora. Nenhuma revisão foi feita." };
    const open = this.itemsOfProject(projectId).filter((item) => isOpen(item.status));
    const risk = open.filter((item) => item.kind === "risk").sort((a, b) => (b.riskScore ?? 0) - (a.riskScore ?? 0))[0];
    const target = this.projects.find((other) => other.id !== projectId && other.status === "active");
    if (!risk || !target) return { ok: false, error: "Não há risco aberto neste projeto para propor uma ligação." };
    this.inbox.unshift({
      id: nextId("in"),
      source: "agente",
      title: `Ligar o risco “${risk.title}” ao projeto ${target.title}`,
      detail: `RADAR leu ${open.length} itens abertos de ${project.title} · agora`,
      receivedAt: this.stamp(),
      suggestion: {
        type: "relation",
        kind: "risk",
        title: `${risk.title} ameaça ${target.title}`,
        projectId: target.id,
        ownerId: this.meId,
        due: null,
        explanation: `${open.filter((item) => item.withIds.length).length} dos itens abertos de ${project.title} dependem da mesma pessoa, e ${target.title} usa o mesmo time.`,
        confidence: 0.64,
        version: 1,
        evidence: [{ label: risk.title, source: `Risco aberto em ${project.title}` }],
        relation: { riskId: risk.id, targetProjectId: target.id, state: "pending" },
      },
    });
    return { ok: true };
  }
}
