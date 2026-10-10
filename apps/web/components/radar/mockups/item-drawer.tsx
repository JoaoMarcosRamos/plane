/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Input } from "@makeplane/propel/components/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { TextArea } from "@makeplane/propel/components/text-area";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import {
  AiStar1Outline,
  ArrowNarrowRightOutline,
  CheckSquareOutline,
  DueDateOutline,
  FlagOutline,
  MembersOutline,
  MoreHorizontalOutline,
  NewTabArrowOutline,
  PriorityOutline,
  ProjectsOutline,
  RefreshOutline,
  StateOutline,
  UserOutline,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import { DateSelect, MemberSelect, PrioritySelect, StateSelect } from "@plane/blocks/property-select";
import type { StateOption } from "@plane/blocks/property-select";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { cn } from "@plane/utils";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { currentToday } from "./mock-data";
import type { TMockItem, TMockProject, TMockRecord } from "./mock-data";
import type { TMessageKind, TVerb, TVerbKey } from "./interaction-model";
import {
  KIND_LABEL,
  STATE_GROUP,
  STATUSES_BY_KIND,
  STATUS_LABEL,
  addDays,
  attentionFor,
  dayMonth,
  followUpState,
  fromLocalDate,
  gapsOf,
  isOpen,
  nextMonday,
  pendingConsults,
  pendingInforms,
  preparedMessage,
  isReversible,
  silentDays,
  statusColor,
  statusMove,
  suggestFollowUp,
  toLocalDate,
  verbsFor,
  waitingOnOthers,
} from "./interaction-model";
import { CompleteComposer, DecideComposer, EvidenceList } from "./composers";
import type { TRunVerb } from "./composers";
import { useRadarMockup } from "./provider";
import { KindIcon, PersonAvatar, PreparedMessage, Signal, commit, useMemberOptions, withUndo } from "./ui";

/** Verbs that ask for one line before running. Concluding and deciding have composers of their own. */
const TEXT_COMPOSER: Partial<
  Record<TVerbKey, { placeholder: string; confirm: string; toast: string; required?: boolean }>
> = {
  unblock: { placeholder: "O que destravou?", confirm: "Desbloquear", toast: "Desbloqueado" },
  ask: { placeholder: "O que falta saber?", confirm: "Registrar pedido", toast: "Pedido de informação registrado" },
  review: { placeholder: "Como está o risco? (opcional)", confirm: "Registrar revisão", toast: "Revisão registrada" },
  accept_risk: {
    placeholder: "Por que aceitar? O risco continua em acompanhamento.",
    confirm: "Aceitar o risco",
    toast: "Risco aceito · segue em acompanhamento",
  },
  mitigate: {
    placeholder: "Título da ação de mitigação",
    confirm: "Criar ação",
    toast: "Ação de mitigação criada",
    required: true,
  },
  block: { placeholder: "O que impede avançar?", confirm: "Marcar como bloqueado", toast: "Marcado como bloqueado" },
};

/** Preparing a message and registering that the conversation happened are two different steps. */
const MESSAGE_VERBS: Partial<Record<TVerbKey, { kind: TMessageKind; record: string; toast: string }>> = {
  nudge: { kind: "nudge", record: "Registrar cobrança realizada", toast: "Cobrança registrada · novo retorno amanhã" },
  consult: { kind: "consult", record: "Registrar consulta realizada", toast: "Consulta registrada" },
  inform: { kind: "inform", record: "Registrar comunicação", toast: "Comunicação registrada" },
};

const INSTANT_TOAST: Partial<Record<TVerbKey, string>> = {
  start: "Iniciado",
  resume: "Retomado",
  confirm: "Confirmação registrada por você",
};

/** "consultado por você em 07/10": a recorded fact says who recorded it and when. */
const recordText = (item: TMockItem, kind: TMockRecord["kind"], personId: string, name: (id: string) => string) => {
  const record = (item.records ?? []).find((entry) => entry.kind === kind && entry.personId === personId);
  const verb = kind === "consult" ? "consultado" : kind === "inform" ? "comunicado" : "registrado";
  return record ? `${verb} por ${name(record.by)} em ${dayMonth(record.at.slice(0, 10))}` : `${verb}`;
};

/** Click to edit; empty shows "a confirmar" and never blocks anything. */
function InlineText({
  value,
  placeholder,
  onSave,
}: {
  value?: string;
  placeholder: string;
  onSave: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  if (editing)
    return (
      <Input
        size="md"
        // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
        autoFocus
        value={draft}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          onSave(draft);
          setEditing(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") (event.target as HTMLInputElement).blur();
          if (event.key === "Escape") {
            setDraft(value ?? "");
            setEditing(false);
          }
        }}
      />
    );
  return (
    <button
      type="button"
      onClick={() => {
        setDraft(value ?? "");
        setEditing(true);
      }}
      className="w-full rounded-md px-2 py-1 text-left text-13 text-primary hover:bg-layer-transparent-hover"
    >
      {value ? value : <Badge variant="warning" size="sm" label="a confirmar" />}
    </button>
  );
}

const PersonWithState = observer(function PersonWithState({
  personId,
  done,
  doneLabel,
  pendingLabel,
  actionLabel,
  onAction,
}: {
  personId: string;
  done: boolean;
  doneLabel: string;
  pendingLabel: string;
  actionLabel: string;
  onAction: () => void;
}) {
  const store = useRadarMockup();
  return (
    <div className="flex items-center gap-2 py-0.5">
      <PersonAvatar personId={personId} size="xs" />
      <span className="text-13 text-primary">{store.person(personId)?.name}</span>
      <Badge variant={done ? "success" : "warning"} size="sm" label={done ? doneLabel : pendingLabel} />
      {!done && actionLabel && (
        <button type="button" className="ml-auto text-12 text-accent-primary hover:underline" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
});

function Section({ title, trailing, children }: { title: string; trailing?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-13 font-semibold text-primary">{title}</h3>
        {trailing}
      </div>
      {children}
    </section>
  );
}

const ItemDetail = observer(function ItemDetail({ item }: { item: TMockItem }) {
  const store = useRadarMockup();
  const members = useMemberOptions();
  const [composer, setComposer] = useState<TVerb | null>(null);
  const [note, setNote] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [followUp, setFollowUp] = useState<string | null>(null);
  const [personId, setPersonId] = useState<string | null>(null);
  const [autonomy, setAutonomy] = useState("");
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState<{ personId: string; text: string } | null>(null);
  const [involving, setInvolving] = useState(false);

  const verbs = verbsFor(item, store.meId, store.personName);
  const [primary, ...secondary] = verbs;
  const visible = secondary.slice(0, 2);
  const overflow = secondary.slice(2);
  const open = isOpen(item.status);
  const attention = attentionFor(item, store.items, store.personName);
  const project = store.project(item.projectId);
  const dependsOn = store.items.filter((other) => item.dependsOnIds.includes(other.id));
  const unlocks = store.items.filter((other) => other.dependsOnIds.includes(item.id));
  const silent = silentDays(item, store.meId);
  const follow = followUpState(item);
  const consults = pendingConsults(item);
  const informs = pendingInforms(item);
  const delegated = waitingOnOthers(item, store.meId);
  const gaps = gapsOf(item);
  // Only the states this item may actually go to, with the same rules as the buttons (no reopening, no free "done").
  const statusOptions: StateOption[] = STATUSES_BY_KIND[item.kind]
    .filter((status) => status === item.status || statusMove(item, status).kind !== "refused")
    .map((status) => ({
      id: status,
      name: STATUS_LABEL[status],
      color: statusColor(status),
      group: STATE_GROUP[status],
    }));

  /** The selector never writes a state: it asks the rules, and hands evidence, reason or examination to its step. */
  const requestStatus = (to: TMockItem["status"]) => {
    const result = store.moveStatus(item.id, to);
    if (result.kind === "flow") {
      choose({ key: result.via, label: "" });
      setToast({ type: "info", title: "Falta um passo", message: result.note });
    } else if (result.kind === "refused")
      setToast({ type: "info", title: "Esse movimento não está disponível", message: result.reason });
    else if (result.kind === "direct")
      setToast({ type: "success", title: `Estado: ${STATUS_LABEL[to]}`, message: item.title });
  };

  const choose = (verb: TVerb) => {
    setNote("");
    setNotice(null);
    const target = verb.personId ?? (verb.key === "inform" ? informs[0] : item.withIds[0]);
    if (INSTANT_TOAST[verb.key]) {
      setComposer(null);
      commit(store, { title: INSTANT_TOAST[verb.key] ?? verb.label, message: item.title }, () =>
        store.run(item.id, verb.key, { personId: target })
      );
      return;
    }
    if (verb.key === "postpone" && item.dueConflict) {
      setComposer(null);
      setToast({
        type: "info",
        title: "Resolva a divergência antes de adiar",
        message: "Há dois prazos para este combinado. Escolha o que vale em Prazo.",
      });
      return;
    }
    const spec = MESSAGE_VERBS[verb.key];
    if (spec && target) setMessage(preparedMessage(spec.kind, item, store.personName, target));
    if (verb.key === "delegate") {
      const due = item.due ?? addDays(currentToday(), 5);
      setPersonId(null);
      setDate(due);
      setFollowUp(suggestFollowUp(due));
      setAutonomy(item.autonomy ?? "");
    }
    if (verb.key === "postpone") setDate(nextMonday(item.due && item.due > currentToday() ? item.due : currentToday()));
    if (verb.key === "mitigate") setNote(`Mitigar: ${item.title}`);
    setComposer({ ...verb, personId: target });
  };

  // A row may hand the item over with a verb ready (Cobrar, Decidir, Concluir…).
  useEffect(() => {
    const pending = store.takePendingVerb();
    if (pending) {
      const verb = verbs.find((candidate) => candidate.key === pending.key) ?? { ...pending, label: "" };
      choose({ ...verb, personId: pending.personId ?? verb.personId });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Every confirmation says what it did. Only what the rules can take back offers "Desfazer"; the rest is
   * recorded for good, and a mistake is corrected with a new record.
   */
  const finish = (
    key: TVerbKey,
    title: string,
    extra: string | undefined,
    change: () => boolean | void,
    keepComposer = false
  ) => {
    const toast = { title, message: extra ?? item.title };
    if (isReversible(key)) withUndo(store, toast, change);
    else commit(store, toast, change);
    if (!keepComposer) {
      setComposer(null);
      setNote("");
    }
  };

  /** The composers of Decidir and Concluir hand their action here. */
  const runVerb: TRunVerb = (key, title, input, extra) => {
    const informsNow = pendingInforms(item);
    const pendingNote =
      (key === "approve" || key === "complete") && informsNow.length
        ? `Falta comunicar ${informsNow.map(store.personName).join(", ")}`
        : undefined;
    finish(key, title, extra ?? pendingNote, () => store.run(item.id, key, input), key === "attach_evidence");
  };

  /** Registers the fact that the conversation happened: author and date come from the record, not the message. */
  const recordFact = () => {
    if (!composer) return;
    const key = composer.key;
    const spec = MESSAGE_VERBS[key];
    if (!spec) return;
    finish(key, spec.toast, `Registrado por você em ${dayMonth(currentToday())}.`, () =>
      store.run(item.id, key, { personId: composer.personId })
    );
  };

  const confirm = () => {
    if (!composer) return;
    const key = composer.key;
    if (key === "delegate") {
      if (!personId) return;
      finish(
        key,
        `Delegado a ${store.personName(personId)}`,
        `Retorno ${followUp ? dayMonth(followUp) : "a confirmar"} · aguardando confirmação`,
        () => store.run(item.id, "delegate", { personId, date, followUp, autonomy })
      );
      return;
    }
    if (key === "postpone") {
      const previous = item.due;
      finish(
        key,
        "Adiado",
        `Novo prazo ${date ? dayMonth(date) : "sem data"} · prazo anterior guardado no histórico`,
        () => store.run(item.id, "postpone", { date, note })
      );
      const affected = item.withIds.find((id) => id !== store.meId);
      if (affected)
        setNotice({
          personId: affected,
          text: preparedMessage("postpone", item, store.personName, affected, {
            from: previous ?? undefined,
            to: date ?? undefined,
            note,
          }),
        });
      return;
    }
    const spec = TEXT_COMPOSER[key];
    if (spec?.required && !note.trim()) return;
    finish(key, spec?.toast ?? composer.label, item.title, () => store.run(item.id, key, { note }));
  };

  const verbButton = (verb: TVerb, variant: "primary" | "secondary") => (
    <Button
      key={verb.key + (verb.personId ?? "")}
      variant={composer?.key === verb.key ? "primary" : variant}
      size="md"
      stretch="auto"
      label={verb.label}
      onClick={() => choose(verb)}
    />
  );

  // The responsible person is shown up front only when it is not you (it usually is).
  const responde =
    item.ownerId !== store.meId ? (
      <SidebarPropertyListItem icon={UserOutline} label="Responde">
        <MemberSelect
          variant="select-ghost-md"
          getValues={members.getValues}
          value={members.find(item.ownerId)}
          onChange={(id) => store.setOwner(item.id, id)}
        />
      </SidebarPropertyListItem>
    ) : null;

  const textSpec = composer ? TEXT_COMPOSER[composer.key] : undefined;
  const messageSpec = composer ? MESSAGE_VERBS[composer.key] : undefined;

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <Tooltip label="Fechar" shortcut="Esc">
            <IconButton
              variant="ghost"
              size="md"
              aria-label="Fechar"
              icon={<Icon icon={ArrowNarrowRightOutline} />}
              onClick={store.closeItem}
            />
          </Tooltip>
          <span className="text-12 text-tertiary">
            {KIND_LABEL[item.kind]}
            {project ? ` · ${project.title}` : ""}
          </span>
        </div>
        <Menu>
          <MenuTrigger
            render={
              <IconButton
                variant="ghost"
                size="md"
                aria-label="Mais opções"
                icon={<Icon icon={MoreHorizontalOutline} />}
              />
            }
          />
          <MenuContent side="bottom" align="end">
            {overflow.map((verb) => (
              <MenuItem key={verb.key + (verb.personId ?? "")} label={verb.label} onClick={() => choose(verb)} />
            ))}
            <MenuItem
              icon={<Icon icon={NewTabArrowOutline} />}
              label="Abrir página completa"
              onClick={() =>
                setToast({
                  type: "info",
                  title: "Página completa",
                  message: "Disponível no produto: abre o item inteiro.",
                })
              }
            />
          </MenuContent>
        </Menu>
      </div>
      <div className="vertical-scrollbar scrollbar-md min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-6 px-8 py-5 pb-10">
          <div className="flex items-start gap-3">
            <KindIcon kind={item.kind} severity={attention?.severity ?? "neutral"} />
            <h2 className="text-18 leading-7 font-semibold text-primary">{item.title}</h2>
          </div>

          {/* why now, and the honest signals */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span
              className={cn("text-13 font-medium", {
                "text-danger-primary": attention?.severity === "critical",
                "text-warning-primary": attention?.severity === "warning",
                "text-secondary": !attention,
              })}
            >
              {attention?.reason ??
                (!open && informs.length
                  ? `${STATUS_LABEL[item.status]} · falta comunicar`
                  : STATUS_LABEL[item.status])}
            </span>
            {silent && (
              <Signal
                label={`sem notícias de ${item.withIds.map(store.personName).join(", ")} há ${silent} dias`}
                tone="warn"
              />
            )}
            {follow && !attention?.reason.startsWith("Retorno") && <Signal label={follow.label} tone={follow.tone} />}
          </div>

          {/* business verbs (§11) */}
          {store.readOnly && (
            <p className="rounded-md bg-layer-2 px-3 py-2 text-12 text-secondary">
              Somente leitura: seu acesso permite consultar este item, não alterá-lo.
            </p>
          )}
          {primary && (
            <div
              className="flex flex-col gap-3"
              inert={store.readOnly}
              style={store.readOnly ? { opacity: 0.55 } : undefined}
            >
              <div className="flex flex-wrap gap-2">
                {verbButton(primary, "primary")}
                {visible.map((verb) => verbButton(verb, "secondary"))}
              </div>

              {composer?.key === "decide" && consults.length > 0 && (
                <div className="flex flex-col gap-2 rounded-lg border border-warning-subtle bg-warning-subtle p-3">
                  <span className="text-13 text-primary">
                    <b>Antes de decidir:</b> {consults.map((id) => store.person(id)?.name).join(", ")} ainda não{" "}
                    {consults.length > 1 ? "foram consultados" : "foi consultado(a)"}.
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label="Preparar consulta"
                      onClick={() => choose({ key: "consult", label: "Consultar", personId: consults[0] })}
                    />
                    <span className="self-center text-12 text-tertiary">ou decida assim mesmo abaixo</span>
                  </div>
                </div>
              )}

              {composer?.key === "decide" && (
                <DecideComposer item={item} onRun={runVerb} onCancel={() => setComposer(null)} />
              )}

              {composer?.key === "complete" && (
                <CompleteComposer item={item} onRun={runVerb} onCancel={() => setComposer(null)} />
              )}

              {textSpec && composer && (
                <form
                  className="flex flex-col gap-2 rounded-lg border border-subtle bg-layer-1 p-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    confirm();
                  }}
                >
                  <TextArea
                    size="md"
                    surface="field"
                    autoResize
                    maxRows={4}
                    // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
                    autoFocus
                    value={note}
                    placeholder={textSpec.placeholder}
                    onChange={(event) => setNote(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        confirm();
                      }
                      if (event.key === "Escape") setComposer(null);
                    }}
                    aria-label={textSpec.placeholder}
                  />
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-11 text-tertiary">Enter confirma · Esc cancela</span>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        stretch="auto"
                        label="Cancelar"
                        onClick={() => setComposer(null)}
                      />
                      <Button
                        variant="primary"
                        size="sm"
                        stretch="auto"
                        type="submit"
                        label={textSpec.confirm}
                        disabled={!!textSpec.required && !note.trim()}
                      />
                    </div>
                  </div>
                </form>
              )}

              {composer?.key === "delegate" && (
                <div className="flex flex-col gap-2 rounded-lg border border-subtle bg-layer-1 p-3">
                  <SidebarPropertyListItem icon={UserOutline} label="Executa">
                    <MemberSelect
                      variant="select-md"
                      getValues={members.getValues}
                      value={members.find(personId)}
                      placeholder="Escolha uma pessoa"
                      filterOption={(member) => member.id !== store.meId}
                      onChange={setPersonId}
                    />
                  </SidebarPropertyListItem>
                  <SidebarPropertyListItem icon={DueDateOutline} label="Prazo">
                    <DateSelect
                      variant="select-md"
                      value={toLocalDate(date)}
                      formatToken="dd/MM/yyyy"
                      onChange={(value) => setDate(fromLocalDate(value))}
                    />
                  </SidebarPropertyListItem>
                  <SidebarPropertyListItem icon={RefreshOutline} label="Retorno">
                    <DateSelect
                      variant="select-md"
                      value={toLocalDate(followUp)}
                      formatToken="dd/MM/yyyy"
                      onChange={(value) => setFollowUp(fromLocalDate(value))}
                    />
                    <span className="text-11 text-tertiary">sugerido: meio do prazo</span>
                  </SidebarPropertyListItem>
                  <Input
                    size="md"
                    value={autonomy}
                    placeholder="Autonomia (opcional): pode pedir cotações; contratar depende de aprovação"
                    aria-label="Autonomia"
                    onChange={(event) => setAutonomy(event.target.value)}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      stretch="auto"
                      label="Cancelar"
                      onClick={() => setComposer(null)}
                    />
                    <Button
                      variant="primary"
                      size="sm"
                      stretch="auto"
                      label="Delegar"
                      disabled={!personId}
                      onClick={() => confirm()}
                    />
                  </div>
                </div>
              )}

              {composer?.key === "postpone" && (
                <div className="flex flex-col gap-2 rounded-lg border border-subtle bg-layer-1 p-3">
                  <SidebarPropertyListItem icon={DueDateOutline} label="Novo prazo">
                    <DateSelect
                      variant="select-md"
                      value={toLocalDate(date)}
                      formatToken="dd/MM/yyyy"
                      onChange={(value) => setDate(fromLocalDate(value))}
                    />
                    {item.due && <span className="text-11 text-tertiary">antes: {dayMonth(item.due)}</span>}
                  </SidebarPropertyListItem>
                  <Input
                    size="md"
                    value={note}
                    placeholder="Motivo (opcional)"
                    aria-label="Motivo"
                    onChange={(event) => setNote(event.target.value)}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      stretch="auto"
                      label="Cancelar"
                      onClick={() => setComposer(null)}
                    />
                    <Button variant="primary" size="sm" stretch="auto" label="Adiar" onClick={() => confirm()} />
                  </div>
                </div>
              )}

              {messageSpec && composer?.personId && (
                <PreparedMessage
                  to={store.person(composer.personId)?.name ?? ""}
                  text={message}
                  onChange={setMessage}
                  recordLabel={messageSpec.record}
                  onRecord={recordFact}
                  onCancel={() => setComposer(null)}
                />
              )}
            </div>
          )}

          {notice && (
            <PreparedMessage
              to={store.person(notice.personId)?.name ?? ""}
              text={notice.text}
              onChange={(text) => setNotice({ ...notice, text })}
              recordLabel="Fechar aviso"
              hint="Copie a mensagem e avise por onde preferir. Este aviso não fica registrado no RADAR."
              onRecord={() => setNotice(null)}
              onCancel={() => setNotice(null)}
            />
          )}

          {open && item.approval?.state === "requested" && composer?.key !== "decide" && (
            <div className="rounded-lg border border-accent-subtle bg-accent-subtle p-3 text-13 text-primary">
              <b>Aguardando revisão:</b> a aprovação foi pedida a {store.personName(item.approval.approverId)} em{" "}
              {dayMonth(item.approval.at.slice(0, 10))}. A decisão continua proposta até lá.
            </div>
          )}
          {open && item.approval?.state === "returned" && composer?.key !== "decide" && (
            <div className="rounded-lg bg-layer-2 p-3 text-13 text-secondary">
              Devolvida para ajuste em {dayMonth(item.approval.at.slice(0, 10))}: “{item.approval.reason}”.
            </div>
          )}

          {/* the agent, inside the work (§16): fact, source and date */}
          {item.agentNote && open && (
            <div className="flex flex-col gap-2 rounded-lg border border-accent-subtle bg-accent-subtle p-3">
              <span className="flex items-center gap-1.5 text-11 font-semibold tracking-wide text-accent-primary uppercase">
                <Icon icon={AiStar1Outline} /> RADAR
              </span>
              <p className="text-13 text-primary">{item.agentNote.text}</p>
              {item.agentNote.source && <p className="text-11 text-tertiary">Fonte: {item.agentNote.source}</p>}
              {item.agentNote.personId &&
                !(primary?.key === "nudge" && primary.personId === item.agentNote.personId) && (
                  <div>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={`Cobrar ${store.personName(item.agentNote.personId)}`}
                      onClick={() => choose({ key: "nudge", label: "Cobrar", personId: item.agentNote?.personId })}
                    />
                  </div>
                )}
            </div>
          )}

          {/* the combinado (Guia básico §03) */}
          {item.kind === "action" && (
            <Section
              title="Combinado"
              trailing={
                gaps.length > 0 && open ? (
                  <span className="text-11 text-warning-primary">a confirmar: {gaps.join(", ")}</span>
                ) : null
              }
            >
              <div
                className="flex flex-col gap-2"
                inert={store.readOnly}
                style={store.readOnly ? { opacity: 0.55 } : undefined}
              >
                <SidebarPropertyListItem icon={FlagOutline} label="Entrega">
                  <InlineText
                    value={item.deliverable}
                    placeholder="O que deve existir ao final e como será aceito"
                    onSave={(value) => store.setText(item.id, "deliverable", value)}
                  />
                </SidebarPropertyListItem>
                <SidebarPropertyListItem icon={CheckSquareOutline} label="Próxima ação">
                  <InlineText
                    value={item.nextStep}
                    placeholder="Um passo com verbo que alguém consegue iniciar"
                    onSave={(value) => store.setText(item.id, "nextStep", value)}
                  />
                </SidebarPropertyListItem>
                <SidebarPropertyListItem icon={MembersOutline} label="Executa">
                  <MemberSelect
                    multiple
                    variant="select-ghost-md"
                    getValues={members.getValues}
                    value={item.withIds.map((id) => members.find(id)).filter((member) => !!member)}
                    placeholder="Você"
                    onChange={(ids) => store.setWith(item.id, ids)}
                  />
                  {delegated && item.confirmation && (
                    <Tooltip
                      label={
                        item.confirmation.state === "confirmed"
                          ? "O executor ainda não confirma pelo RADAR: este registro é seu."
                          : "Aguardando você registrar a confirmação do executor."
                      }
                    >
                      <span>
                        <Badge
                          variant={item.confirmation.state === "confirmed" ? "success" : "warning"}
                          size="sm"
                          label={
                            item.confirmation.state === "confirmed"
                              ? `confirmação registrada por ${store.personName(item.confirmation.recordedBy ?? store.meId)}${item.confirmation.at ? ` · ${dayMonth(item.confirmation.at)}` : ""}`
                              : "aguardando confirmação"
                          }
                        />
                      </span>
                    </Tooltip>
                  )}
                  {item.ownerId === store.meId && item.withIds.length > 0 && (
                    <span className="text-11 text-tertiary">responde você</span>
                  )}
                </SidebarPropertyListItem>
                {responde}
                {item.dueConflict && (
                  <div
                    className="flex flex-col gap-2 rounded-lg border border-warning-subtle bg-warning-subtle p-3"
                    role="group"
                    aria-label="Prazos divergentes"
                  >
                    <span className="text-13 text-primary">
                      <b>Prazos divergentes.</b> Duas fontes dizem datas diferentes. Escolha qual vale; até lá, não dá
                      para adiar.
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {item.dueConflict.sources.map((source) => (
                        <Button
                          key={source.label}
                          variant="secondary"
                          size="sm"
                          stretch="auto"
                          label={`${dayMonth(source.date)} · ${source.label}`}
                          onClick={() =>
                            commit(store, { title: `Vale ${dayMonth(source.date)}`, message: source.label }, () =>
                              store.resolveDueConflict(item.id, source.date)
                            )
                          }
                        />
                      ))}
                    </div>
                  </div>
                )}
                <SidebarPropertyListItem icon={DueDateOutline} label="Prazo">
                  <DateSelect
                    variant="select-ghost-md"
                    value={toLocalDate(item.due)}
                    placeholder="a confirmar"
                    clearable
                    formatToken="dd/MM/yyyy"
                    onChange={(value) => store.setDue(item.id, fromLocalDate(value))}
                  />
                  {item.previousDues?.length ? (
                    <span className="text-11 text-tertiary">
                      antes: {item.previousDues.map((entry) => dayMonth(entry.from)).join(", ")}
                    </span>
                  ) : null}
                </SidebarPropertyListItem>
                <SidebarPropertyListItem icon={RefreshOutline} label="Retorno">
                  <DateSelect
                    variant="select-ghost-md"
                    value={toLocalDate(item.followUp)}
                    placeholder={delegated ? "a confirmar" : "quando voltar a olhar"}
                    clearable
                    formatToken="dd/MM/yyyy"
                    onChange={(value) => store.setFollowUp(item.id, fromLocalDate(value))}
                  />
                  {!item.followUp && delegated && (
                    <button
                      type="button"
                      className="text-12 text-accent-primary hover:underline"
                      onClick={() => store.setFollowUp(item.id, suggestFollowUp(item.due))}
                    >
                      usar {dayMonth(suggestFollowUp(item.due))}
                    </button>
                  )}
                </SidebarPropertyListItem>
                {item.status === "blocked" && (
                  <SidebarPropertyListItem icon={WarningTriangleOutline} label="Bloqueio">
                    <InlineText
                      value={item.blockedReason}
                      placeholder="O que impede avançar"
                      onSave={(value) => store.setText(item.id, "blockedReason", value)}
                    />
                  </SidebarPropertyListItem>
                )}
              </div>
            </Section>
          )}

          {item.kind !== "action" && (
            <div
              className="flex flex-col gap-2"
              inert={store.readOnly}
              style={store.readOnly ? { opacity: 0.55 } : undefined}
            >
              {responde}
              <SidebarPropertyListItem
                icon={DueDateOutline}
                label={item.kind === "risk" ? "Revisar até" : "Decidir até"}
              >
                <DateSelect
                  variant="select-ghost-md"
                  value={toLocalDate(item.due)}
                  placeholder={item.kind === "decision" ? "Prazo a definir" : "Sem prazo"}
                  clearable
                  formatToken="dd/MM/yyyy"
                  onChange={(value) => store.setDue(item.id, fromLocalDate(value))}
                />
                {item.kind === "decision" && !item.due && <Badge variant="warning" size="sm" label="prazo a definir" />}
              </SidebarPropertyListItem>
              {item.kind === "risk" && item.riskScore !== undefined && (
                <SidebarPropertyListItem icon={WarningTriangleOutline} label="Exposição">
                  <span className="px-2 text-13 text-primary">
                    {item.riskScore} de 25 ·{" "}
                    {item.riskScore >= 20 ? "muito alta" : item.riskScore >= 15 ? "alta" : "moderada"}
                  </span>
                </SidebarPropertyListItem>
              )}
            </div>
          )}

          {/* less frequent properties, still edited in place (§7, §10) */}
          <Collapsible
            trigger={
              <span className="text-13 text-secondary">
                Mais detalhes · {item.kind === "action" && delegated ? "autonomia, " : ""}responsável, estado,
                prioridade, projeto
              </span>
            }
          >
            <div
              className="flex flex-col gap-2 pt-2"
              inert={store.readOnly}
              style={store.readOnly ? { opacity: 0.55 } : undefined}
            >
              {item.kind === "action" && (delegated || item.autonomy) && (
                <SidebarPropertyListItem icon={StateOutline} label="Autonomia">
                  <InlineText
                    value={item.autonomy}
                    placeholder="O que pode decidir sem você"
                    onSave={(value) => store.setText(item.id, "autonomy", value)}
                  />
                </SidebarPropertyListItem>
              )}
              <SidebarPropertyListItem icon={UserOutline} label="Responde">
                <MemberSelect
                  variant="select-ghost-md"
                  getValues={members.getValues}
                  value={members.find(item.ownerId)}
                  onChange={(id) => store.setOwner(item.id, id)}
                />
              </SidebarPropertyListItem>
              <SidebarPropertyListItem icon={StateOutline} label="Estado">
                <StateSelect
                  variant="select-ghost-md"
                  getValues={async () => ({ results: statusOptions })}
                  value={statusOptions.find((option) => option.id === item.status) ?? null}
                  onChange={(id) => requestStatus(id as TMockItem["status"])}
                />
                {!open && <span className="text-11 text-tertiary">Item fechado: o estado não volta atrás.</span>}
              </SidebarPropertyListItem>
              <SidebarPropertyListItem icon={PriorityOutline} label="Prioridade">
                <PrioritySelect
                  variant="select-ghost-md"
                  value={item.priority}
                  onChange={(priority) => store.setPriority(item.id, priority)}
                />
              </SidebarPropertyListItem>
              <SidebarPropertyListItem icon={ProjectsOutline} label="Projeto">
                <Select<TMockProject>
                  getValues={() => store.projects}
                  value={project ?? null}
                  onChange={(id) => store.setProject(item.id, id)}
                  getOptionValue={(option) => option.id}
                  getOptionLabel={(option) => option.title}
                  showSearch={false}
                  pinSelected={false}
                >
                  <Select.Trigger variant="select-ghost-md">
                    <span className="truncate text-13">{project?.title ?? "Sem projeto"}</span>
                  </Select.Trigger>
                </Select>
              </SidebarPropertyListItem>
            </div>
          </Collapsible>

          {/* who must be heard and who must know (Metodologia §05, lei 6) */}
          {item.kind === "decision" || item.consultIds?.length || item.informIds?.length || involving ? (
            <Section
              title="Consultar e informar"
              trailing={
                <button
                  type="button"
                  className="text-12 text-accent-primary hover:underline"
                  onClick={() => setInvolving(!involving)}
                >
                  {involving ? "Pronto" : "Editar"}
                </button>
              }
            >
              {involving ? (
                <div className="flex flex-col gap-2">
                  <SidebarPropertyListItem icon={MembersOutline} label="Consultar">
                    <MemberSelect
                      multiple
                      variant="select-ghost-md"
                      getValues={members.getValues}
                      value={(item.consultIds ?? []).map((id) => members.find(id)).filter((member) => !!member)}
                      placeholder="Ninguém"
                      onChange={(ids) => store.setInvolved(item.id, "consultIds", ids)}
                    />
                  </SidebarPropertyListItem>
                  <SidebarPropertyListItem icon={MembersOutline} label="Informar">
                    <MemberSelect
                      multiple
                      variant="select-ghost-md"
                      getValues={members.getValues}
                      value={(item.informIds ?? []).map((id) => members.find(id)).filter((member) => !!member)}
                      placeholder="Ninguém"
                      onChange={(ids) => store.setInvolved(item.id, "informIds", ids)}
                    />
                  </SidebarPropertyListItem>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-col">
                    <span className="text-12 text-tertiary">
                      Antes de {item.kind === "decision" ? "decidir" : "concluir"}, ouvir
                    </span>
                    {(item.consultIds ?? []).length ? (
                      (item.consultIds ?? []).map((id) => (
                        <PersonWithState
                          key={id}
                          personId={id}
                          done={(item.consultedIds ?? []).includes(id)}
                          doneLabel={recordText(item, "consult", id, store.personName)}
                          pendingLabel={open ? "pendente" : "não consultado"}
                          actionLabel={open ? "Preparar consulta" : ""}
                          onAction={() => choose({ key: "consult", label: "Consultar", personId: id })}
                        />
                      ))
                    ) : (
                      <span className="text-13 text-tertiary">Ninguém</span>
                    )}
                  </div>
                  <div className="flex flex-col">
                    <span className="text-12 text-tertiary">Depois, informar</span>
                    {(item.informIds ?? []).length ? (
                      (item.informIds ?? []).map((id) => (
                        <PersonWithState
                          key={id}
                          personId={id}
                          done={(item.informedIds ?? []).includes(id)}
                          doneLabel={recordText(item, "inform", id, store.personName)}
                          pendingLabel={open ? "depois de decidir" : "falta comunicar"}
                          actionLabel={open ? "" : "Preparar mensagem"}
                          onAction={() => !open && choose({ key: "inform", label: "Comunicar", personId: id })}
                        />
                      ))
                    ) : (
                      <span className="text-13 text-tertiary">Ninguém</span>
                    )}
                  </div>
                </div>
              )}
            </Section>
          ) : (
            <button
              type="button"
              className="self-start text-12 text-accent-primary hover:underline"
              onClick={() => setInvolving(true)}
            >
              + Envolver alguém (consultar ou informar)
            </button>
          )}

          {item.context && (
            <Section title="O que está acontecendo">
              <p className="text-13 leading-relaxed text-secondary">{item.context}</p>
            </Section>
          )}

          {(dependsOn.length > 0 || unlocks.length > 0 || item.threatensIds?.length) && (
            <Section title="Ligações">
              {(item.threatensIds ?? []).map((projectId) => (
                <p key={projectId} className="text-13 text-secondary">
                  Ameaça {store.project(projectId)?.title ?? "um projeto"}
                </p>
              ))}
              {dependsOn.map((other) => (
                <p key={other.id} className="text-13 text-secondary">
                  Depende de{" "}
                  <button
                    type="button"
                    className="text-accent-primary hover:underline"
                    onClick={() => store.openItemById(other.id)}
                  >
                    {other.title}
                  </button>
                  {!isOpen(other.status) && " (resolvido)"}
                </p>
              ))}
              {unlocks.map((other) => (
                <p key={other.id} className="text-13 text-secondary">
                  Destrava{" "}
                  <button
                    type="button"
                    className="text-accent-primary hover:underline"
                    onClick={() => store.openItemById(other.id)}
                  >
                    {other.title}
                  </button>
                </p>
              ))}
            </Section>
          )}

          {item.evidence.length > 0 && (
            <Section title="Evidências">
              <EvidenceList item={item} />
              {item.outcome && <p className="text-12 text-tertiary">Entregue: {item.outcome}</p>}
            </Section>
          )}

          {/* depth, only on demand (§7, level 3) */}
          <Collapsible trigger={<span className="text-13 font-semibold text-primary">Histórico e detalhes</span>}>
            <div className="flex flex-col gap-4 pt-2">
              <ol className="flex flex-col gap-2.5">
                {[...item.activity].reverse().map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2 text-13">
                    {entry.actorId === "radar" ? (
                      <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent-subtle text-accent-primary">
                        <Icon icon={AiStar1Outline} />
                      </span>
                    ) : (
                      <PersonAvatar personId={entry.actorId} size="xs" />
                    )}
                    <span className="text-secondary">
                      <span className="font-medium text-primary">
                        {entry.actorId === store.meId ? "Você" : store.personName(entry.actorId)}
                      </span>{" "}
                      {entry.text}
                      <span className="ml-1 text-11 text-placeholder">{dayMonth(entry.at.slice(0, 10))}</span>
                    </span>
                  </li>
                ))}
              </ol>
              {item.previousDues?.length ? (
                <p className="text-12 text-tertiary">
                  Prazos anteriores:{" "}
                  {item.previousDues
                    .map(
                      (entry) =>
                        `${dayMonth(entry.from)} → ${dayMonth(entry.to)}${entry.reason ? ` (${entry.reason})` : ""}`
                    )
                    .join("; ")}
                </p>
              ) : null}
            </div>
          </Collapsible>
        </div>
      </div>
    </>
  );
});

/** The URL named an item that is not here: an old link, or something created in another session. */
function MissingItem({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex flex-col gap-3 p-6">
      <h2 className="text-16 font-semibold text-primary">Item não encontrado</h2>
      <p className="text-13 text-secondary">
        O link aponta para um item que não está mais disponível nesta sessão, ou que você não pode ver.
      </p>
      <div>
        <Button variant="secondary" size="md" stretch="auto" label="Voltar à lista" onClick={onClose} />
      </div>
    </div>
  );
}

const FOCUSABLE =
  "a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])";

/**
 * Peek of one item beside the list it came from: context without losing your place (§23.12). Same
 * geometry as Plane's work item side peek; clicking another row swaps the item, Esc closes. The item lives
 * in the address bar, so a link, a reload and Back all bring it back. Focus moves into the panel on opening
 * and returns to what opened it on closing; on a phone the panel covers the screen and keeps Tab inside it.
 */
export const RadarMockupItemDrawer = observer(function RadarMockupItemDrawer() {
  const store = useRadarMockup();
  const openId = store.openItemId;
  const item = store.openItem;
  const panelRef = useRef<HTMLElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);

  // Remember what had focus when the panel opened; give it back when the panel closes.
  useEffect(() => {
    if (!openId) return;
    returnTo.current = (document.activeElement as HTMLElement | null) ?? null;
    panelRef.current?.focus();
    return () => {
      const target = returnTo.current;
      returnTo.current = null;
      if (target && target.isConnected) target.focus();
    };
    // Re-run only when the panel opens or closes, not when another item replaces this one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!openId]);

  useEffect(() => {
    if (!openId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !(event.target as HTMLElement | null)?.closest("textarea, input, [role='listbox']"))
        store.closeItem();
      if (event.key === "Tab" && window.matchMedia("(max-width: 767px)").matches) {
        const nodes = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
        if (!nodes?.length) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        const active = document.activeElement;
        if (event.shiftKey && (active === first || active === panelRef.current)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openId, store]);

  if (!openId) return null;
  return (
    <aside
      ref={panelRef}
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-label={item?.title ?? "Item não encontrado"}
      className="absolute top-0 right-0 bottom-0 z-[25] flex w-full flex-col overflow-hidden border-l border-subtle bg-surface-1 outline-none md:w-[50%] xl:w-[44%]"
      style={{
        boxShadow:
          "0px 4px 8px 0px rgba(0, 0, 0, 0.12), 0px 6px 12px 0px rgba(16, 24, 40, 0.12), 0px 1px 16px 0px rgba(16, 24, 40, 0.12)",
      }}
    >
      {item ? <ItemDetail key={item.id} item={item} /> : <MissingItem onClose={store.closeItem} />}
    </aside>
  );
});
