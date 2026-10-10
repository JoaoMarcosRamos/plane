/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import type {
  TMockItem,
  TMockKind,
  TMockNow,
  TMockPerson,
  TMockPriority,
  TMockProject,
  TMockResult,
  TMockStatus,
} from "./mock-data";
import { currentToday } from "./mock-data";

/**
 * A sketch of the Interaction Model (RADAR_UX_VIEW §3) speaking the Guia básico do gestor: combinados,
 * retornos, the seven states and the five relational views of the Metodologia. Pure functions, so the
 * mock screens and the tests share them.
 */

// ---------------------------------------------------------------- dates (date-only, no timezone shifts)

const dayNumber = (iso: string) => {
  const [year, month, day] = iso.split("-").map(Number);
  return Math.round(Date.UTC(year, month - 1, day) / 86_400_000);
};

const fromDayNumber = (value: number) => new Date(value * 86_400_000).toISOString().slice(0, 10);

export const diffDays = (iso: string, from: string = currentToday()) => dayNumber(iso) - dayNumber(from);

export const addDays = (iso: string, days: number) => fromDayNumber(dayNumber(iso) + days);

/** 0 = domingo … 6 = sábado. */
export const weekday = (iso: string) => new Date(dayNumber(iso) * 86_400_000).getUTCDay();

/** The next Monday strictly after `base`. */
export const nextMonday = (base: string = currentToday()) => addDays(base, (8 - weekday(base)) % 7 || 7);

/** The next Friday strictly after `base`. */
export const nextFriday = (base: string = currentToday()) => addDays(base, (12 - weekday(base)) % 7 || 7);

const WEEKDAYS_SHORT = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export const shortDate = (iso: string) => {
  const [, month, day] = iso.split("-").map(Number);
  return `${day} ${MONTHS_SHORT[month - 1]}`;
};

/** "06/10". */
export const dayMonth = (iso: string) => iso.slice(8, 10) + "/" + iso.slice(5, 7);

export const toLocalDate = (iso: string | null | undefined) => {
  if (!iso) return null;
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
};

export const fromLocalDate = (date: Date | null) =>
  date
    ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
    : null;

export type TDueTone = "late" | "soon" | "normal" | "none";

/** "há 2 dias", "hoje", "amanhã", "sex", "20 out". */
export function relativeDue(
  due: string | null | undefined,
  today: string = currentToday()
): { label: string; tone: TDueTone } {
  if (!due) return { label: "sem prazo", tone: "none" };
  const diff = diffDays(due, today);
  if (diff < 0) return { label: diff === -1 ? "ontem" : `há ${-diff} dias`, tone: "late" };
  if (diff === 0) return { label: "hoje", tone: "soon" };
  if (diff === 1) return { label: "amanhã", tone: "soon" };
  if (diff < 7) return { label: WEEKDAYS_SHORT[weekday(due)], tone: "normal" };
  return { label: shortDate(due), tone: "normal" };
}

// ---------------------------------------------------------------- vocabulary (Guia básico §03)

export const KIND_LABEL: Record<TMockKind, string> = {
  action: "Combinado",
  decision: "Decisão",
  risk: "Risco",
  issue: "Entrada",
};

/** The seven states of the guide for work; decisions and risks keep their own words. */
export const STATUS_LABEL: Record<TMockStatus, string> = {
  inbox: "Entrada",
  todo: "Planejado",
  in_progress: "Em andamento",
  waiting: "Aguardando",
  blocked: "Bloqueado",
  done: "Concluído",
  cancelled: "Cancelado",
  proposed: "Aguardando decisão",
  decided: "Aprovada",
  identified: "Identificado",
  monitoring: "Monitorando",
  mitigating: "Mitigando",
  accepted: "Aceito",
  closed: "Encerrado",
};

export const STATUSES_BY_KIND: Record<TMockKind, TMockStatus[]> = {
  action: ["todo", "in_progress", "waiting", "blocked", "done", "cancelled"],
  decision: ["proposed", "decided"],
  risk: ["identified", "monitoring", "mitigating", "accepted", "closed"],
  issue: ["inbox", "cancelled"],
};

/**
 * Closed for the work queue. A risk that was accepted is NOT closed: it is still followed up until someone
 * closes it, so it stays in every list that shows open items.
 */
const CLOSED = new Set<TMockStatus>(["done", "cancelled", "decided", "closed"]);

export const isOpen = (status: TMockStatus) => !CLOSED.has(status);

/** Plane's state groups, so the stock StateGroupIcon and StateSelect render RADAR statuses. */
export type TStateGroup = "backlog" | "unstarted" | "started" | "completed" | "cancelled";

export const STATE_GROUP: Record<TMockStatus, TStateGroup> = {
  inbox: "backlog",
  todo: "unstarted",
  proposed: "unstarted",
  identified: "unstarted",
  in_progress: "started",
  waiting: "started",
  blocked: "started",
  monitoring: "started",
  mitigating: "started",
  done: "completed",
  decided: "completed",
  accepted: "started",
  closed: "completed",
  cancelled: "cancelled",
};

export const STATE_COLOR: Record<TStateGroup, string> = {
  backlog: "#a3a3a3",
  unstarted: "#3a3a3a",
  started: "#f59e0b",
  completed: "#16a34a",
  cancelled: "#ef4444",
};

export const statusColor = (status: TMockStatus) =>
  status === "blocked" ? "#dc2626" : STATE_COLOR[STATE_GROUP[status]];

export const PRIORITY_LABEL: Record<TMockPriority, string> = {
  urgent: "Crítica",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
  none: "Sem prioridade",
};

// ---------------------------------------------------------------- people around an item (Metodologia §05)

/** Who executes: the delegated people, else the owner. */
export const executorsOf = (item: TMockItem) => (item.withIds.length ? item.withIds : [item.ownerId]);

export const involves = (item: TMockItem, personId: string) =>
  item.ownerId === personId || item.withIds.includes(personId);

/** Owned by me but in someone else's hands. */
export const waitingOnOthers = (item: TMockItem, meId: string) =>
  item.ownerId === meId && item.withIds.length > 0 && !item.withIds.includes(meId);

export const pendingConsults = (item: TMockItem) =>
  (item.consultIds ?? []).filter((id) => !(item.consultedIds ?? []).includes(id));

export const pendingInforms = (item: TMockItem) =>
  (item.informIds ?? []).filter((id) => !(item.informedIds ?? []).includes(id));

// ---------------------------------------------------------------- signals the guide asks for

/** Days since the executors last said anything on a delegated item: "sem notícias", never "em andamento". */
export function silentDays(item: TMockItem, meId: string, today: string = currentToday()): number | null {
  if (item.kind !== "action" || !isOpen(item.status) || !waitingOnOthers(item, meId)) return null;
  // The silence is the executors': an edit by the manager never counts as news from them. Without any word
  // from them yet, the clock starts when the item was handed over (the oldest record).
  const fromThem = item.activity
    .filter((entry) => item.withIds.includes(entry.actorId))
    .map((entry) => entry.at.slice(0, 10));
  const sorted = [...fromThem].sort();
  const handedOver = item.activity.map((entry) => entry.at.slice(0, 10)).sort()[0];
  const last = sorted.length ? sorted[sorted.length - 1] : handedOver;
  if (!last) return null;
  const days = -diffDays(last, today);
  return days >= 3 ? days : null;
}

/** The return date (retorno), which is not the due date (prazo). */
export function followUpState(item: TMockItem, today: string = currentToday()) {
  if (!item.followUp || !isOpen(item.status)) return null;
  const diff = diffDays(item.followUp, today);
  if (diff < 0) return { label: `retorno venceu em ${dayMonth(item.followUp)}`, tone: "late" as const };
  if (diff === 0) return { label: "retorno hoje", tone: "soon" as const };
  return { label: `retorno ${relativeDue(item.followUp, today).label}`, tone: "normal" as const };
}

/** Return suggested when delegating: half way to the due date, on a weekday (law 5). */
export function suggestFollowUp(due: string | null | undefined, today: string = currentToday()) {
  const shift = (iso: string) => (weekday(iso) === 6 ? addDays(iso, -1) : weekday(iso) === 0 ? addDays(iso, 1) : iso);
  if (!due) return shift(addDays(today, 3));
  const diff = diffDays(due, today);
  if (diff <= 1) return diff < 0 ? addDays(today, 1) : due;
  return shift(addDays(today, Math.ceil(diff / 2)));
}

/** Gaps in a combinado. Shown as "a confirmar"; they never block saving. */
export function gapsOf(item: TMockItem) {
  if (item.kind !== "action" || !isOpen(item.status)) return [];
  const gaps: string[] = [];
  if (!item.deliverable) gaps.push("entrega");
  if (!item.nextStep) gaps.push("próxima ação");
  if (!item.due) gaps.push("prazo");
  if (item.withIds.length && !item.followUp) gaps.push("retorno");
  return gaps;
}

// ---------------------------------------------------------------- attention

export type TSeverity = "critical" | "warning" | "neutral";

export type TAttention = { item: TMockItem; severity: TSeverity; reason: string };

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

/** Why an open item deserves attention now, or null. Business language only. */
export function attentionFor(
  item: TMockItem,
  items: TMockItem[],
  personName: (id: string) => string
): TAttention | null {
  if (!isOpen(item.status) || item.kind === "issue") return null;
  const diff = item.due ? diffDays(item.due) : null;
  if (item.kind === "decision") {
    // A decision without a date is still a decision waiting for you: it never leaves the queue for lack of one.
    if (diff === null) return { item, severity: "warning", reason: "Decisão necessária · Prazo a definir" };
    if (diff > 7) return null;
    const when =
      diff < 0 ? "vencida" : diff === 0 ? "vence hoje" : diff === 1 ? "vence amanhã" : `vence em ${diff} dias`;
    return { item, severity: diff <= 1 ? "critical" : "warning", reason: `Decisão necessária · ${when}` };
  }
  if (item.kind === "risk") {
    const score = item.riskScore ?? 0;
    const reviewLate = diff !== null && diff < 0;
    const accepted = item.status === "accepted";
    const followUpSoon = accepted && diff !== null && diff <= 7;
    if (score < 15 && !reviewLate && !followUpSoon) return null;
    const parts = [
      accepted
        ? `Risco aceito${score ? ` (${score})` : ""}`
        : score >= 15
          ? `Risco ${score >= 20 ? "muito alto" : "alto"} (${score})`
          : `Risco ${score}`,
    ];
    if (reviewLate) parts.push(`${accepted ? "acompanhamento" : "revisão"} vencido há ${plural(-diff, "dia", "dias")}`);
    else if (followUpSoon && item.due) parts.push(`acompanhar até ${dayMonth(item.due)}`);
    return {
      item,
      severity: score >= 20 ? "critical" : accepted && !reviewLate ? "neutral" : "warning",
      reason: parts.join(" · "),
    };
  }
  if (item.dueConflict && !(diff !== null && diff < 0)) {
    const dates = item.dueConflict.sources.map((source) => dayMonth(source.date)).join(" × ");
    return { item, severity: "warning", reason: `Prazos divergentes · ${dates}` };
  }
  if (diff !== null && diff < 0) {
    const others = item.withIds.map(personName);
    const late = `Atrasado há ${plural(-diff, "dia", "dias")}`;
    return { item, severity: "critical", reason: others.length ? `${late} · com ${others.join(", ")}` : late };
  }
  if (item.status === "blocked")
    return { item, severity: "warning", reason: `Bloqueado · ${item.blockedReason ?? "motivo a confirmar"}` };
  if (item.followUp && diffDays(item.followUp) < 0 && item.withIds.length)
    return {
      item,
      severity: "warning",
      reason: `Retorno venceu em ${dayMonth(item.followUp)} sem resposta de ${item.withIds.map(personName).join(", ")}`,
    };
  const blocker = items.find(
    (other) => item.dependsOnIds.includes(other.id) && isOpen(other.status) && other.due && diffDays(other.due) < 0
  );
  if (blocker) return { item, severity: "warning", reason: `Travado por “${blocker.title}”` };
  return null;
}

const SEVERITY_ORDER: Record<TSeverity, number> = { critical: 0, warning: 1, neutral: 2 };

export const byUrgency = (a: TAttention, b: TAttention) =>
  SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
  (a.item.due ?? "9999").localeCompare(b.item.due ?? "9999") ||
  a.item.title.localeCompare(b.item.title);

const byDue = (a: TMockItem, b: TMockItem) => (a.due ?? "9999").localeCompare(b.due ?? "9999");
const byFollowUp = (a: TMockItem, b: TMockItem) =>
  (a.followUp ?? a.due ?? "9999").localeCompare(b.followUp ?? b.due ?? "9999");

// ---------------------------------------------------------------- the five relational views (Metodologia §05)

export type TRelational = "fazer" | "decidir" | "consultar" | "aguardando" | "informar";

export const RELATIONAL: { key: TRelational; label: string; hint: string }[] = [
  { key: "fazer", label: "Fazer", hint: "Combinados em que você executa." },
  { key: "decidir", label: "Decidir", hint: "Decisões sob sua responsabilidade." },
  { key: "consultar", label: "Consultar", hint: "Quem precisa ser ouvido antes de você decidir ou concluir." },
  { key: "aguardando", label: "Aguardando", hint: "Entregas de outras pessoas, com o retorno combinado." },
  {
    key: "informar",
    label: "Informar",
    hint: "Decisões e entregas que ainda não foram comunicadas a quem precisa saber.",
  },
];

export function relationalViews(items: TMockItem[], meId: string): Record<TRelational, TMockItem[]> {
  const open = items.filter((item) => isOpen(item.status) && item.kind !== "issue");
  const mine = (item: TMockItem) => item.ownerId === meId;
  return {
    fazer: open
      .filter((item) => item.kind === "action" && item.status !== "waiting" && executorsOf(item).includes(meId))
      .sort(byDue),
    decidir: open.filter((item) => item.kind === "decision" && mine(item)).sort(byDue),
    consultar: open.filter((item) => mine(item) && pendingConsults(item).length > 0).sort(byDue),
    aguardando: open
      .filter(
        (item) => item.kind === "action" && mine(item) && (waitingOnOthers(item, meId) || item.status === "waiting")
      )
      .sort(byFollowUp),
    informar: items.filter((item) => mine(item) && !isOpen(item.status) && pendingInforms(item).length > 0),
  };
}

/** Bucket by when it is due: today (or late), this week, later. */
export function byWhen(items: TMockItem[], today: string = currentToday()) {
  const endOfWeek = addDays(today, 7 - weekday(today));
  return {
    today: items.filter((item) => item.due && diffDays(item.due, today) <= 0),
    week: items.filter((item) => item.due && diffDays(item.due, today) > 0 && item.due <= endOfWeek),
    later: items.filter((item) => !item.due || item.due > endOfWeek),
  };
}

export type THoje = { attention: TAttention[]; views: Record<TRelational, TMockItem[]> | null };

/** "Hoje" for one person (§5, §14), or the whole team when `meId` is null. */
export function buildHoje(items: TMockItem[], meId: string | null, personName: (id: string) => string): THoje {
  const scoped = meId ? items.filter((item) => involves(item, meId)) : items;
  const attention = scoped
    .map((item) => attentionFor(item, items, personName))
    .filter((entry): entry is TAttention => !!entry)
    .sort(byUrgency);
  return { attention, views: meId ? relationalViews(items, meId) : null };
}

// ---------------------------------------------------------------- rituals (Guia básico §05)

/** "Fechar o dia": what expired, stalled or went silent today, one at a time. */
export function closeDayQueue(items: TMockItem[], meId: string, today: string = currentToday()) {
  return items
    .filter((item) => isOpen(item.status) && item.kind === "action" && involves(item, meId))
    .map((item) => {
      const silent = silentDays(item, meId, today);
      const reason =
        item.due && diffDays(item.due, today) < 0
          ? `Venceu ${relativeDue(item.due, today).label}`
          : item.due && diffDays(item.due, today) === 0
            ? "Vence hoje"
            : item.followUp && diffDays(item.followUp, today) <= 0
              ? diffDays(item.followUp, today) === 0
                ? "Retorno combinado para hoje"
                : `Retorno venceu em ${dayMonth(item.followUp)}`
              : item.status === "blocked"
                ? `Bloqueado · ${item.blockedReason ?? "motivo a confirmar"}`
                : silent
                  ? `Sem notícias há ${silent} dias`
                  : null;
      return reason ? { item, reason } : null;
    })
    .filter((entry): entry is { item: TMockItem; reason: string } => !!entry)
    .sort((a, b) => byDue(a.item, b.item));
}

/** "Fiquei alguns dias sem usar": what changed since the last review. */
export function sinceLastReview(items: TMockItem[], meId: string, lastReview: string, today: string = currentToday()) {
  const open = items.filter((item) => isOpen(item.status) && involves(item, meId));
  return {
    expired: open.filter((item) => item.due && item.due >= lastReview && diffDays(item.due, today) < 0),
    silent: open.filter((item) => silentDays(item, meId, today)),
    fromOthers: items.filter((item) =>
      item.activity.some((entry) => entry.actorId !== meId && entry.at.slice(0, 10) > lastReview)
    ),
  };
}

// ---------------------------------------------------------------- business verbs (§11)

export type TVerbKey =
  | "decide"
  | "approve"
  | "send_back"
  | "request_approval"
  | "attach_evidence"
  | "postpone"
  | "ask"
  | "complete"
  | "start"
  | "delegate"
  | "nudge"
  | "confirm"
  | "resume"
  | "block"
  | "unblock"
  | "consult"
  | "inform"
  | "review"
  | "mitigate"
  | "accept_risk";

export type TVerb = { key: TVerbKey; label: string; personId?: string };

/**
 * What the Undo toast may offer. Only changes whose reverse is a legitimate act: dates, delegation, a review
 * date, a mitigation action, a pending approval request. Conclusion, approval, state changes and recorded facts
 * are not taken back (they are corrected with a new record), and copying a message changes nothing to undo.
 */
const REVERSIBLE_VERBS = new Set<TVerbKey>(["postpone", "delegate", "review", "mitigate", "request_approval"]);

export const isReversible = (key: TVerbKey) => REVERSIBLE_VERBS.has(key);

/** The verbs a manager would use on this item, most likely first. */
export function verbsFor(item: TMockItem, meId: string, personName: (id: string) => string): TVerb[] {
  const informs = pendingInforms(item);
  const inform: TVerb[] = informs.length ? [{ key: "inform", label: "Comunicar", personId: informs[0] }] : [];
  // Closed work is not reopened: the contract has no way back, so only the pending communication remains.
  if (!isOpen(item.status)) return inform;
  const other = item.withIds.find((id) => id !== meId);
  const nudge: TVerb[] = other ? [{ key: "nudge", label: `Cobrar ${personName(other)}`, personId: other }] : [];
  const confirm: TVerb[] =
    other && item.confirmation?.state === "pending"
      ? [{ key: "confirm", label: "Registrar confirmação", personId: other }]
      : [];
  switch (item.kind) {
    case "decision": {
      const consult = pendingConsults(item).map(
        (id): TVerb => ({ key: "consult", label: `Consultar ${personName(id)}`, personId: id })
      );
      // One verb on the row and in the panel: "Decidir" opens the examination, with its conditions.
      return [
        { key: "decide", label: "Decidir" },
        ...consult,
        { key: "postpone", label: "Adiar" },
        { key: "ask", label: "Pedir informação" },
      ];
    }
    case "risk":
      return item.status === "accepted"
        ? [
            { key: "review", label: "Revisar" },
            { key: "mitigate", label: "Criar ação de mitigação" },
            { key: "complete", label: "Encerrar o risco" },
          ]
        : [
            { key: "review", label: "Revisar" },
            { key: "mitigate", label: "Criar ação de mitigação" },
            { key: "accept_risk", label: "Aceitar o risco" },
          ];
    case "action": {
      const late = !!item.due && diffDays(item.due) < 0;
      if (item.status === "blocked")
        return [{ key: "unblock", label: "Desbloquear" }, ...nudge, { key: "postpone", label: "Adiar" }];
      if (item.status === "waiting")
        return [...nudge, ...confirm, { key: "resume", label: "Retomar" }, { key: "postpone", label: "Adiar" }];
      if (other && waitingOnOthers(item, meId))
        return late || followUpState(item)?.tone === "late"
          ? [
              ...nudge,
              ...confirm,
              { key: "complete", label: "Concluir" },
              { key: "postpone", label: "Adiar" },
              { key: "block", label: "Marcar bloqueio" },
            ]
          : [
              ...confirm,
              { key: "complete", label: "Concluir" },
              ...nudge,
              { key: "postpone", label: "Adiar" },
              { key: "block", label: "Marcar bloqueio" },
            ];
      return [
        { key: "complete", label: "Concluir" },
        ...(item.status === "todo" ? [{ key: "start" as const, label: "Iniciar" }] : []),
        { key: "delegate", label: "Delegar" },
        { key: "postpone", label: "Adiar" },
        { key: "block", label: "Marcar bloqueio" },
      ];
    }
    default:
      return [];
  }
}

export const primaryVerb = (item: TMockItem, meId: string, personName: (id: string) => string): TVerb | undefined =>
  verbsFor(item, meId, personName)[0];

// ---------------------------------------------------------------- what stands between a decision and its approval

export type TApprovalBlocker = {
  key: "proposal" | "evidence" | "author" | "permission" | "pending";
  text: string;
  /** What the manager can do about it right here, when anything. */
  fix?: "attach_evidence" | "request_approval";
};

const authorOf = (item: TMockItem) => item.authorId ?? item.ownerId;

/** People who may approve this decision: allowed to approve and not its author. */
export const approversOf = (item: TMockItem, people: TMockPerson[]) =>
  people.filter((person) => person.canApprove && person.id !== authorOf(item));

/**
 * Conditions to approve, in the manager's words: a complete proposal, evidence, someone other than the author,
 * a person allowed to approve. An empty list means the manager may approve now.
 */
export function approvalBlockers(item: TMockItem, meId: string, people: TMockPerson[]): TApprovalBlocker[] {
  if (item.kind !== "decision" || !isOpen(item.status)) return [];
  const blockers: TApprovalBlocker[] = [];
  if (!item.proposal?.rationale.trim() || !item.context.trim())
    blockers.push({ key: "proposal", text: "Falta a proposta completa: contexto, decisão e justificativa." });
  if (!item.evidence.length)
    blockers.push({ key: "evidence", text: "Falta ao menos uma evidência anexada.", fix: "attach_evidence" });
  const me = people.find((person) => person.id === meId);
  if (authorOf(item) === meId)
    blockers.push({
      key: "author",
      text: "Você é o autor desta proposta. Quem aprova precisa ser outra pessoa habilitada.",
      fix: "request_approval",
    });
  else if (!me?.canApprove) blockers.push({ key: "permission", text: "Seu perfil não aprova decisões." });
  const request = item.approval?.state === "requested" ? item.approval : null;
  if (request && request.approverId !== meId) {
    const approver = people.find((person) => person.id === request.approverId)?.display_name ?? "outra pessoa";
    blockers.push({
      key: "pending",
      text: `Aprovação pendente de ${approver} desde ${dayMonth(request.at.slice(0, 10))}.`,
    });
  }
  return blockers;
}

// ---------------------------------------------------------------- status changes follow the same rules as the buttons

export type TStatusMove =
  | { kind: "same" }
  | { kind: "direct"; via?: TVerbKey }
  /** Needs its own step (evidence, reason, examination): the selector and the board hand it to the panel. */
  | { kind: "flow"; via: TVerbKey; note: string }
  | { kind: "refused"; reason: string };

const TERMINAL_REASON: Partial<Record<TMockKind, string>> = {
  action: "Um combinado concluído não é reaberto. Registre um novo combinado para o que faltou.",
  decision: "Uma decisão aprovada não volta a ser proposta. Para mudá-la, registre uma nova decisão.",
  risk: "Um risco encerrado não é reaberto. Registre um novo risco, se voltar a existir.",
};

/**
 * Whether an item may go from its status to another, and how. The status selector and the board's drag and
 * drop ask this instead of writing a status: moving to Concluído needs evidence, Bloqueado needs a reason,
 * and nothing is reopened.
 */
export function statusMove(item: TMockItem, to: TMockStatus): TStatusMove {
  const from = item.status;
  if (from === to) return { kind: "same" };
  if (!isOpen(from)) return { kind: "refused", reason: TERMINAL_REASON[item.kind] ?? "Este item já está fechado." };
  if (item.kind === "decision") {
    if (to === "decided") return { kind: "flow", via: "decide", note: "Decidir pede as condições da aprovação." };
    return { kind: "refused", reason: "Uma decisão só sai de Aguardando decisão quando é aprovada." };
  }
  if (item.kind === "risk") {
    if (to === "accepted") return { kind: "flow", via: "accept_risk", note: "Aceitar um risco pede o motivo." };
    if (to === "closed") return { kind: "flow", via: "complete", note: "Encerrar um risco pede a evidência." };
    if (["identified", "monitoring", "mitigating"].includes(to)) return { kind: "direct" };
    return { kind: "refused", reason: "Este estado não se aplica a um risco." };
  }
  if (item.kind !== "action") return { kind: "refused", reason: "Este item não muda de estado aqui." };
  switch (to) {
    case "done":
      return { kind: "flow", via: "complete", note: "Concluir pede a evidência que comprova a entrega." };
    case "blocked":
      return { kind: "flow", via: "block", note: "Marcar bloqueio pede o que impede avançar." };
    case "in_progress":
      return from === "blocked"
        ? { kind: "flow", via: "unblock", note: "Desbloquear pede o que destravou." }
        : from === "waiting"
          ? { kind: "direct", via: "resume" }
          : { kind: "direct", via: "start" };
    case "waiting":
      return item.withIds.length
        ? { kind: "direct" }
        : { kind: "refused", reason: "Aguardando exige alguém executando. Delegue o combinado primeiro." };
    case "todo":
      return { kind: "refused", reason: "Uma ação iniciada não volta para Planejado. Use Adiar ou Marcar bloqueio." };
    case "cancelled":
      return { kind: "refused", reason: "Cancelar não está disponível para combinados." };
    default:
      return { kind: "refused", reason: "Este estado não se aplica a um combinado." };
  }
}

// ---------------------------------------------------------------- which ritual fits now (Guia básico §05)

export type TRitual = "abrir" | "fechar" | "revisao";

/** Preferred times, as chosen in the first use: "08:30", "17:30" and "sex 16:00". */
export type TRitualPrefs = { abrir: string; fechar: string; semanal: string };

/** The last date each ritual was completed. A ritual done in its period is no longer pending. */
export type TRitualMarks = { openedOn: string | null; closedOn: string | null; weeklyOn: string | null };

const minutesOf = (time: string) => {
  const match = /(\d{1,2}):(\d{2})/.exec(time);
  return match ? Number(match[1]) * 60 + Number(match[2]) : 0;
};

export function parseWeekly(value: string) {
  const match = /^([a-zç]{3})\s+(\d{1,2}:\d{2})$/i.exec(value.trim());
  const day = match ? WEEKDAYS_SHORT.indexOf(match[1].toLowerCase()) : -1;
  return { weekday: day < 0 ? 5 : day, minutes: minutesOf(match?.[2] ?? "16:00") };
}

/** The Monday that starts the week of `iso`. */
export const mondayOf = (iso: string) => addDays(iso, -((weekday(iso) + 6) % 7));

/**
 * The one ritual to offer now. Opening is offered from the chosen time until the closing time, closing from
 * then on, and the weekly review once its slot arrives in a week with no review. Each stops being offered
 * after it is completed in its own period (the day, or the week).
 */
export function ritualFor(
  now: Pick<TMockNow, "date" | "time">,
  prefs: TRitualPrefs,
  marks: TRitualMarks
): { now: TRitual | null; reviewDue: boolean; weeklyDoneOn: string | null } {
  const today = now.date;
  const minutes = minutesOf(now.time);
  const slot = parseWeekly(prefs.semanal);
  const weekStart = mondayOf(today);
  const slotDate = addDays(weekStart, (slot.weekday + 6) % 7);
  const slotArrived = today > slotDate || (today === slotDate && minutes >= slot.minutes);
  const weeklyDone = !!marks.weeklyOn && marks.weeklyOn >= weekStart;
  const missedLastWeek = !marks.weeklyOn || marks.weeklyOn < addDays(weekStart, -7);
  const reviewDue = !weeklyDone && (slotArrived || missedLastWeek);
  const daily: TRitual | null =
    minutes >= minutesOf(prefs.fechar)
      ? marks.closedOn === today
        ? null
        : "fechar"
      : minutes >= minutesOf(prefs.abrir)
        ? marks.openedOn === today
          ? null
          : "abrir"
        : null;
  return { now: reviewDue ? "revisao" : daily, reviewDue, weeklyDoneOn: weeklyDone ? marks.weeklyOn : null };
}

export const RITUAL_LABEL: Record<TRitual, string> = {
  abrir: "Abrir o dia",
  fechar: "Fechar o dia",
  revisao: "Revisão semanal",
};

const WEEKDAY_LONG = [
  "domingo",
  "segunda-feira",
  "terça-feira",
  "quarta-feira",
  "quinta-feira",
  "sexta-feira",
  "sábado",
];
const MONTH_LONG = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

/** "Quinta-feira, 8 de outubro". */
export function longDate(iso: string) {
  const [, month, day] = iso.split("-").map(Number);
  const name = WEEKDAY_LONG[weekday(iso)];
  return `${name[0].toUpperCase()}${name.slice(1)}, ${day} de ${MONTH_LONG[month - 1]}`;
}

export const greeting = (time: string) => {
  const hour = Math.floor(minutesOf(time) / 60);
  return hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
};

// ---------------------------------------------------------------- prepared messages: the agent drafts, it does not send

export type TMessageKind = "nudge" | "consult" | "inform" | "postpone";

export function preparedMessage(
  kind: TMessageKind,
  item: TMockItem,
  personName: (id: string) => string,
  personId: string,
  extra: { note?: string; from?: string; to?: string } = {}
) {
  const name = personName(personId);
  switch (kind) {
    case "nudge": {
      const opener =
        item.followUp && diffDays(item.followUp) <= 0
          ? `nosso retorno era ${diffDays(item.followUp) === 0 ? "hoje" : `em ${dayMonth(item.followUp)}`}`
          : "passando para acompanhar";
      const due = item.due ? ` até ${dayMonth(item.due)}` : "";
      return `${name}, ${opener}. Como está “${item.title}”? O que falta para entregar${due} e de que apoio você precisa?`;
    }
    case "consult": {
      const by = item.due ? addDays(item.due, -1) : addDays(currentToday(), 1);
      return `${name}, antes de decidir “${item.title}”, preciso da sua avaliação. Consegue me responder até ${dayMonth(by < currentToday() ? currentToday() : by)}?`;
    }
    case "inform":
      return `${name}, para seu conhecimento: “${item.title}” foi ${item.kind === "decision" ? "aprovada" : "concluída"}${extra.note ? `. ${extra.note}` : ""}. Se isso muda algo no seu trabalho, me avise.`;
    case "postpone":
      return `${name}, “${item.title}” passou de ${extra.from ? dayMonth(extra.from) : "sem prazo"} para ${extra.to ? dayMonth(extra.to) : "sem prazo"}${extra.note ? ` (${extra.note})` : ""}.`;
  }
}

// ---------------------------------------------------------------- projects (laws 1, 2 and 7)

export function resultProgress(result: TMockResult) {
  if (!("measure" in result)) return null;
  const { baseline, current, target } = result.measure;
  if (target === baseline) return 100;
  return Math.max(0, Math.min(100, Math.round(((current - baseline) / (target - baseline)) * 100)));
}

/** The visible next action of a project: the earliest workable combinado, or null (law 7: stalled). */
export function projectNextAction(items: TMockItem[], projectId: string) {
  return (
    items
      .filter(
        (item) =>
          item.projectId === projectId &&
          item.kind === "action" &&
          (item.status === "todo" || item.status === "in_progress")
      )
      .sort(byDue)[0] ?? null
  );
}

export const STALL_CAUSES = [
  { key: "decisao", label: "Falta uma decisão" },
  { key: "recurso", label: "Falta recurso" },
  { key: "responsavel", label: "Falta um responsável" },
  { key: "informacao", label: "Falta informação" },
  { key: "capacidade", label: "Falta capacidade" },
] as const;

// ---------------------------------------------------------------- capture first, structure later (§8, §9, §17)

export type TCaptureGuess = {
  title: string;
  kind: TMockKind | null;
  due: string | null;
  personIds: string[];
  projectId: string | null;
  followUp?: string | null;
};

/** The one question the agent asks after interpreting a capture (Metodologia §09), or null. */
export function captureGap(guess: TCaptureGuess, personName: (id: string) => string, today: string = currentToday()) {
  if (guess.kind === "action" && guess.personIds.length && guess.followUp === undefined) {
    const options = [
      { label: "amanhã", value: addDays(today, 1) },
      ...(guess.due && diffDays(guess.due, today) > 2
        ? [
            {
              label: `${relativeDue(suggestFollowUp(guess.due, today), today).label} (meio do prazo)`,
              value: suggestFollowUp(guess.due, today),
            },
          ]
        : []),
      { label: "próxima segunda", value: nextMonday(today) },
    ];
    return {
      field: "followUp" as const,
      text: `Quando você quer revisar isso com ${personName(guess.personIds[0])}?`,
      options,
    };
  }
  if (guess.kind === "action" && !guess.due)
    return {
      field: "due" as const,
      text: "Para quando?",
      options: [
        { label: "hoje", value: today },
        { label: "amanhã", value: addDays(today, 1) },
        { label: "sexta", value: weekday(today) === 5 ? today : nextFriday(today) },
      ],
    };
  if (guess.kind === "decision" && !guess.due)
    return {
      field: "due" as const,
      text: "Até quando decidir?",
      options: [
        { label: "amanhã", value: addDays(today, 1) },
        { label: "sexta", value: weekday(today) === 5 ? today : nextFriday(today) },
        { label: "próxima semana", value: nextMonday(today) },
      ],
    };
  return null;
}

const normalize = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

const WEEKDAY_WORDS: [RegExp, number][] = [
  [/\b(domingo|dom)\b/, 0],
  [/\b(segunda(-feira)?|seg)\b/, 1],
  [/\b(terca(-feira)?|ter)\b/, 2],
  [/\b(quarta(-feira)?|qua)\b/, 3],
  [/\b(quinta(-feira)?|qui)\b/, 4],
  [/\b(sexta(-feira)?|sex)\b/, 5],
  [/\b(sabado|sab)\b/, 6],
];

const ACTION_START =
  /^(cobrar|enviar|mandar|revisar|preparar|ligar|agendar|marcar|pedir|solicitar|responder|atualizar|ver|falar|fazer|criar|checar|verificar|consolidar|ajustar|confirmar|alinhar|organizar|comprar)\b/;

function guessDue(text: string, today: string): string | null {
  if (/\bhoje\b/.test(text)) return today;
  if (/\bamanha\b/.test(text)) return addDays(today, 1);
  if (/\b(semana que vem|proxima semana)\b/.test(text)) return nextMonday(today);
  if (/\bfim do mes\b/.test(text)) {
    const [year, month] = today.split("-").map(Number);
    return fromDayNumber(
      dayNumber(`${month === 12 ? year + 1 : year}-${String((month % 12) + 1).padStart(2, "0")}-01`) - 1
    );
  }
  const explicit = /\b(\d{1,2})\/(\d{1,2})\b/.exec(text);
  if (explicit) {
    const year = Number(today.slice(0, 4));
    const candidate = `${year}-${explicit[2].padStart(2, "0")}-${explicit[1].padStart(2, "0")}`;
    return diffDays(candidate, today) < -30 ? `${year + 1}${candidate.slice(4)}` : candidate;
  }
  for (const [pattern, day] of WEEKDAY_WORDS) {
    if (pattern.test(text)) return addDays(today, (day - weekday(today) + 7) % 7 || 7);
  }
  return null;
}

/** Deterministic first pass: no model involved, every guess is shown as a correctable chip. */
export function parseCapture(
  raw: string,
  people: TMockPerson[],
  projects: TMockProject[],
  meId: string,
  today: string = currentToday()
): TCaptureGuess {
  const text = normalize(raw.trim());
  const tags = new Set([...text.matchAll(/#([a-z0-9-]+)/g)].map((match) => match[1]));
  const projectId =
    projects.find((project) => tags.has(project.identifier.toLowerCase()))?.id ??
    projects.find((project) => project.keywords.some((word) => new RegExp(`\\b${normalize(word)}\\b`).test(text)))
      ?.id ??
    null;
  const personIds = people
    .filter((person) => person.id !== meId)
    .filter((person) => new RegExp(`@?\\b${normalize(person.display_name)}\\b`).test(text))
    .map((person) => person.id);
  const due = guessDue(text, today);
  const kind: TMockKind | null = /\b(decidir|decisao|aprovar|escolher)\b/.test(text)
    ? "decision"
    : /\b(risco|pode atrasar|ameaca|pode falhar)\b/.test(text)
      ? "risk"
      : ACTION_START.test(text) || due
        ? "action"
        : null;
  const title = raw
    .replace(/#[\p{L}0-9-]+/gu, "")
    .replace(/@/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
  return { title, kind, due, personIds, projectId };
}
