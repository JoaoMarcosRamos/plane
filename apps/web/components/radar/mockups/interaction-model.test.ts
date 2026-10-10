/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { copyText } from "./clipboard";
import { ME_ID, MOCK_ITEMS, MOCK_PEOPLE, MOCK_PROJECTS, resetMockNow } from "./mock-data";
import {
  STATUSES_BY_KIND,
  approvalBlockers,
  approversOf,
  attentionFor,
  buildHoje,
  captureGap,
  closeDayQueue,
  greeting,
  isOpen,
  isReversible,
  longDate,
  parseCapture,
  preparedMessage,
  primaryVerb,
  projectNextAction,
  relativeDue,
  resultProgress,
  ritualFor,
  statusMove,
  suggestFollowUp,
  verbsFor,
} from "./interaction-model";
import { RadarMockupStore } from "./mockup.store";

const name = (id: string) => MOCK_PEOPLE.find((person) => person.id === id)?.display_name ?? id;
const byId = (id: string) => MOCK_ITEMS.find((item) => item.id === id)!;
const ids = (items: { id: string }[]) => items.map((item) => item.id);
const PREFS = { abrir: "08:30", fechar: "17:30", semanal: "sex 16:00" };
const NO_MARKS = { openedOn: null, closedOn: null, weeklyOn: null };

beforeEach(() => resetMockNow());
afterEach(() => vi.unstubAllGlobals());

describe("relativeDue", () => {
  it("speaks in days relative to the frozen today (Thu 08/10/2026)", () => {
    expect(relativeDue("2026-10-06")).toEqual({ label: "há 2 dias", tone: "late" });
    expect(relativeDue("2026-10-07")).toEqual({ label: "ontem", tone: "late" });
    expect(relativeDue("2026-10-08")).toEqual({ label: "hoje", tone: "soon" });
    expect(relativeDue("2026-10-09")).toEqual({ label: "amanhã", tone: "soon" });
    expect(relativeDue("2026-10-10")).toEqual({ label: "sáb", tone: "normal" });
    expect(relativeDue("2026-10-20")).toEqual({ label: "20 out", tone: "normal" });
    expect(relativeDue(null)).toEqual({ label: "sem prazo", tone: "none" });
  });

  it("follows the one clock: moving it moves every relative date", () => {
    const store = new RadarMockupStore({ now: { date: "2026-10-12", time: "09:00" } });
    expect(relativeDue("2026-10-12")).toEqual({ label: "hoje", tone: "soon" });
    expect(longDate(store.today)).toBe("Segunda-feira, 12 de outubro");
    store.setNow({ date: "2026-10-13", time: "19:00" });
    expect(relativeDue("2026-10-12")).toEqual({ label: "ontem", tone: "late" });
    expect(greeting(store.now.time)).toBe("Boa noite");
  });
});

describe("Hoje", () => {
  const hoje = buildHoje(MOCK_ITEMS, ME_ID, name);

  it("keeps what is still pending: undated decisions, followed-up risks and conflicting dates stay visible", () => {
    expect(hoje.attention.map((entry) => [entry.item.id, entry.severity])).toEqual([
      ["it-risco-mob", "critical"],
      ["it-comparativo", "critical"],
      ["it-parecer-reajuste", "critical"],
      ["it-xpto-decision", "critical"],
      ["it-mob-cronograma", "warning"],
      ["it-xpto-cronograma", "warning"],
      ["it-erp-cutover", "warning"],
      ["it-treinamento-decision", "warning"],
      ["it-risco-chuva", "neutral"],
    ]);
    const reason = (id: string) => hoje.attention.find((entry) => entry.item.id === id)?.reason;
    expect(reason("it-comparativo")).toBe("Atrasado há 2 dias · com Carlos");
    expect(reason("it-mob-cronograma")).toBe(
      "Bloqueado · Sem fornecedor contratado, não há data de entrega dos equipamentos"
    );
    expect(reason("it-treinamento-decision")).toBe("Decisão necessária · Prazo a definir");
    expect(reason("it-risco-chuva")).toBe("Risco aceito (9) · acompanhar até 12/10");
    expect(reason("it-xpto-cronograma")).toBe("Prazos divergentes · 13/10 × 16/10");
  });

  it("answers the five relational questions of the Metodologia", () => {
    const views = hoje.views!;
    expect(ids(views.fazer)).toEqual(["it-orc-revisar", "it-maria-carlos", "it-orc-pauta", "it-mob-cronograma"]);
    expect(ids(views.decidir)).toEqual(["it-xpto-decision", "it-erp-cutover", "it-treinamento-decision"]);
    expect(ids(views.consultar)).toEqual(["it-xpto-decision"]);
    expect(ids(views.aguardando)).toEqual([
      "it-comparativo",
      "it-parecer-reajuste",
      "it-contrato-clausula",
      "it-orc-numeros",
      "it-xpto-cronograma",
    ]);
    expect(ids(views.informar)).toEqual(["it-mob-licenca"]);
  });

  it("shows other people's late work only in the team view", () => {
    expect(hoje.attention.some((entry) => entry.item.id === "it-erp-treinamento")).toBe(false);
    const team = buildHoje(MOCK_ITEMS, null, name);
    expect(team.attention.some((entry) => entry.item.id === "it-erp-treinamento")).toBe(true);
    expect(team.views).toBeNull();
  });

  it("an accepted risk is not closed: it keeps being followed until someone closes it", () => {
    expect(isOpen("accepted")).toBe(true);
    const store = new RadarMockupStore();
    store.run("it-risco-mob", "accept_risk", { note: "o comitê aceitou" });
    const risk = store.item("it-risco-mob")!;
    expect(risk.status).toBe("accepted");
    expect(risk.due).toBe("2026-11-07");
    expect(verbsFor(risk, ME_ID, name).map((verb) => verb.label)).toEqual([
      "Revisar",
      "Criar ação de mitigação",
      "Encerrar o risco",
    ]);
    expect(store.run("it-risco-mob", "complete", { note: "Risco eliminado: fornecedor contratado" })).toBe(true);
    expect(store.item("it-risco-mob")?.status).toBe("closed");
  });

  it("with two sources for the due date nothing is postponed until one is chosen", () => {
    const store = new RadarMockupStore();
    expect(store.run("it-xpto-cronograma", "postpone", { date: "2026-10-20" })).toBe(false);
    expect(store.item("it-xpto-cronograma")?.due).toBe("2026-10-13");
    store.resolveDueConflict("it-xpto-cronograma", "2026-10-16");
    expect(store.item("it-xpto-cronograma")).toMatchObject({ due: "2026-10-16", dueConflict: undefined });
    expect(store.run("it-xpto-cronograma", "postpone", { date: "2026-10-20" })).toBe(true);
  });
});

describe("combinado", () => {
  it("suggests the return half way to the due date, on a weekday", () => {
    expect(suggestFollowUp("2026-10-16")).toBe("2026-10-12");
    expect(suggestFollowUp("2026-10-13")).toBe("2026-10-12");
    expect(suggestFollowUp("2026-10-09")).toBe("2026-10-09");
    expect(suggestFollowUp(null)).toBe("2026-10-12");
  });

  it("closes the day over what expired, stalled or went silent", () => {
    expect(closeDayQueue(MOCK_ITEMS, ME_ID).map((entry) => [entry.item.id, entry.reason])).toEqual([
      ["it-comparativo", "Venceu há 2 dias"],
      ["it-parecer-reajuste", "Venceu ontem"],
      ["it-orc-revisar", "Vence hoje"],
      ["it-contrato-clausula", "Retorno combinado para hoje"],
      ["it-mob-cronograma", "Bloqueado · Sem fornecedor contratado, não há data de entrega dos equipamentos"],
      ["it-orc-numeros", "Sem notícias há 3 dias"],
    ]);
  });
});

describe("a prepared message is not a fact", () => {
  it("preparing a message changes nothing; the follow-up is recorded as a fact with author and date", () => {
    const store = new RadarMockupStore();
    const before = JSON.stringify(store.item("it-comparativo"));
    const text = preparedMessage("nudge", store.item("it-comparativo")!, name, "p-carlos");
    expect(text).toBe(
      "Carlos, nosso retorno era em 03/10. Como está “Enviar comparativo de fornecedores”? O que falta para entregar até 06/10 e de que apoio você precisa?"
    );
    expect(JSON.stringify(store.item("it-comparativo"))).toBe(before);

    store.run("it-comparativo", "nudge", { personId: "p-carlos" });
    const item = store.item("it-comparativo")!;
    expect(item.records?.at(-1)).toMatchObject({ kind: "nudge", personId: "p-carlos", by: ME_ID });
    expect(item.records?.at(-1)?.at.startsWith("2026-10-08T09:00")).toBe(true);
    const last = item.activity.at(-1)!;
    expect(last.actorId).toBe(ME_ID);
    expect(last.text).not.toMatch(/enviad/);
    expect(item.followUp).toBe("2026-10-09");
  });

  it("a consultation and a communication are separate records with their author and date", () => {
    const store = new RadarMockupStore();
    store.run("it-xpto-decision", "consult", { personId: "p-ana" });
    const item = store.item("it-xpto-decision")!;
    expect(item.consultedIds).toEqual(["p-ana"]);
    expect(item.records?.at(-1)).toMatchObject({ kind: "consult", personId: "p-ana", by: ME_ID });
    expect(item.informedIds).toEqual([]);
    store.run("it-xpto-decision", "inform", { personId: "p-carlos" });
    expect(store.item("it-xpto-decision")?.informedIds).toEqual(["p-carlos"]);
    expect(store.item("it-xpto-decision")?.records?.at(-1)).toMatchObject({ kind: "inform", personId: "p-carlos" });
  });

  it("a confirmation recorded by the manager is not attributed to the executor", () => {
    const store = new RadarMockupStore();
    store.run("it-contrato-clausula", "confirm", { personId: "p-ana" });
    const item = store.item("it-contrato-clausula")!;
    expect(item.confirmation).toMatchObject({ state: "confirmed", recordedBy: ME_ID });
    expect(item.activity.at(-1)).toMatchObject({ actorId: ME_ID });
    expect(item.activity.at(-1)?.text).toContain("registrou que Ana confirmou");
  });

  it("copying reports failure instead of success", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.reject(new Error("negado")) } });
    expect(await copyText("oi")).toBe(false);
    vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.resolve() } });
    expect(await copyText("oi")).toBe(true);
    vi.stubGlobal("navigator", {});
    expect(await copyText("oi")).toBe(false);
  });
});

describe("verbs", () => {
  it("offers business verbs instead of status changes, and never a way back from closed", () => {
    expect(primaryVerb(byId("it-xpto-decision"), ME_ID, name)?.label).toBe("Decidir");
    expect(primaryVerb(byId("it-comparativo"), ME_ID, name)).toMatchObject({ key: "nudge", label: "Cobrar Carlos" });
    expect(verbsFor(byId("it-xpto-decision"), ME_ID, name).map((verb) => verb.label)).toEqual([
      "Decidir",
      "Consultar Ana",
      "Adiar",
      "Pedir informação",
    ]);
    expect(verbsFor(byId("it-contrato-clausula"), ME_ID, name).map((verb) => verb.label)).toEqual([
      "Registrar confirmação",
      "Concluir",
      "Cobrar Ana",
      "Adiar",
      "Marcar bloqueio",
    ]);
    expect(verbsFor(byId("it-mob-licenca"), ME_ID, name).map((verb) => verb.label)).toEqual(["Comunicar"]);
    expect(verbsFor(byId("it-mob-epi"), ME_ID, name)).toEqual([]);
  });

  it("delegating suggests the return and waits for the executor's confirmation", () => {
    const store = new RadarMockupStore();
    store.run("it-orc-pauta", "delegate", { personId: "p-beatriz", date: "2026-10-16" });
    expect(store.item("it-orc-pauta")).toMatchObject({
      withIds: ["p-beatriz"],
      due: "2026-10-16",
      followUp: "2026-10-12",
      confirmation: { state: "pending" },
    });
  });

  it("postponing keeps the previous due date and the reason", () => {
    const store = new RadarMockupStore();
    store.run("it-parecer-reajuste", "postpone", { date: "2026-10-14", note: "Luiza pediu mais prazo" });
    expect(store.item("it-parecer-reajuste")?.previousDues).toEqual([
      { from: "2026-10-07", to: "2026-10-14", reason: "Luiza pediu mais prazo" },
    ]);
  });

  it("only offers Undo for what the rules can take back", () => {
    expect(
      ["postpone", "delegate", "review", "mitigate", "request_approval"].every((key) => isReversible(key as never))
    ).toBe(true);
    expect(
      [
        "complete",
        "approve",
        "send_back",
        "confirm",
        "nudge",
        "consult",
        "inform",
        "start",
        "block",
        "accept_risk",
      ].some((key) => isReversible(key as never))
    ).toBe(false);
  });
});

describe("Decidir", () => {
  it("shows why the author cannot approve, and approving is refused until the conditions are met", () => {
    const store = new RadarMockupStore();
    const xpto = store.item("it-xpto-decision")!;
    const blockers = approvalBlockers(xpto, ME_ID, store.people);
    expect(blockers.map((blocker) => blocker.key)).toEqual(["author"]);
    expect(blockers[0].fix).toBe("request_approval");
    expect(store.run("it-xpto-decision", "approve")).toBe(false);
    expect(store.item("it-xpto-decision")?.status).toBe("proposed");
    expect(approversOf(xpto, store.people).map((person) => person.id)).toEqual(["p-rafael", "p-beatriz"]);
  });

  it("a requested approval leaves the decision proposed, waiting for review", () => {
    const store = new RadarMockupStore();
    store.run("it-xpto-decision", "request_approval", { personId: "p-beatriz" });
    const xpto = store.item("it-xpto-decision")!;
    expect(xpto.status).toBe("proposed");
    expect(xpto.approval).toMatchObject({ state: "requested", approverId: "p-beatriz", requestedBy: ME_ID });
    expect(approvalBlockers(xpto, ME_ID, store.people).map((blocker) => blocker.key)).toEqual(["author", "pending"]);
  });

  it("evidence is a condition: without it, approval waits for an attachment", () => {
    const store = new RadarMockupStore();
    const decision = store.item("it-treinamento-decision")!;
    expect(approvalBlockers(decision, ME_ID, store.people).map((blocker) => blocker.key)).toEqual(["evidence"]);
    expect(store.run("it-treinamento-decision", "approve")).toBe(false);
    store.run("it-treinamento-decision", "attach_evidence", { note: "Cotação da consultoria, 2 turmas" });
    expect(store.item("it-treinamento-decision")?.evidence.at(-1)).toMatchObject({
      label: "Cotação da consultoria, 2 turmas",
      addedBy: ME_ID,
    });
    expect(store.run("it-treinamento-decision", "approve", { note: "Vale o investimento" })).toBe(true);
    expect(store.item("it-treinamento-decision")?.status).toBe("decided");
  });

  it("an independent decision with evidence is approved, and the dependents hear about it", () => {
    const store = new RadarMockupStore();
    expect(approvalBlockers(store.item("it-erp-cutover")!, ME_ID, store.people)).toEqual([]);
    expect(store.run("it-erp-cutover", "approve", { note: "Seguimos com 01/12" })).toBe(true);
    expect(ids(store.hojeMine.views!.informar)).toContain("it-erp-cutover");
    store.run("it-erp-cutover", "inform");
    expect(ids(store.hojeMine.views!.informar)).not.toContain("it-erp-cutover");
  });

  it("sending a proposal back is not rejecting a decision: it stays proposed, with the reason", () => {
    const store = new RadarMockupStore();
    expect(store.run("it-erp-cutover", "send_back")).toBe(false);
    expect(store.run("it-erp-cutover", "send_back", { note: "Falta o plano de reversão" })).toBe(true);
    expect(store.item("it-erp-cutover")).toMatchObject({
      status: "proposed",
      approval: { state: "returned", reason: "Falta o plano de reversão" },
    });
    expect(STATUSES_BY_KIND.decision).toEqual(["proposed", "decided"]);
  });
});

describe("Concluir", () => {
  it("concluding records valid evidence, new or already attached", () => {
    const store = new RadarMockupStore();
    expect(store.run("it-orc-revisar", "complete")).toBe(false);
    expect(store.item("it-orc-revisar")?.status).toBe("todo");
    expect(store.run("it-orc-revisar", "complete", { note: "Premissas validadas com Maria, 08/10" })).toBe(true);
    const item = store.item("it-orc-revisar")!;
    expect(item).toMatchObject({ status: "done", outcome: "Premissas validadas com Maria, 08/10" });
    expect(item.evidence.at(-1)).toMatchObject({ addedBy: ME_ID, label: "Premissas validadas com Maria, 08/10" });
    expect(store.run("it-parecer-reajuste", "complete", { evidenceId: "ev-1" })).toBe(true);
    expect(store.item("it-parecer-reajuste")).toMatchObject({
      status: "done",
      outcome: "Minuta de aditivo do contrato de manutenção",
    });
  });

  it("the state selector and the board follow the same rules as the buttons", () => {
    expect(statusMove(byId("it-orc-revisar"), "done")).toMatchObject({ kind: "flow", via: "complete" });
    expect(statusMove(byId("it-orc-revisar"), "blocked")).toMatchObject({ kind: "flow", via: "block" });
    expect(statusMove(byId("it-xpto-decision"), "decided")).toMatchObject({ kind: "flow", via: "decide" });
    expect(statusMove(byId("it-mob-epi"), "todo")).toMatchObject({ kind: "refused" });
    expect(statusMove(byId("it-mob-licenca"), "proposed")).toMatchObject({ kind: "refused" });
    expect(statusMove(byId("it-comparativo"), "todo")).toMatchObject({ kind: "refused" });
    expect(statusMove(byId("it-orc-revisar"), "cancelled")).toMatchObject({ kind: "refused" });
    expect(statusMove(byId("it-orc-pauta"), "waiting")).toMatchObject({ kind: "refused" });
    const store = new RadarMockupStore();
    expect(store.moveStatus("it-orc-revisar", "done").kind).toBe("flow");
    expect(store.item("it-orc-revisar")?.status).toBe("todo");
    expect(store.moveStatus("it-orc-revisar", "in_progress").kind).toBe("direct");
    expect(store.item("it-orc-revisar")?.status).toBe("in_progress");
    expect(store.moveStatus("it-mob-epi", "todo").kind).toBe("refused");
    expect(store.item("it-mob-epi")?.status).toBe("done");
  });
});

describe("Desfazer undoes only what the action did", () => {
  it("undoing A keeps B created afterwards", () => {
    const store = new RadarMockupStore();
    const a = store.track(() =>
      store.run("it-parecer-reajuste", "postpone", { date: "2026-10-14", note: "mais prazo" })
    );
    const created = store.capture({
      title: "Pedir cotação à Delta",
      kind: "action",
      due: "2026-10-09",
      personIds: [],
      projectId: null,
    });
    store.setPriority("it-comparativo", "low");
    const result = a.undo();
    expect(result.conflicts).toEqual([]);
    expect(store.item("it-parecer-reajuste")).toMatchObject({ due: "2026-10-07" });
    expect(store.item("it-parecer-reajuste")?.previousDues).toBeUndefined();
    expect(store.item(created.id)).toBeDefined();
    expect(store.item("it-comparativo")?.priority).toBe("low");
    // the history is not erased: undoing is one more entry
    expect(store.item("it-parecer-reajuste")?.activity.at(-1)?.text).toBe("desfez uma alteração");
  });

  it("what changed again after the action is kept, and reported", () => {
    const store = new RadarMockupStore();
    const a = store.track(() => store.run("it-parecer-reajuste", "postpone", { date: "2026-10-14" }));
    store.setDue("it-parecer-reajuste", "2026-10-20");
    const result = a.undo();
    expect(store.item("it-parecer-reajuste")?.due).toBe("2026-10-20");
    expect(result.conflicts.length).toBeGreaterThan(0);
  });

  it("undoing a creation removes it only while it is untouched", () => {
    const store = new RadarMockupStore();
    const a = store.track(() => store.run("it-risco-fornecedor", "mitigate", { note: "Segunda fonte para a XPTO" }));
    const created = store.items.find((item) => item.title === "Segunda fonte para a XPTO")!;
    expect(store.item("it-risco-fornecedor")?.status).toBe("mitigating");
    a.undo();
    expect(store.item(created.id)).toBeUndefined();
    expect(store.item("it-risco-fornecedor")?.status).toBe("identified");

    const b = store.track(() => store.run("it-risco-fornecedor", "mitigate", { note: "Outra ação" }));
    const kept = store.items.find((item) => item.title === "Outra ação")!;
    store.setPriority(kept.id, "urgent");
    const result = b.undo();
    expect(store.item(kept.id)).toBeDefined();
    expect(result.conflicts.length).toBeGreaterThan(0);
  });

  it("a triaged Inbox entry comes back where it was", () => {
    const store = new RadarMockupStore();
    const index = store.inbox.findIndex((entry) => entry.id === "in-request");
    const a = store.track(() => store.refuse("in-request", "Duplicado"));
    store.capture({ title: "Captura nova", kind: null, due: null, personIds: [], projectId: null });
    expect(store.inbox.some((entry) => entry.id === "in-request")).toBe(false);
    a.undo();
    expect(store.inbox.some((entry) => entry.id === "in-request")).toBe(true);
    expect(store.inbox.some((entry) => entry.title === "Captura nova")).toBe(true);
    expect(store.feedback).toEqual([]);
    expect(index).toBeGreaterThanOrEqual(0);
  });

  it("reports nothing changed when the action did not apply", () => {
    const store = new RadarMockupStore();
    const a = store.track(() => store.run("it-xpto-decision", "approve"));
    expect(a.changed).toBe(false);
  });
});

describe("rituals follow the chosen times and what was already done", () => {
  it("offers opening from the chosen time until closing, and closing from then on", () => {
    expect(
      ritualFor({ date: "2026-10-08", time: "08:00" }, PREFS, { ...NO_MARKS, weeklyOn: "2026-10-05" }).now
    ).toBeNull();
    // never reviewed at all: the weekly review is due before anything else
    expect(ritualFor({ date: "2026-10-08", time: "09:00" }, PREFS, NO_MARKS).now).toBe("revisao");
    expect(ritualFor({ date: "2026-10-08", time: "09:00" }, PREFS, { ...NO_MARKS, weeklyOn: "2026-10-05" }).now).toBe(
      "abrir"
    );
    expect(
      ritualFor(
        { date: "2026-10-08", time: "09:00" },
        { ...PREFS, abrir: "10:00" },
        { ...NO_MARKS, weeklyOn: "2026-10-05" }
      ).now
    ).toBeNull();
    const marks = { openedOn: "2026-10-08", closedOn: null, weeklyOn: "2026-10-05" };
    expect(ritualFor({ date: "2026-10-08", time: "13:00" }, PREFS, marks).now).toBeNull();
    expect(ritualFor({ date: "2026-10-08", time: "17:30" }, PREFS, marks).now).toBe("fechar");
    expect(
      ritualFor({ date: "2026-10-08", time: "18:00" }, PREFS, { ...marks, closedOn: "2026-10-08" }).now
    ).toBeNull();
  });

  it("a weekly review done in the week is no longer pending, even on Friday after the slot", () => {
    const friday = { date: "2026-10-09", time: "17:00" };
    expect(ritualFor(friday, PREFS, { openedOn: "2026-10-09", closedOn: null, weeklyOn: "2026-10-05" })).toMatchObject({
      reviewDue: false,
      weeklyDoneOn: "2026-10-05",
    });
    expect(ritualFor(friday, PREFS, { openedOn: "2026-10-09", closedOn: null, weeklyOn: "2026-09-30" })).toMatchObject({
      now: "revisao",
      reviewDue: true,
    });
    expect(ritualFor(friday, PREFS, { openedOn: "2026-10-09", closedOn: null, weeklyOn: "2026-10-09" }).reviewDue).toBe(
      false
    );
  });

  it("the weekly slot chosen moves the recommendation", () => {
    const monday = { ...PREFS, semanal: "seg 08:30" };
    expect(ritualFor({ date: "2026-10-12", time: "09:00" }, monday, { ...NO_MARKS, weeklyOn: "2026-10-05" }).now).toBe(
      "revisao"
    );
    expect(
      ritualFor({ date: "2026-10-12", time: "08:00" }, monday, { ...NO_MARKS, weeklyOn: "2026-10-05" }).reviewDue
    ).toBe(false);
  });

  it("opening, closing and the weekly review are kept apart, and a day is not carried over", () => {
    const store = new RadarMockupStore();
    expect(store.ritualNow.now).toBe("abrir");
    store.completeOpenDay(["it-xpto-decision", "it-comparativo"]);
    expect(store.marks).toMatchObject({ openedOn: "2026-10-08", closedOn: "2026-10-05", weeklyOn: "2026-10-05" });
    expect(store.ritualNow.now).toBeNull();
    store.advanceClock("evening");
    expect(store.ritualNow.now).toBe("fechar");
    store.completeCloseDay("it-erp-cutover");
    expect(store.ritualNow.now).toBeNull();
    store.advanceClock("nextDay");
    expect(store.today).toBe("2026-10-09");
    expect(store.hasFocusToday).toBe(false);
    expect(store.focusItems).toEqual([]);
    expect(store.ritualNow.now).toBe("abrir");
    expect(store.tomorrowFirstItem?.id).toBe("it-erp-cutover");
  });

  it("preferences are only preferences: saving them books nothing", () => {
    const store = new RadarMockupStore();
    store.startFresh();
    store.setRitualTime("abrir", "09:00");
    expect(store.onboarding.prefsSaved).toBe(false);
    store.savePreferences();
    expect(store.onboarding.prefsSaved).toBe(true);
    expect(store.ritualTimes.abrir).toBe("09:00");
  });
});

describe("Foco de hoje", () => {
  it("separates focus from alerts, without duplicates, and the counter matches the rows", () => {
    const store = new RadarMockupStore();
    store.completeOpenDay(["it-xpto-decision", "it-comparativo"]);
    const { focusOpen, focusDone, alerts, count } = store.atencao;
    expect(ids(focusOpen)).toEqual(["it-xpto-decision", "it-comparativo"]);
    expect(focusDone).toEqual([]);
    expect(alerts.some((entry) => store.isFocus(entry.item.id))).toBe(false);
    expect(count).toBe(focusOpen.length + alerts.length);
    expect(count).toBe(store.hojeMine.attention.length);
  });

  it("a fulfilled focus is marked as such and leaves the count", () => {
    const store = new RadarMockupStore();
    store.completeOpenDay(["it-comparativo", "it-orc-revisar"]);
    const before = store.atencao.count;
    store.run("it-comparativo", "complete", { note: "Tabela recebida de Carlos" });
    const { focusOpen, focusDone, count } = store.atencao;
    expect(ids(focusDone)).toEqual(["it-comparativo"]);
    expect(ids(focusOpen)).toEqual(["it-orc-revisar"]);
    expect(count).toBe(before - 1);
  });
});

describe("projects", () => {
  it("shows the result, not the share of tasks, and flags a project without a next action", () => {
    expect(resultProgress(MOCK_PROJECTS[0].result)).toBe(39);
    expect(resultProgress(MOCK_PROJECTS[1].result)).toBeNull();
    expect(projectNextAction(MOCK_ITEMS, "pr-mob")?.id).toBe("it-comparativo");
    expect(projectNextAction(MOCK_ITEMS, "pr-ia")).toBeNull();
  });
});

describe("capture", () => {
  it("reads kind, date, person and project from one line", () => {
    expect(parseCapture("Cobrar Carlos sobre o orçamento até sexta", MOCK_PEOPLE, MOCK_PROJECTS, ME_ID)).toEqual({
      title: "Cobrar Carlos sobre o orçamento até sexta",
      kind: "action",
      due: "2026-10-09",
      personIds: ["p-carlos"],
      projectId: "pr-orc",
    });
    expect(parseCapture("Decidir amanhã se seguimos com a XPTO", MOCK_PEOPLE, MOCK_PROJECTS, ME_ID)).toMatchObject({
      kind: "decision",
      due: "2026-10-09",
      projectId: "pr-mob",
    });
  });

  it("asks one question about the gap, as in the Metodologia's example", () => {
    const guess = parseCapture(
      "Carlos organizar a terceirização do suporte até o fim do mês",
      MOCK_PEOPLE,
      MOCK_PROJECTS,
      ME_ID
    );
    expect(guess).toMatchObject({ kind: "action", due: "2026-10-31", personIds: ["p-carlos"] });
    expect(captureGap(guess, name)).toEqual({
      field: "followUp",
      text: "Quando você quer revisar isso com Carlos?",
      options: [
        { label: "amanhã", value: "2026-10-09" },
        { label: "20 out (meio do prazo)", value: "2026-10-20" },
        { label: "próxima segunda", value: "2026-10-12" },
      ],
    });
  });

  it("leaves unrecognized text for the Inbox", () => {
    expect(parseCapture("Ideia para o comitê de IA #gia", MOCK_PEOPLE, MOCK_PROJECTS, ME_ID)).toEqual({
      title: "Ideia para o comitê de IA",
      kind: null,
      due: null,
      personIds: [],
      projectId: "pr-ia",
    });
  });
});

describe("Inbox: what the agent proposes today", () => {
  it("accepts the relation and the mitigation on their own, and one failing does not undo the other", () => {
    const store = new RadarMockupStore();
    expect(store.acceptSuggestionPart("in-agent-link", "relation").ok).toBe(true);
    expect(store.item("it-risco-fornecedor")?.threatensIds).toEqual(["pr-orc"]);
    expect(store.inbox.some((entry) => entry.id === "in-agent-link")).toBe(true);

    store.toggleDemo("failMitigation");
    const items = store.items.length;
    const failed = store.acceptSuggestionPart("in-agent-link", "mitigation");
    expect(failed.ok).toBe(false);
    expect(store.items.length).toBe(items);
    const proposal = store.inbox.find((entry) => entry.id === "in-agent-link")!.suggestion!;
    expect(proposal.relation?.state).toBe("accepted");
    expect(proposal.mitigation?.state).toBe("failed");

    expect(store.acceptSuggestionPart("in-agent-link", "mitigation").ok).toBe(true);
    expect(store.items.length).toBe(items + 1);
    expect(store.item("it-risco-fornecedor")?.status).toBe("mitigating");
    expect(store.inbox.some((entry) => entry.id === "in-agent-link")).toBe(false);
  });

  it("keeps review: rejecting records the reason, editing makes a new version", () => {
    const store = new RadarMockupStore();
    store.rejectSuggestionPart("in-agent-link", "relation", "redundante");
    expect(store.feedback.at(-1)).toMatchObject({ entryId: "in-agent-link:relation", reason: "redundante" });
    store.editSuggestion("in-agent-link", { mitigationTitle: "Reservar 8% de contingência" });
    const proposal = store.inbox.find((entry) => entry.id === "in-agent-link")!.suggestion!;
    expect(proposal).toMatchObject({ version: 2 });
    expect(proposal.mitigation?.title).toBe("Reservar 8% de contingência");
    expect(proposal.relation?.state).toBe("rejected");
  });

  it("the agent unavailable says so instead of inventing a review", () => {
    const store = new RadarMockupStore();
    store.toggleDemo("agentDown");
    const inbox = store.inbox.length;
    expect(store.reviewProjectRisks("pr-mob")).toMatchObject({ ok: false });
    expect(store.inbox.length).toBe(inbox);
    store.toggleDemo("agentDown");
    expect(store.reviewProjectRisks("pr-mob").ok).toBe(true);
    expect(store.inbox.length).toBe(inbox + 1);
  });
});

describe("first use", () => {
  it("starts empty with the vault's context, or from nothing without it", () => {
    const store = new RadarMockupStore();
    store.startFresh({ vault: true });
    expect(store.items).toEqual([]);
    expect(store.people.length).toBeGreaterThan(1);
    store.startFresh({ vault: false });
    expect(store.people.map((person) => person.id)).toEqual([ME_ID]);
    expect(store.projects).toEqual([]);
    store.addProject("Obra Norte");
    store.addPerson("Paula Reis", "externa", "Paula & Co");
    expect(store.projects[0]).toMatchObject({ title: "Obra Norte" });
    expect(store.people.at(-1)).toMatchObject({
      display_name: "Paula",
      affiliation: "externa",
      organization: "Paula & Co",
    });
    store.setDraft("Cobrar Paula sobre o laudo até sexta #obra");
    expect(store.onboardingRows[0].guess).toMatchObject({ kind: "action", personIds: [store.people.at(-1)!.id] });
  });

  it("the manager corrects what was inferred before anything is created", () => {
    const store = new RadarMockupStore();
    store.startFresh();
    store.setDraft("Cobrar Carlos sobre o comparativo até sexta");
    const [row] = store.onboardingRows;
    store.correctRow(row.key, { kind: "decision", personIds: ["p-maria"], projectId: "pr-orc", due: "2026-10-15" });
    const [result] = store.organizeDraft();
    const item = store.item(result.id!)!;
    expect(item).toMatchObject({ kind: "decision", withIds: ["p-maria"], projectId: "pr-orc", due: "2026-10-15" });
  });

  it("a partial failure shows each result, and retrying never duplicates", () => {
    const store = new RadarMockupStore();
    store.startFresh();
    store.setDraft(
      "Cobrar Carlos sobre o comparativo até sexta\nVer com jurídico a cláusula de reajuste\nEnviar relatório à diretoria até sexta"
    );
    store.toggleDemo("failBatchLine");
    const first = store.organizeDraft();
    expect(first.map((entry) => entry.status)).toEqual(["created", "failed", "created"]);
    expect(store.items).toHaveLength(2);
    const again = store.organizeDraft();
    expect(again.map((entry) => entry.status)).toEqual(["created", "created", "created"]);
    expect(store.items).toHaveLength(3);
    store.organizeDraft();
    expect(store.items).toHaveLength(3);
  });

  it("the progress stays in the store, and a missing 'how we will know' stays a visible gap", () => {
    const store = new RadarMockupStore();
    store.startFresh();
    store.confirmContext();
    store.setDraft("Cobrar Carlos até sexta");
    store.addWeekResult("Fornecedor contratado", "");
    expect(store.onboarding).toMatchObject({ contextConfirmed: true, draft: "Cobrar Carlos até sexta" });
    expect(store.weekResults[0].howWeKnow).toBe("");
    store.setWeekResultHow(store.weekResults[0].id, "Contrato assinado");
    expect(store.weekResults[0].howWeKnow).toBe("Contrato assinado");
  });

  it("the weekly review is not due on the first day", () => {
    const store = new RadarMockupStore();
    store.startFresh();
    store.finishFirstUse();
    expect(store.ritualNow.reviewDue).toBe(false);
  });
});

describe("the open item lives in the address", () => {
  it("asks the URL to change, and only the URL changes it", () => {
    const store = new RadarMockupStore();
    const writes: (string | null)[] = [];
    store.bindUrl((id) => writes.push(id));
    store.openItemById("it-comparativo", { key: "nudge", personId: "p-carlos" });
    expect(writes).toEqual(["it-comparativo"]);
    expect(store.openItemId).toBeNull();
    store.syncOpenItem("it-comparativo");
    expect(store.openItem?.id).toBe("it-comparativo");
    expect(store.takePendingVerb()).toMatchObject({ key: "nudge" });
    store.closeItem();
    expect(writes).toEqual(["it-comparativo", null]);
    store.syncOpenItem(null);
    expect(store.openItem).toBeUndefined();
  });

  it("a link to an item that is not there opens nothing instead of breaking", () => {
    const store = new RadarMockupStore();
    store.syncOpenItem("it-que-nao-existe");
    expect(store.openItemId).toBe("it-que-nao-existe");
    expect(store.openItem).toBeUndefined();
  });
});

describe("demonstration scenarios", () => {
  it("read only changes nothing, and incomplete data is never read as 'no pending'", () => {
    const store = new RadarMockupStore();
    store.setScenario("readonly");
    expect(store.readOnly).toBe(true);
    expect(store.run("it-orc-revisar", "start")).toBe(false);
    expect(store.moveStatus("it-orc-revisar", "in_progress").kind).toBe("refused");
    expect(store.item("it-orc-revisar")?.status).toBe("todo");
    store.setScenario("partial");
    expect(store.complete).toBe(false);
    store.setScenario("normal");
    expect(store.complete).toBe(true);
  });

  it("pending approval is an operation waiting for review, visible on the item", () => {
    const item = new RadarMockupStore();
    item.run("it-xpto-decision", "request_approval", { personId: "p-rafael" });
    expect(item.item("it-xpto-decision")?.approval?.state).toBe("requested");
    expect(attentionFor(item.item("it-xpto-decision")!, item.items, name)?.reason).toContain("Decisão necessária");
  });
});
