/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { Input } from "@makeplane/propel/components/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { TextArea } from "@makeplane/propel/components/text-area";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import {
  AiStar1Outline,
  ChevronDownOutline,
  InboxOutline,
  MailOutline,
  PresentationOutline,
  UserOutline,
} from "@makeplane/propel/icons";
import { DateSelect, MemberSelect } from "@plane/blocks/property-select";
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { setToast } from "@plane/blocks/toast";
import type { TMockInboxEntry, TMockSuggestionPart } from "./mock-data";
import { addDays, dayMonth, fromLocalDate, nextMonday, toLocalDate } from "./interaction-model";
import { REFUSE_REASONS, REJECT_REASONS } from "./mockup.store";
import { useRadarMockup } from "./provider";
import {
  DueChip,
  MockupHeader,
  PartialNotice,
  PersonAvatar,
  ScenarioGate,
  SectionTitle,
  commit,
  useMemberOptions,
  withUndo,
} from "./ui";

const SOURCE = {
  agente: { icon: AiStar1Outline, label: "RADAR" },
  reuniao: { icon: PresentationOutline, label: "Reunião" },
  captura: { icon: UserOutline, label: "Você" },
  integracao: { icon: MailOutline, label: "E-mail" },
} as const;

function SourceLine({ entry }: { entry: TMockInboxEntry }) {
  const source = SOURCE[entry.source];
  return (
    <span className="flex items-center gap-1.5 text-11 font-medium text-tertiary">
      <Icon icon={source.icon} />
      {source.label} · {entry.detail}
    </span>
  );
}

const PART_BADGE: Record<
  TMockSuggestionPart["state"],
  { variant: "warning" | "success" | "neutral" | "danger"; label: string }
> = {
  pending: { variant: "warning", label: "Aguardando sua revisão" },
  accepted: { variant: "success", label: "Aceita" },
  rejected: { variant: "neutral", label: "Rejeitada" },
  failed: { variant: "danger", label: "Não foi criada" },
};

/** One of the two proposals of a card: it is reviewed, accepted or rejected on its own. */
function PartRow({
  title,
  detail,
  part,
  onAccept,
  onReject,
  trailing,
}: {
  title: string;
  detail?: string;
  part: TMockSuggestionPart;
  onAccept: () => void;
  onReject: (reason: (typeof REJECT_REASONS)[number]) => void;
  trailing?: React.ReactNode;
}) {
  const store = useRadarMockup();
  const decided = part.state === "accepted" || part.state === "rejected";
  return (
    <div className="flex flex-col gap-2 rounded-md border border-subtle bg-layer-1 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 text-13 font-medium text-primary">{title}</span>
        {trailing}
        <Badge variant={PART_BADGE[part.state].variant} size="sm" label={PART_BADGE[part.state].label} />
      </div>
      {detail && <p className="text-12 text-tertiary">{detail}</p>}
      {part.error && <p className="text-12 text-danger-primary">{part.error}</p>}
      {!decided && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={part.state === "failed" ? "Tentar de novo" : "Aceitar"}
            disabled={store.readOnly}
            onClick={onAccept}
          />
          <Menu>
            <MenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  label="Rejeitar"
                  disabled={store.readOnly}
                  icon={<Icon icon={ChevronDownOutline} />}
                  iconPosition="end"
                />
              }
            />
            <MenuContent side="bottom" align="start">
              {REJECT_REASONS.map((reason) => (
                <MenuItem key={reason.key} label={reason.label} onClick={() => onReject(reason)} />
              ))}
            </MenuContent>
          </Menu>
        </div>
      )}
    </div>
  );
}

/**
 * What the agent proposes today: a link between objects that already exist (a risk that threatens a project)
 * and a mitigation action. Each is a separate proposal with its own review, evidence and version, so
 * accepting both is two steps, and one of them can fail while the other stands.
 */
const ProposalCard = observer(function ProposalCard({ entry }: { entry: TMockInboxEntry }) {
  const store = useRadarMockup();
  const members = useMemberOptions();
  const suggestion = entry.suggestion;
  const [editing, setEditing] = useState(false);
  const [explanation, setExplanation] = useState(suggestion?.explanation ?? "");
  const [mitigationTitle, setMitigationTitle] = useState(suggestion?.mitigation?.title ?? "");
  const [mitigationDue, setMitigationDue] = useState<string | null>(suggestion?.mitigation?.due ?? null);
  const [mitigationWith, setMitigationWith] = useState<string | null>(suggestion?.mitigation?.withId ?? null);
  if (!suggestion?.relation) return null;
  const relation = suggestion.relation;
  const mitigation = suggestion.mitigation;
  const risk = store.item(relation.riskId);
  const target = store.project(relation.targetProjectId);
  const version = suggestion.version ?? 1;

  const acceptPart = (part: "relation" | "mitigation") => {
    let error: string | undefined;
    withUndo(
      store,
      {
        title: part === "relation" ? "Relação aceita" : "Ação de mitigação criada",
        message: part === "relation" ? `${risk?.title} ameaça ${target?.title}` : mitigation?.title,
      },
      () => {
        const result = store.acceptSuggestionPart(entry.id, part);
        error = result.error;
        return result.ok;
      },
      {
        onSkipped: () =>
          setToast({ type: "error", title: "Não foi possível aceitar", message: error ?? "Tente de novo." }),
      }
    );
  };

  const acceptBoth = () => {
    const outcome: { relation?: boolean; mitigation?: boolean } = {};
    withUndo(
      store,
      { title: "As duas propostas foram aceitas", message: suggestion.title },
      () => {
        if (relation.state === "pending" || relation.state === "failed")
          outcome.relation = store.acceptSuggestionPart(entry.id, "relation").ok;
        if (mitigation && (mitigation.state === "pending" || mitigation.state === "failed"))
          outcome.mitigation = store.acceptSuggestionPart(entry.id, "mitigation").ok;
        return outcome.relation !== false && outcome.mitigation !== false;
      },
      {
        onSkipped: () =>
          setToast({
            type: "warning",
            title: "Só uma parte foi aceita",
            message: `${outcome.relation ? "A relação foi aceita e continua valendo. " : ""}${outcome.mitigation === false ? "A ação de mitigação não foi criada: tente de novo. " : ""}As propostas são decididas separadamente.`,
          }),
      }
    );
  };

  const reject = (part: "relation" | "mitigation", reason: (typeof REJECT_REASONS)[number]) =>
    withUndo(store, { title: "Proposta rejeitada", message: `Motivo registrado: ${reason.label}.` }, () =>
      store.rejectSuggestionPart(entry.id, part, reason.key)
    );

  const save = () => {
    commit(
      store,
      { title: `Proposta editada · versão ${version + 1}`, message: "A edição fica registrada com a sua autoria." },
      () => {
        store.editSuggestion(entry.id, {
          explanation,
          mitigationTitle: mitigation ? mitigationTitle : undefined,
          mitigationDue: mitigation && mitigationDue ? mitigationDue : undefined,
          mitigationWithId: mitigation && mitigationWith ? mitigationWith : undefined,
        });
      }
    );
    setEditing(false);
  };

  const pending = [relation, mitigation].filter(
    (part) => part && (part.state === "pending" || part.state === "failed")
  );
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-accent-subtle bg-surface-1 p-4 shadow-raised-100">
      <SourceLine entry={entry} />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="min-w-0 flex-1 text-14 font-semibold text-primary">{suggestion.title}</h3>
        <Tooltip label="Editar cria uma nova versão da proposta, com o seu nome.">
          <span>
            <Badge
              variant="neutral"
              size="sm"
              label={`Proposta v${version}${suggestion.editedAt ? " · editada por você" : ""}`}
            />
          </span>
        </Tooltip>
      </div>

      {editing ? (
        <TextArea
          size="md"
          surface="field"
          autoResize
          maxRows={5}
          // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
          autoFocus
          value={explanation}
          aria-label="Justificativa da proposta"
          onChange={(event) => setExplanation(event.target.value)}
        />
      ) : (
        <p className="text-13 leading-relaxed text-secondary">{suggestion.explanation}</p>
      )}

      {suggestion.evidence?.length ? (
        <div className="flex flex-col gap-1">
          <span className="text-12 font-medium text-secondary">Evidências do RADAR</span>
          <ul className="flex flex-col gap-0.5">
            {suggestion.evidence.map((evidence) => (
              <li key={evidence.label} className="text-12 text-tertiary">
                {evidence.label} <span className="text-placeholder">· {evidence.source}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <PartRow
        title={`Relação: “${risk?.title ?? "risco"}” ameaça ${target?.title ?? "o projeto"}`}
        detail="Liga dois itens que já existem. Não cria um risco novo."
        part={relation}
        onAccept={() => acceptPart("relation")}
        onReject={(reason) => reject("relation", reason)}
      />
      {mitigation && (
        <PartRow
          title={`Ação: ${mitigation.title}`}
          detail={`Com ${store.personName(mitigation.withId)} · prazo ${dayMonth(mitigation.due)}`}
          part={mitigation}
          onAccept={() => acceptPart("mitigation")}
          onReject={(reason) => reject("mitigation", reason)}
          trailing={
            <>
              <PersonAvatar personId={mitigation.withId} size="xs" />
              <DueChip due={mitigation.due} />
            </>
          }
        />
      )}

      {editing && mitigation && (
        <div className="flex flex-col gap-2 rounded-md border border-subtle p-3">
          <Input
            size="md"
            value={mitigationTitle}
            aria-label="Título da ação"
            onChange={(event) => setMitigationTitle(event.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <MemberSelect
              variant="select-md"
              getValues={members.getValues}
              value={members.find(mitigationWith)}
              onChange={setMitigationWith}
            />
            <DateSelect
              variant="select-md"
              value={toLocalDate(mitigationDue)}
              formatToken="dd/MM/yyyy"
              onChange={(value) => setMitigationDue(fromLocalDate(value))}
            />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {editing ? (
          <>
            <Button variant="primary" size="md" stretch="auto" label="Salvar nova versão" onClick={save} />
            <Button variant="ghost" size="md" stretch="auto" label="Cancelar" onClick={() => setEditing(false)} />
          </>
        ) : (
          <>
            {pending.length > 1 && (
              <Button
                variant="primary"
                size="md"
                stretch="auto"
                label="Aceitar as duas"
                disabled={store.readOnly}
                onClick={acceptBoth}
              />
            )}
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label="Editar"
              disabled={store.readOnly || !pending.length}
              onClick={() => setEditing(true)}
            />
          </>
        )}
      </div>
      {pending.length > 1 && !editing && (
        <p className="text-11 text-tertiary">
          Aceitar as duas são dois passos: se um falhar, o outro continua valendo e você tenta de novo só o que faltou.
        </p>
      )}
    </article>
  );
});

/** A preview of something the agent cannot do yet: visible, labeled, and without a way to accept it. */
const FuturePreview = observer(function FuturePreview({ entry }: { entry: TMockInboxEntry }) {
  const store = useRadarMockup();
  const suggestion = entry.suggestion;
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-dashed border-subtle bg-layer-1 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="purple" size="sm" label="Funcionalidade futura" />
        <SourceLine entry={entry} />
      </div>
      <h3 className="text-14 font-semibold text-primary">{suggestion?.title ?? entry.title}</h3>
      {suggestion ? (
        <p className="text-13 leading-relaxed text-secondary">{suggestion.explanation}</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-subtle bg-surface-1">
          {entry.candidates?.map((candidate) => (
            <div
              key={candidate.title}
              className="flex items-center gap-3 border-b border-subtle px-3 py-2 text-13 last:border-b-0"
            >
              <span className="min-w-0 flex-1 truncate text-primary">{candidate.title}</span>
              <PersonAvatar personId={candidate.withId} size="xs" />
              <DueChip due={candidate.due} />
            </div>
          ))}
        </div>
      )}
      <p className="text-12 text-tertiary">
        {suggestion
          ? "O agente de hoje não sugere riscos novos: ele só liga e mitiga o que já existe."
          : "O RADAR ainda não lê atas de reunião. Esta é uma prévia com dados fictícios."}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" stretch="auto" label="Indisponível hoje" disabled />
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          label="Dispensar a prévia"
          onClick={() => {
            withUndo(store, { title: "Prévia dispensada", message: entry.title }, () => store.ignoreEntry(entry.id));
          }}
        />
      </div>
    </article>
  );
});

const DestinationMenu = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <Menu>
    <MenuTrigger
      render={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={label}
          icon={<Icon icon={ChevronDownOutline} />}
          iconPosition="end"
        />
      }
    />
    <MenuContent side="bottom" align="end">
      {children}
    </MenuContent>
  </Menu>
);

/** The destinations of the Guia básico §04: intervene, take it on, review later, keep as reference, refuse. */
const TriageRow = observer(function TriageRow({ entry }: { entry: TMockInboxEntry }) {
  const store = useRadarMockup();
  const assume = (as: "fazer" | "delegar" | "decidir" | "risco", title: string) => {
    withUndo(store, { title, message: entry.title }, () => {
      store.assume(entry.id, as);
    });
  };
  return (
    <div className="flex min-h-[52px] flex-wrap items-center gap-2 border-b border-subtle px-4 py-2.5 last:border-b-0">
      <div className="min-w-0 flex-1 basis-64">
        <p className="truncate text-13 font-medium text-primary">{entry.title}</p>
        <SourceLine entry={entry} />
      </div>
      <Tooltip label="Há impacto grave em curso: vira o primeiro item de hoje">
        <Button
          variant="danger-outline"
          size="sm"
          stretch="auto"
          label="Intervir"
          disabled={store.readOnly}
          onClick={() => {
            withUndo(store, { title: "Intervenção aberta para hoje", message: entry.title }, () => {
              const item = store.intervene(entry.id);
              if (item) store.openItemById(item.id);
            });
          }}
        />
      </Tooltip>
      <DestinationMenu label="Assumir">
        <MenuItem
          label="Eu faço"
          description="Vira um combinado seu"
          onClick={() => assume("fazer", "Combinado criado")}
        />
        <MenuItem
          label="Delegar…"
          description="Escolha quem executa, prazo e retorno"
          onClick={() => assume("delegar", "Combinado criado")}
        />
        <MenuItem
          label="Decidir"
          description="Vira uma decisão sua"
          onClick={() => assume("decidir", "Decisão criada")}
        />
        <MenuItem
          label="É um risco"
          description="Algo que ainda pode acontecer"
          onClick={() => assume("risco", "Risco registrado")}
        />
      </DestinationMenu>
      <DestinationMenu label="Revisar em">
        {[
          { label: "Amanhã", value: addDays(store.today, 1) },
          { label: `Segunda (${dayMonth(nextMonday())})`, value: nextMonday() },
          { label: "Em duas semanas", value: addDays(store.today, 14) },
        ].map((option) => (
          <MenuItem
            key={option.label}
            label={option.label}
            onClick={() => {
              withUndo(store, { title: `Volta para a Inbox em ${dayMonth(option.value)}`, message: entry.title }, () =>
                store.scheduleEntry(entry.id, option.value)
              );
            }}
          />
        ))}
      </DestinationMenu>
      <DestinationMenu label="Outro destino">
        <MenuItem
          label="Guardar como referência"
          description="Memória útil, sem compromisso"
          onClick={() => {
            withUndo(store, { title: "Guardado como referência", message: entry.title }, () =>
              store.keepAsReference(entry.id)
            );
          }}
        />
        {REFUSE_REASONS.map((reason) => (
          <MenuItem
            key={reason}
            label={`Recusar: ${reason.toLowerCase()}`}
            onClick={() => {
              withUndo(store, { title: "Recusado", message: `Motivo registrado: ${reason}.` }, () =>
                store.refuse(entry.id, reason)
              );
            }}
          />
        ))}
      </DestinationMenu>
    </div>
  );
});

/** Inbox: capture and triage, so that an input does not become structure on arrival (§15). */
export const RadarMockupInbox = observer(function RadarMockupInbox() {
  const store = useRadarMockup();
  const proposals = store.visibleInbox.filter(
    (entry) => entry.source === "agente" && entry.suggestion?.type === "relation"
  );
  const previews = store.visibleInbox.filter(
    (entry) => entry.source === "reuniao" || (entry.source === "agente" && entry.suggestion?.type === "new_risk")
  );
  const others = store.visibleInbox.filter((entry) => entry.source === "captura" || entry.source === "integracao");
  const shown = proposals.length + previews.length + others.length;
  return (
    <>
      <MockupHeader
        crumbs={[{ label: "Inbox", icon: <Icon icon={InboxOutline} /> }]}
        actions={
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Capturar"
            disabled={store.readOnly}
            onClick={() => store.setCaptureOpen(true)}
          />
        }
      />
      <div className="mx-auto flex w-full max-w-[880px] flex-col gap-7 px-4 py-6 md:px-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-20 font-semibold text-primary">Inbox</h1>
          <p className="text-13 text-secondary">Tudo que chegou e ainda não virou trabalho. Decida o que fica.</p>
        </header>
        <PartialNotice what="Parte das entradas não carregou." />
        <ScenarioGate>
          {shown === 0 && (
            <div className="rounded-lg border border-subtle py-10">
              <EmptyStateCompact
                title="Inbox zerada"
                description={`Capturas, pedidos e propostas do RADAR aparecem aqui. Conferido às ${store.now.time}.`}
              />
            </div>
          )}
          {proposals.length > 0 && (
            <section className="flex flex-col gap-3" aria-label="Propostas do RADAR">
              <SectionTitle title="Propostas do RADAR" count={proposals.length} />
              {proposals.map((entry) => (
                <ProposalCard key={entry.id} entry={entry} />
              ))}
            </section>
          )}
          {others.length > 0 && (
            <section className="flex flex-col gap-3" aria-label="Capturas e pedidos">
              <SectionTitle title="Capturas e pedidos" count={others.length} />
              <div className="overflow-hidden rounded-lg border border-subtle">
                {others.map((entry) => (
                  <TriageRow key={entry.id} entry={entry} />
                ))}
              </div>
            </section>
          )}
          {previews.length > 0 && (
            <section className="flex flex-col gap-3" aria-label="Funcionalidades futuras">
              <SectionTitle title="Prévias de funcionalidades futuras" count={previews.length} />
              {previews.map((entry) => (
                <FuturePreview key={entry.id} entry={entry} />
              ))}
            </section>
          )}
          {(store.scheduledInbox.length > 0 || store.references.length > 0) && (
            <Collapsible
              trigger={
                <span className="text-12 font-medium text-secondary">
                  Agendados · {store.scheduledInbox.length} · Referências · {store.references.length}
                </span>
              }
            >
              <ul className="flex flex-col gap-1 px-1 pt-1 text-13 text-secondary">
                {store.scheduledInbox.map((entry) => (
                  <li key={entry.id}>
                    {entry.title}{" "}
                    <span className="text-tertiary">· volta em {dayMonth(entry.reviewOn ?? store.today)}</span>
                  </li>
                ))}
                {store.references.map((entry) => (
                  <li key={entry.id}>
                    {entry.title} <span className="text-tertiary">· referência</span>
                  </li>
                ))}
              </ul>
            </Collapsible>
          )}
        </ScenarioGate>
      </div>
    </>
  );
});
