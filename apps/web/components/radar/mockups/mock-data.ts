/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Fictional data for the RADAR UX mockups (RADAR_UX_VIEW). This is the shape the Interaction Model
 * would hand the interface, not the Core model: no ObjectType, PropertyDefinition or capability here.
 * "Today" is frozen so relative dates ("amanhã", "atrasada 2 dias") read the same on every run.
 */

export const MOCK_TODAY = "2026-10-08";

/** The single reference for date, time and zone. Everything that says "hoje" reads it, so tests can move it. */
export type TMockNow = { date: string; time: string; tz: string };

export const MOCK_NOW: TMockNow = { date: MOCK_TODAY, time: "09:00", tz: "-03:00" };

let currentNow: TMockNow = { ...MOCK_NOW };

export const mockNow = (): TMockNow => currentNow;
export const currentToday = () => currentNow.date;
export const setMockNow = (now: Partial<TMockNow>) => {
  currentNow = { ...currentNow, ...now };
};
export const resetMockNow = () => {
  currentNow = { ...MOCK_NOW };
};

export type TMockKind = "action" | "decision" | "risk" | "issue";

export type TMockStatus =
  | "inbox"
  | "todo"
  | "in_progress"
  | "waiting"
  | "blocked"
  | "done"
  | "cancelled"
  | "proposed"
  | "decided"
  | "identified"
  | "monitoring"
  | "mitigating"
  | "accepted"
  | "closed";

/** Plane's priority keys, so the stock PrioritySelect / PriorityIcon render them. */
export type TMockPriority = "urgent" | "high" | "medium" | "low" | "none";

export type TMockPerson = {
  id: string;
  name: string;
  display_name: string;
  role: string;
  /** Part of the manager's team, or someone outside it (supplier, counsel, client). */
  affiliation: "equipe" | "externa";
  organization?: string;
  /** May approve decisions, as long as they are not the author. */
  canApprove?: boolean;
};

/** How the project's result is observed (laws 1 and 2): a number, or an observable criterion. */
export type TMockResult =
  | { statement: string; measure: { baseline: number; current: number; target: number; unit: string } }
  | { statement: string; criterion: string };

export type TMockProject = {
  id: string;
  identifier: string;
  title: string;
  objective: string;
  ownerId: string;
  status: "active" | "on_hold" | "done";
  due: string | null;
  keywords: string[];
  result: TMockResult;
};

/** Up to three results for the week (Guia básico §01), each with how we will know it happened. */
export type TMockWeekResult = {
  id: string;
  title: string;
  /** Empty means "a confirmar": the gap stays visible instead of being filled with a guess. */
  howWeKnow: string;
  projectId: string | null;
  state: "open" | "met" | "partial" | "missed";
};

/** A piece of evidence: who attached it and when, never anonymous. */
export type TMockEvidence = { id: string; label: string; addedBy: string; at: string };

/** A fact the manager recorded: it happened, by whom, when. Preparing a message is not one of these. */
export type TMockRecord = {
  id: string;
  kind: "consult" | "inform" | "nudge" | "confirmation";
  personId: string;
  by: string;
  at: string;
  note?: string;
};

/** Decision approval: asked of someone else, or sent back to the author. */
export type TMockApproval =
  | { state: "requested"; approverId: string; requestedBy: string; at: string }
  | { state: "returned"; by: string; at: string; reason: string };

/** Two sources disagree about the due date: both stay visible until someone picks. */
export type TMockDueConflict = { sources: { label: string; date: string }[] };

export type TMockActivity = {
  id: string;
  at: string;
  actorId: string;
  text: string;
};

export type TMockItem = {
  id: string;
  kind: TMockKind;
  title: string;
  status: TMockStatus;
  priority: TMockPriority;
  projectId: string | null;
  /** Responsável: who answers for the item. */
  ownerId: string;
  /** Who executes or must respond, when not the owner. */
  withIds: string[];
  due: string | null;
  riskScore?: number;
  context: string;
  dependsOnIds: string[];
  evidence: TMockEvidence[];
  agentNote?: { text: string; personId?: string; source?: string };
  activity: TMockActivity[];
  // ---- the "combinado" (Guia básico §03)
  /** What must exist at the end and how it will be accepted. */
  deliverable?: string;
  /** One step, with a verb, that someone can start. Core: action.next_step. */
  nextStep?: string;
  /** When to look again, distinct from the due date. Core: next_review_at on the delegation. */
  followUp?: string | null;
  /** Whether the executor confirmed the terms. Core: delegation acceptance (proposed/accepted). */
  /**
   * "confirmed" is what the manager recorded, never the executor's own act: there is no executor channel yet,
   * so `recordedBy` is always the manager.
   */
  confirmation?: { state: "pending" | "confirmed"; at?: string; recordedBy?: string };
  autonomy?: string;
  /** "Bloqueado" is waiting + a reason in the Core; the interface names it. */
  blockedReason?: string;
  previousDues?: { from: string; to: string; reason?: string }[];
  // ---- distribution (Metodologia §05). Core records the obligation, not that it happened.
  consultIds?: string[];
  consultedIds?: string[];
  informIds?: string[];
  informedIds?: string[];
  /** Facts the manager recorded about consultations, communications, follow-ups and confirmations. */
  records?: TMockRecord[];
  // ---- decisions
  /** Who proposed the decision. Approval needs someone else. */
  authorId?: string;
  proposal?: { rationale: string };
  approval?: TMockApproval;
  // ---- risks and dates
  /** Projects this risk threatens (relation "threatens" between existing objects). */
  threatensIds?: string[];
  dueConflict?: TMockDueConflict;
  /** What was delivered, in the words recorded when the item was concluded. */
  outcome?: string;
};

export type TMockSuggestionPart = { state: "pending" | "accepted" | "rejected" | "failed"; error?: string };

export type TMockSuggestion = {
  /**
   * "relation": what the agent proposes today, a link between existing objects plus a mitigation action,
   * each reviewed on its own. "new_risk": a preview of a future capability, not available.
   */
  type: "relation" | "new_risk";
  kind: "risk" | "action";
  title: string;
  projectId: string;
  ownerId: string;
  due: string | null;
  riskScore?: number;
  explanation: string;
  confidence: number;
  companion?: { title: string; withId: string; due: string };
  relation?: { riskId: string; targetProjectId: string } & TMockSuggestionPart;
  mitigation?: { title: string; withId: string; due: string } & TMockSuggestionPart;
  evidence?: { label: string; source: string }[];
  version?: number;
  editedAt?: string;
};

export type TMockInboxEntry = {
  id: string;
  source: "captura" | "agente" | "reuniao" | "integracao";
  title: string;
  detail: string;
  receivedAt: string;
  suggestion?: TMockSuggestion;
  /** Meeting extraction: candidate actions, each accepted on its own. */
  candidates?: { title: string; withId: string; due: string }[];
  /** "Revisar em…": hidden from the Inbox until this date. */
  reviewOn?: string;
};

export const ME_ID = "p-joao";

/** When the manager last opened the day, closed it and did the weekly review, for "Desde sua última revisão". */
export const MOCK_RITUAL_MARKS = { openedOn: "2026-10-05", closedOn: "2026-10-05", weeklyOn: "2026-10-05" };

export const MOCK_PEOPLE: TMockPerson[] = [
  {
    id: ME_ID,
    name: "João Marcos Ramos",
    display_name: "João",
    role: "Gerente de projetos",
    affiliation: "equipe",
    canApprove: true,
  },
  { id: "p-carlos", name: "Carlos Andrade", display_name: "Carlos", role: "Suprimentos", affiliation: "equipe" },
  { id: "p-ana", name: "Ana Paula Lima", display_name: "Ana", role: "Jurídico", affiliation: "equipe" },
  { id: "p-maria", name: "Maria Souza", display_name: "Maria", role: "Financeiro", affiliation: "equipe" },
  {
    id: "p-rafael",
    name: "Rafael Costa",
    display_name: "Rafael",
    role: "Engenharia",
    affiliation: "equipe",
    canApprove: true,
  },
  {
    id: "p-beatriz",
    name: "Beatriz Nunes",
    display_name: "Beatriz",
    role: "PMO",
    affiliation: "equipe",
    canApprove: true,
  },
  {
    id: "p-ricardo",
    name: "Ricardo Mendes",
    display_name: "Ricardo",
    role: "Gerente comercial",
    affiliation: "externa",
    organization: "XPTO Engenharia",
  },
  {
    id: "p-luiza",
    name: "Luiza Prado",
    display_name: "Luiza",
    role: "Advogada",
    affiliation: "externa",
    organization: "Prado & Assis Advogados",
  },
];

export const MOCK_PROJECTS: TMockProject[] = [
  {
    id: "pr-mob",
    identifier: "MOB",
    title: "Mobilização Refinaria",
    objective: "Iniciar a operação em 3 de novembro",
    ownerId: ME_ID,
    status: "active",
    due: "2026-11-03",
    keywords: ["mobilização", "mobilizacao", "refinaria", "xpto", "fornecedor"],
    result: {
      statement: "Mobilizações entregues no prazo",
      measure: { baseline: 72, current: 81, target: 95, unit: "%" },
    },
  },
  {
    id: "pr-orc",
    identifier: "ORC",
    title: "Orçamento 2027",
    objective: "Aprovar o orçamento no comitê de dezembro",
    ownerId: ME_ID,
    status: "active",
    due: "2026-12-05",
    keywords: ["orçamento", "orcamento", "budget", "comitê", "comite"],
    result: { statement: "Orçamento 2027 aprovado", criterion: "Ata do comitê de dezembro com a aprovação" },
  },
  {
    id: "pr-erp",
    identifier: "ERP",
    title: "ERP Fase 2",
    objective: "Migrar compras e estoque para o novo ERP",
    ownerId: "p-rafael",
    status: "active",
    due: "2027-02-15",
    keywords: ["erp", "migração", "migracao", "estoque"],
    result: {
      statement: "Pedidos de compra emitidos no novo ERP",
      measure: { baseline: 0, current: 0, target: 100, unit: "%" },
    },
  },
  {
    id: "pr-ia",
    identifier: "GIA",
    title: "Governança de IA",
    objective: "Política de uso de IA publicada até março",
    ownerId: "p-beatriz",
    status: "active",
    due: "2027-03-31",
    keywords: ["ia", "governança", "governanca", "política", "politica"],
    result: {
      statement: "Política de uso de IA publicada",
      criterion: "Aprovada pela diretoria e publicada na intranet",
    },
  },
];

export const MOCK_WEEK_RESULTS: TMockWeekResult[] = [
  {
    id: "wr-fornecedor",
    title: "Fornecedor da mobilização contratado",
    howWeKnow: "Contrato da XPTO assinado até sexta, 09/10",
    projectId: "pr-mob",
    state: "open",
  },
  {
    id: "wr-premissas",
    title: "Premissas do orçamento 2027 validadas",
    howWeKnow: "Maria de acordo, por escrito, com as premissas",
    projectId: "pr-orc",
    state: "open",
  },
];

const at = (date: string, time = "09:00") => `${date}T${time}:00-03:00`;

const evidenceOf = (labels: string[], by = ME_ID, date = "2026-10-02"): TMockEvidence[] =>
  labels.map((label, index) => ({ id: `ev-${index + 1}`, label, addedBy: by, at: date }));

export const MOCK_ITEMS: TMockItem[] = [
  {
    id: "it-xpto-decision",
    kind: "decision",
    title: "Contratação do fornecedor XPTO",
    status: "proposed",
    priority: "urgent",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-09",
    context:
      "A XPTO é a única proposta dentro do prazo de mobilização. O jurídico pediu ajuste na cláusula de multa, e o comparativo de fornecedores ainda não chegou.",
    dependsOnIds: ["it-comparativo"],
    evidence: evidenceOf(["Proposta comercial XPTO (v2)", "Parecer jurídico preliminar"]),
    agentNote: {
      text: "Esta decisão depende do comparativo que Carlos deveria ter enviado em 06/10.",
      personId: "p-carlos",
      source: "Combinado com Carlos · prazo 06/10 · sem atualização desde 04/10",
    },
    authorId: ME_ID,
    proposal: { rationale: "É a única proposta que cumpre o prazo de mobilização, com a multa limitada a 10%." },
    consultIds: ["p-ana"],
    consultedIds: [],
    informIds: ["p-carlos", "p-ricardo"],
    informedIds: [],
    activity: [
      { id: "a1", at: at("2026-10-01"), actorId: ME_ID, text: "criou a decisão" },
      { id: "a2", at: at("2026-10-03", "14:20"), actorId: "p-ana", text: "anexou o parecer jurídico preliminar" },
      { id: "a3", at: at("2026-10-07", "08:00"), actorId: "radar", text: "ligou a decisão ao comparativo pendente" },
    ],
  },
  {
    id: "it-comparativo",
    kind: "action",
    title: "Enviar comparativo de fornecedores",
    status: "in_progress",
    priority: "high",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: ["p-carlos"],
    due: "2026-10-06",
    context: "Comparar XPTO, Alfa e Delta em prazo de entrega, preço e garantia.",
    dependsOnIds: [],
    evidence: [],
    agentNote: {
      text: "Carlos não atualiza esta ação há 4 dias, e a decisão da XPTO vence amanhã.",
      personId: "p-carlos",
      source: "Último comentário de Carlos em 04/10 · decisão XPTO com prazo 09/10",
    },
    deliverable: "Tabela com 3 opções: custo total, prazo de entrega, riscos e recomendação",
    nextStep: "Cotar a Delta",
    followUp: "2026-10-03",
    confirmation: { state: "confirmed", at: "2026-09-29", recordedBy: ME_ID },
    autonomy: "Pode pedir cotações; a contratação depende de aprovação",
    activity: [
      { id: "a1", at: at("2026-09-29"), actorId: ME_ID, text: "delegou a Carlos, prazo 06/10" },
      { id: "a2", at: at("2026-10-04", "11:10"), actorId: "p-carlos", text: "comentou: falta a cotação da Delta" },
    ],
  },
  {
    id: "it-risco-mob",
    kind: "risk",
    title: "Atraso na mobilização da refinaria",
    status: "mitigating",
    priority: "high",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: ["p-rafael"],
    due: "2026-10-03",
    riskScore: 20,
    context: "Sem fornecedor contratado até 10/10, o canteiro não fica pronto para 03/11. Probabilidade 4, impacto 5.",
    dependsOnIds: ["it-xpto-decision"],
    evidence: evidenceOf(["Cronograma de mobilização rev. 3"]),
    activity: [
      { id: "a1", at: at("2026-09-20"), actorId: ME_ID, text: "registrou o risco" },
      { id: "a2", at: at("2026-09-26"), actorId: ME_ID, text: "revisou: segue mitigando" },
    ],
  },
  {
    id: "it-orc-revisar",
    kind: "action",
    title: "Revisar premissas do orçamento 2027",
    status: "todo",
    priority: "medium",
    projectId: "pr-orc",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-08",
    context: "Inflação, câmbio e reajuste salarial enviados pelo Financeiro.",
    nextStep: "Comparar inflação e câmbio com o plano de 2026",
    dependsOnIds: [],
    evidence: evidenceOf(["Planilha de premissas (Maria)"]),
    activity: [{ id: "a1", at: at("2026-10-02"), actorId: "p-maria", text: "enviou as premissas" }],
  },
  {
    id: "it-orc-pauta",
    kind: "action",
    title: "Preparar pauta do comitê de orçamento",
    status: "todo",
    priority: "medium",
    projectId: "pr-orc",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-12",
    context: "Pauta para o comitê de 15/10.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-01"), actorId: ME_ID, text: "criou a ação" }],
  },
  {
    id: "it-maria-carlos",
    kind: "action",
    title: "Responder Maria sobre o rateio de TI",
    status: "todo",
    priority: "low",
    projectId: "pr-orc",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-09",
    context: "Maria perguntou se o rateio de TI entra no centro de custo do projeto.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-07", "16:40"), actorId: "p-maria", text: "perguntou por mensagem" }],
  },
  {
    id: "it-orc-numeros",
    kind: "action",
    title: "Consolidar números de pessoal",
    status: "waiting",
    priority: "medium",
    projectId: "pr-orc",
    ownerId: ME_ID,
    withIds: ["p-maria"],
    due: "2026-10-13",
    context: "Aguardando a base de headcount do RH, que Maria vai consolidar.",
    deliverable: "Planilha de headcount por centro de custo, validada pelo RH",
    followUp: "2026-10-09",
    confirmation: { state: "confirmed", at: "2026-10-05", recordedBy: ME_ID },
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-05"), actorId: ME_ID, text: "delegou a Maria" }],
  },
  {
    id: "it-contrato-clausula",
    kind: "action",
    title: "Ajustar cláusula de multa do contrato XPTO",
    status: "in_progress",
    priority: "high",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: ["p-ana"],
    due: "2026-10-09",
    context: "Limitar a multa a 10% do valor do contrato.",
    deliverable: "Minuta revisada com a multa limitada a 10%",
    nextStep: "Enviar a contraproposta ao jurídico da XPTO",
    followUp: "2026-10-08",
    confirmation: { state: "pending" },
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-03"), actorId: ME_ID, text: "delegou a Ana" }],
  },
  {
    id: "it-erp-cutover",
    kind: "decision",
    title: "Data de virada do módulo de compras",
    status: "proposed",
    priority: "high",
    projectId: "pr-erp",
    ownerId: ME_ID,
    withIds: ["p-rafael"],
    due: "2026-10-14",
    context: "Rafael propõe 01/12. A alternativa é 05/01, depois do fechamento do ano.",
    authorId: "p-rafael",
    proposal: {
      rationale: "A virada em 01/12 antecipa o ganho de estoque e deixa janela para correção antes do fechamento.",
    },
    consultIds: ["p-maria"],
    consultedIds: ["p-maria"],
    records: [{ id: "r-maria", kind: "consult", personId: "p-maria", by: ME_ID, at: at("2026-10-07", "15:10") }],
    informIds: ["p-rafael", "p-beatriz"],
    informedIds: [],
    dependsOnIds: [],
    evidence: evidenceOf(["Plano de virada v1"]),
    activity: [{ id: "a1", at: at("2026-10-06"), actorId: "p-rafael", text: "propôs a decisão" }],
  },
  {
    id: "it-erp-risco-dados",
    kind: "risk",
    title: "Qualidade dos dados de estoque na migração",
    status: "monitoring",
    priority: "medium",
    projectId: "pr-erp",
    ownerId: "p-rafael",
    withIds: [],
    due: "2026-10-20",
    riskScore: 12,
    context: "8% dos itens têm unidade de medida divergente.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-09-30"), actorId: "p-rafael", text: "registrou o risco" }],
  },
  {
    id: "it-erp-testes",
    kind: "action",
    title: "Executar testes integrados de compras",
    status: "in_progress",
    priority: "high",
    projectId: "pr-erp",
    ownerId: "p-rafael",
    withIds: [],
    due: "2026-10-17",
    context: "Roteiro com 42 cenários.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-01"), actorId: "p-rafael", text: "iniciou" }],
  },
  {
    id: "it-erp-treinamento",
    kind: "action",
    title: "Agendar treinamento dos compradores",
    status: "todo",
    priority: "low",
    projectId: "pr-erp",
    ownerId: "p-rafael",
    withIds: ["p-beatriz"],
    due: "2026-10-05",
    context: "Turmas de 2 horas para 25 compradores.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-09-28"), actorId: "p-rafael", text: "delegou a Beatriz" }],
  },
  {
    id: "it-ia-politica",
    kind: "action",
    title: "Minuta da política de uso de IA",
    status: "waiting",
    priority: "medium",
    projectId: "pr-ia",
    ownerId: "p-beatriz",
    withIds: ["p-ana"],
    due: "2026-10-24",
    context: "Aguardando revisão do jurídico.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-09-25"), actorId: "p-beatriz", text: "enviou ao jurídico" }],
  },
  {
    id: "it-mob-epi",
    kind: "action",
    title: "Comprar EPIs para a equipe de campo",
    status: "done",
    priority: "medium",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: ["p-carlos"],
    due: "2026-10-02",
    context: "",
    dependsOnIds: [],
    evidence: evidenceOf(["Pedido de compra 4512"]),
    activity: [{ id: "a1", at: at("2026-10-02"), actorId: "p-carlos", text: "concluiu" }],
  },
  {
    id: "it-mob-licenca",
    kind: "decision",
    title: "Usar alojamento próprio em vez de hotel",
    status: "decided",
    priority: "medium",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: [],
    due: null,
    context: "",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-09-22"), actorId: ME_ID, text: "aprovou" }],
    authorId: ME_ID,
    informIds: ["p-carlos", "p-rafael"],
    informedIds: ["p-carlos"],
    records: [{ id: "r-carlos", kind: "inform", personId: "p-carlos", by: ME_ID, at: at("2026-09-23", "10:00") }],
  },
  {
    id: "it-xpto-cronograma",
    kind: "action",
    title: "Receber cronograma de entrega da XPTO",
    status: "waiting",
    priority: "high",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: ["p-ricardo"],
    due: "2026-10-13",
    context: "Ricardo prometeu o cronograma assim que a engenharia da XPTO confirmar a fabricação.",
    deliverable: "Cronograma com data de entrega de cada equipamento",
    dueConflict: {
      sources: [
        { label: "Combinado com Ricardo", date: "2026-10-13" },
        { label: "Cronograma do projeto", date: "2026-10-16" },
      ],
    },
    followUp: "2026-10-09",
    confirmation: { state: "confirmed", at: "2026-10-06", recordedBy: ME_ID },
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-06", "10:30"), actorId: ME_ID, text: "pediu o cronograma a Ricardo" }],
  },
  {
    id: "it-parecer-reajuste",
    kind: "action",
    title: "Parecer sobre o reajuste do contrato de manutenção",
    status: "in_progress",
    priority: "medium",
    projectId: "pr-orc",
    ownerId: ME_ID,
    withIds: ["p-luiza"],
    due: "2026-10-07",
    context: "O reajuste proposto (IGP-M + 3%) impacta a linha de manutenção do orçamento 2027.",
    deliverable: "Parecer escrito: o reajuste é devido e qual o índice correto",
    followUp: "2026-10-06",
    confirmation: { state: "confirmed", at: "2026-09-30", recordedBy: ME_ID },
    dependsOnIds: [],
    evidence: evidenceOf(["Minuta de aditivo do contrato de manutenção"]),
    activity: [{ id: "a1", at: at("2026-09-30"), actorId: ME_ID, text: "contratou o parecer com Luiza" }],
  },
  {
    id: "it-mob-cronograma",
    kind: "action",
    title: "Atualizar o cronograma da mobilização",
    status: "blocked",
    priority: "high",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-12",
    context: "O cronograma depende das datas de entrega dos equipamentos.",
    dependsOnIds: ["it-xpto-decision"],
    evidence: [],
    nextStep: "Lançar as datas de entrega da XPTO no cronograma rev. 4",
    blockedReason: "Sem fornecedor contratado, não há data de entrega dos equipamentos",
    activity: [{ id: "a1", at: at("2026-10-05"), actorId: ME_ID, text: "marcou como bloqueada" }],
  },
  {
    id: "it-risco-fornecedor",
    kind: "risk",
    title: "Dependência de um único fornecedor (XPTO)",
    status: "identified",
    priority: "medium",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-22",
    riskScore: 12,
    context: "Só a XPTO atende o prazo. Se ela falhar, não há segunda opção homologada.",
    dependsOnIds: [],
    evidence: [],
    activity: [{ id: "a1", at: at("2026-10-06"), actorId: ME_ID, text: "registrou o risco" }],
  },
  {
    id: "it-risco-chuva",
    kind: "risk",
    title: "Chuvas podem atrasar a concretagem da base",
    status: "accepted",
    priority: "low",
    projectId: "pr-mob",
    ownerId: ME_ID,
    withIds: [],
    due: "2026-10-12",
    riskScore: 9,
    context: "Risco aceito em 28/09 pelo comitê. Continua em acompanhamento: rever a previsão do tempo a cada semana.",
    dependsOnIds: [],
    evidence: evidenceOf(["Ata do comitê de 28/09"], ME_ID, "2026-09-28"),
    activity: [{ id: "a1", at: at("2026-09-28"), actorId: ME_ID, text: "aceitou o risco" }],
  },
  {
    id: "it-treinamento-decision",
    kind: "decision",
    title: "Contratar treinamento externo para os compradores",
    status: "proposed",
    priority: "medium",
    projectId: "pr-erp",
    ownerId: ME_ID,
    withIds: [],
    due: null,
    context:
      "Beatriz propõe duas turmas com consultoria externa antes da virada do ERP. A cotação ainda não foi anexada.",
    authorId: "p-beatriz",
    proposal: { rationale: "Reduz o risco de erro operacional nas primeiras semanas depois da virada." },
    dependsOnIds: [],
    evidence: [],
    informIds: ["p-beatriz"],
    informedIds: [],
    activity: [{ id: "a1", at: at("2026-10-07", "09:30"), actorId: "p-beatriz", text: "propôs a decisão" }],
  },
];

export const MOCK_INBOX: TMockInboxEntry[] = [
  {
    id: "in-agent-link",
    source: "agente",
    title: "Ligar o risco “Dependência de um único fornecedor (XPTO)” ao projeto Orçamento 2027",
    detail: "Revisão de riscos dos seus projetos ativos · hoje, 08:00",
    receivedAt: at("2026-10-08", "08:00"),
    suggestion: {
      type: "relation",
      kind: "risk",
      title: "Dependência de um único fornecedor (XPTO) ameaça o Orçamento 2027",
      projectId: "pr-orc",
      ownerId: ME_ID,
      due: null,
      explanation:
        "O valor da XPTO é 18% acima da linha de mobilização prevista no orçamento. Se ela for a única fornecedora, o custo não tem alternativa de comparação.",
      confidence: 0.71,
      version: 1,
      evidence: [
        { label: "Proposta comercial XPTO (v2): valor sem reajuste", source: "Documento anexado à decisão XPTO" },
        { label: "Linha de mobilização do orçamento 2027", source: "Planilha de premissas (Maria)" },
      ],
      relation: { riskId: "it-risco-fornecedor", targetProjectId: "pr-orc", state: "pending" },
      mitigation: {
        title: "Reservar contingência de 5% no orçamento 2027 para a XPTO",
        withId: "p-maria",
        due: "2026-10-14",
        state: "pending",
      },
    },
  },
  {
    id: "in-agent-risk",
    source: "agente",
    title: "Novo risco: fornecedor XPTO pode atrasar a entrega",
    detail: "Prévia de funcionalidade futura · dados fictícios",
    receivedAt: at("2026-10-08", "08:00"),
    suggestion: {
      type: "new_risk",
      kind: "risk",
      title: "Fornecedor XPTO pode atrasar a entrega de equipamentos",
      projectId: "pr-mob",
      ownerId: ME_ID,
      due: "2026-10-15",
      riskScore: 16,
      explanation:
        "A proposta comercial da XPTO não traz prazo de entrega, e o cronograma de mobilização exige equipamentos em campo até 27/10.",
      confidence: 0.78,
      companion: { title: "Pedir cronograma de entrega à XPTO", withId: "p-carlos", due: "2026-10-09" },
    },
  },
  {
    id: "in-meeting",
    source: "reuniao",
    title: "Ata do comitê de projetos: 2 ações detectadas",
    detail: "Comitê semanal · ontem, 16:00",
    receivedAt: at("2026-10-07", "17:05"),
    candidates: [
      { title: "Atualizar cronograma do ERP com a nova data de testes", withId: "p-rafael", due: "2026-10-13" },
      { title: "Enviar status da mobilização para a diretoria", withId: ME_ID, due: "2026-10-09" },
    ],
  },
  {
    id: "in-capture-juridico",
    source: "captura",
    title: "Ver com jurídico a cláusula de reajuste do contrato de manutenção",
    detail: "ontem, 18:12",
    receivedAt: at("2026-10-07", "18:12"),
  },
  {
    id: "in-request",
    source: "integracao",
    title: "Carlos pediu aprovação para compra emergencial de R$ 48 mil",
    detail: "Carlos Andrade · hoje, 07:41",
    receivedAt: at("2026-10-08", "07:41"),
  },
];
