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
import { Input } from "@makeplane/propel/components/input";
import { TextArea } from "@makeplane/propel/components/text-area";
import { FileOutline, WarningTriangleOutline } from "@makeplane/propel/icons";
import { cn } from "@plane/utils";
import type { TMockItem } from "./mock-data";
import type { TVerbKey } from "./interaction-model";
import { approvalBlockers, approversOf, dayMonth } from "./interaction-model";
import type { TVerbInput } from "./mockup.store";
import { useRadarMockup } from "./provider";

export type TRunVerb = (key: TVerbKey, title: string, input: TVerbInput, message?: string) => void;

const when = (iso: string) => dayMonth(iso.slice(0, 10));

/** Who attached what, when: evidence is never anonymous. */
export const EvidenceList = observer(function EvidenceList({ item }: { item: TMockItem }) {
  const store = useRadarMockup();
  if (!item.evidence.length) return <p className="text-13 text-tertiary">Nenhuma evidência anexada.</p>;
  return (
    <ul className="flex flex-col gap-1">
      {item.evidence.map((evidence) => (
        <li key={evidence.id} className="flex items-start gap-2 text-13 text-secondary">
          <span className="mt-0.5 shrink-0">
            <Icon icon={FileOutline} />
          </span>
          <span>
            {evidence.label}
            <span className="ml-1 text-11 text-tertiary">
              · {store.personName(evidence.addedBy)} em {when(evidence.at)}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
});

/**
 * "Decidir": examine the choice before making it. Shows the evidence, what stands in the way of approving
 * (including being the author, which makes the approval someone else's), and what can be done about each.
 * Sending a proposal back is not the same as an agent suggestion being rejected: the decision stays proposed.
 */
export const DecideComposer = observer(function DecideComposer({
  item,
  onRun,
  onCancel,
}: {
  item: TMockItem;
  onRun: TRunVerb;
  onCancel: () => void;
}) {
  const store = useRadarMockup();
  const [note, setNote] = useState("");
  const [sub, setSub] = useState<"evidence" | "approver" | null>(null);
  const [evidenceText, setEvidenceText] = useState("");
  const [approverId, setApproverId] = useState<string | null>(null);
  const blockers = approvalBlockers(item, store.meId, store.people);
  const approvers = approversOf(item, store.people);
  const requested = item.approval?.state === "requested" ? item.approval : null;
  const returned = item.approval?.state === "returned" ? item.approval : null;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-subtle bg-layer-1 p-3">
      <div className="flex flex-col gap-1.5">
        <span className="text-12 font-medium text-secondary">Evidências para decidir</span>
        <EvidenceList item={item} />
        {item.proposal && (
          <p className="text-12 text-tertiary">
            Justificativa da proposta, por {store.personName(item.authorId ?? item.ownerId)}: {item.proposal.rationale}
          </p>
        )}
      </div>

      {requested && (
        <div className="flex items-start gap-2 rounded-md border border-accent-subtle bg-accent-subtle p-2.5 text-13 text-primary">
          <span>
            <b>Aguardando revisão:</b> a aprovação foi pedida a {store.personName(requested.approverId)} em{" "}
            {when(requested.at)}. A decisão continua proposta até lá.
          </span>
        </div>
      )}
      {returned && (
        <p className="rounded-md bg-layer-2 p-2.5 text-13 text-secondary">
          Devolvida para ajuste por {store.personName(returned.by)} em {when(returned.at)}: “{returned.reason}”.
        </p>
      )}

      {blockers.length > 0 && (
        <ul className="flex flex-col gap-1.5" aria-label="Condições para aprovar">
          {blockers.map((blocker) => (
            <li key={blocker.key} className="flex flex-wrap items-center gap-2 text-13 text-primary">
              <span className="text-warning-primary">
                <Icon icon={WarningTriangleOutline} />
              </span>
              <span className="min-w-0 flex-1">{blocker.text}</span>
              {blocker.fix === "attach_evidence" && (
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label="Anexar evidência"
                  onClick={() => setSub(sub === "evidence" ? null : "evidence")}
                />
              )}
              {blocker.fix === "request_approval" && !requested && (
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label="Pedir aprovação"
                  onClick={() => setSub(sub === "approver" ? null : "approver")}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {sub === "evidence" && (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!evidenceText.trim()) return;
            onRun("attach_evidence", "Evidência anexada", { note: evidenceText }, evidenceText.trim());
            setEvidenceText("");
            setSub(null);
          }}
        >
          <Input
            size="md"
            // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
            autoFocus
            value={evidenceText}
            placeholder="Link, documento ou confirmação com nome e data"
            aria-label="Evidência"
            onChange={(event) => setEvidenceText(event.target.value)}
          />
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            type="submit"
            label="Anexar"
            disabled={!evidenceText.trim()}
          />
        </form>
      )}

      {sub === "approver" && (
        <div className="flex flex-col gap-2 rounded-md border border-subtle bg-surface-1 p-2.5">
          <span className="text-12 text-secondary">Quem pode aprovar no seu lugar (não é o autor):</span>
          <div className="flex flex-wrap gap-1.5">
            {approvers.map((person) => (
              <button
                key={person.id}
                type="button"
                aria-pressed={approverId === person.id}
                onClick={() => setApproverId(person.id)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-12",
                  approverId === person.id
                    ? "border-accent-strong bg-accent-subtle text-accent-primary"
                    : "border-subtle text-secondary hover:bg-layer-transparent-hover"
                )}
              >
                {person.display_name}
                {person.id === store.meId ? " (você)" : ""}
              </button>
            ))}
          </div>
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label={approverId ? `Pedir a ${store.personName(approverId)}` : "Escolha quem aprova"}
              disabled={!approverId}
              onClick={() => {
                if (!approverId) return;
                onRun(
                  "request_approval",
                  "Pedido de aprovação registrado",
                  { personId: approverId },
                  `Aguardando ${store.personName(approverId)}. O RADAR não avisa a pessoa: combine por onde você preferir.`
                );
                setSub(null);
              }}
            />
          </div>
        </div>
      )}

      <TextArea
        size="md"
        surface="field"
        autoResize
        maxRows={4}
        value={note}
        placeholder="Justificativa: por que esta escolha (obrigatória para devolver)"
        onChange={(event) => setNote(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
        }}
        aria-label="Justificativa"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-11 text-tertiary">
          {blockers.length ? "Resolva as condições acima para aprovar." : "Aprovar não pode ser desfeito."}
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" stretch="auto" label="Cancelar" onClick={onCancel} />
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Devolver para ajuste"
            disabled={!note.trim()}
            onClick={() =>
              onRun("send_back", "Proposta devolvida para ajuste", { note }, `${item.title}. A decisão segue proposta.`)
            }
          />
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            label="Aprovar"
            disabled={blockers.length > 0}
            onClick={() => onRun("approve", "Decisão aprovada", { note })}
          />
        </div>
      </div>
    </div>
  );
});

/**
 * "Concluir": recording valid evidence, in one short step. Pick an evidence already attached or write what
 * proves the delivery. Concluding is not undone: what was missing becomes a new combinado.
 */
export const CompleteComposer = observer(function CompleteComposer({
  item,
  onRun,
  onCancel,
}: {
  item: TMockItem;
  onRun: TRunVerb;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const valid = !!text.trim() || !!picked;
  const closing = item.kind === "risk";
  const submit = () => {
    if (!valid) return;
    onRun(
      "complete",
      closing ? "Risco encerrado" : "Concluído",
      { note: text, evidenceId: picked ?? undefined },
      "Fica registrado com a evidência."
    );
  };
  return (
    <form
      className="flex flex-col gap-2 rounded-lg border border-subtle bg-layer-1 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      {item.deliverable && (
        <div className="text-13">
          <span className="text-tertiary">Atendeu ao combinado?</span>
          <p className="mt-0.5 text-primary">{item.deliverable}</p>
        </div>
      )}
      {item.evidence.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-12 text-tertiary">Usar o que já está anexado:</span>
          {item.evidence.map((evidence) => (
            <button
              key={evidence.id}
              type="button"
              aria-pressed={picked === evidence.id}
              onClick={() => setPicked(picked === evidence.id ? null : evidence.id)}
              className={cn(
                "max-w-full truncate rounded-full border px-2.5 py-1 text-12",
                picked === evidence.id
                  ? "border-accent-strong bg-accent-subtle text-accent-primary"
                  : "border-subtle text-secondary hover:bg-layer-transparent-hover"
              )}
            >
              {evidence.label}
            </button>
          ))}
        </div>
      )}
      <TextArea
        size="md"
        surface="field"
        autoResize
        maxRows={4}
        // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
        autoFocus
        value={text}
        placeholder={
          picked
            ? "Acrescente o que foi entregue (opcional)"
            : "O que comprova a entrega? Link, documento ou confirmação com nome e data"
        }
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
          if (event.key === "Escape") onCancel();
        }}
        aria-label="Evidência da conclusão"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-11 text-tertiary">
          <Badge variant="neutral" size="xs" label="Sem desfazer" />
          Concluir exige uma evidência e fica no histórico.
        </span>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" stretch="auto" label="Cancelar" onClick={onCancel} />
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            type="submit"
            label={closing ? "Encerrar o risco" : "Concluir"}
            disabled={!valid}
          />
        </div>
      </div>
    </form>
  );
});
