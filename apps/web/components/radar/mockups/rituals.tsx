/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { Input } from "@makeplane/propel/components/input";
import { TextArea } from "@makeplane/propel/components/text-area";
import { LinearProgress } from "@makeplane/propel/components/linear-progress";
import { setToast } from "@plane/blocks/toast";
import { cn } from "@plane/utils";
import type { TMockItem } from "./mock-data";
import { addDays, attentionFor, byUrgency, dayMonth, diffDays, nextMonday } from "./interaction-model";
import type { TAttention } from "./interaction-model";
import { useRadarMockup } from "./provider";
import { DueChip, KindIcon, PersonAvatar, commit, withUndo } from "./ui";

/** Fixed commitments of the day, to check that the chosen focus fits (Guia §05). Mock agenda. */
const MOCK_AGENDA = [
  { time: "10:00", title: "1:1 com Carlos", minutes: 30 },
  { time: "14:00", title: "Comitê de projetos", minutes: 90 },
  { time: "16:30", title: "Alinhamento com o Financeiro", minutes: 30 },
];

/** "Abrir o dia": commitments, decisions and deadlines of the day; choose up to three things to protect. */
export const OpenDayDialog = observer(function OpenDayDialog() {
  const store = useRadarMockup();
  const [selected, setSelected] = useState<string[]>([]);
  // Each opening starts from today's focus, if any. Yesterday's focus is not carried over: a new day, a new choice.
  useEffect(() => {
    if (store.ritual === "abrir") setSelected(store.hasFocusToday ? [...store.focus.ids] : []);
  }, [store.ritual, store]);
  const views = store.hojeMine.views;
  const pool = new Map<string, TMockItem>();
  store.hojeMine.attention.forEach((entry) => pool.set(entry.item.id, entry.item));
  views?.fazer.filter((item) => item.due && diffDays(item.due) <= 1).forEach((item) => pool.set(item.id, item));
  views?.decidir.forEach((item) => pool.set(item.id, item));
  views?.aguardando
    .filter((item) => item.followUp && diffDays(item.followUp) <= 0)
    .forEach((item) => pool.set(item.id, item));
  const candidates = [...pool.values()];
  const busy = MOCK_AGENDA.reduce((total, entry) => total + entry.minutes, 0);
  const close = () => store.setRitual(null);
  return (
    <Dialog open={store.ritual === "abrir"} onOpenChange={(open) => !open && close()}>
      <DialogContent size="lg">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>Abrir o dia</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-4">
              <p className="text-13 text-secondary">
                Escolha até 3 coisas para proteger hoje. O resto continua no radar, só não é o foco.
              </p>
              <div className="flex flex-col gap-1 rounded-lg bg-layer-1 p-3 text-13">
                <span className="text-12 font-medium text-secondary">
                  Agenda de hoje (exemplo) · {(busy / 60).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h em
                  compromissos fixos
                </span>
                {MOCK_AGENDA.map((entry) => (
                  <span key={entry.time} className="text-primary">
                    <span className="text-tertiary tabular-nums">{entry.time}</span> {entry.title}
                  </span>
                ))}
              </div>
              <div className="overflow-hidden rounded-lg border border-subtle">
                {candidates.map((item) => {
                  const checked = selected.includes(item.id);
                  const attention = attentionFor(item, store.items, store.personName);
                  return (
                    // oxlint-disable-next-line jsx-a11y/label-has-associated-control -- the checkbox is inside the label
                    <label
                      key={item.id}
                      className="flex cursor-pointer items-center gap-3 border-b border-subtle px-3 py-2 last:border-b-0 hover:bg-layer-transparent-hover"
                    >
                      <Checkbox
                        checked={checked}
                        disabled={!checked && selected.length >= 3}
                        aria-label={`Focar em ${item.title}`}
                        onCheckedChange={(value) =>
                          setSelected((current) =>
                            value ? [...current, item.id] : current.filter((id) => id !== item.id)
                          )
                        }
                      />
                      <KindIcon kind={item.kind} severity={attention?.severity} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-13 font-medium text-primary">{item.title}</span>
                        <span className="block truncate text-12 text-tertiary">{attention?.reason ?? "Para hoje"}</span>
                      </span>
                      <DueChip due={item.due} />
                    </label>
                  );
                })}
              </div>
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <span className="mr-auto text-12 text-tertiary">{selected.length} de 3</span>
          <Button variant="secondary" size="md" stretch="auto" label="Agora não" onClick={close} />
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label="Começar o dia"
            disabled={!selected.length}
            onClick={() => {
              store.completeOpenDay(selected);
              close();
              setToast({
                type: "success",
                title: "Foco de hoje definido",
                message: `${selected.length} ${selected.length === 1 ? "item" : "itens"} no topo de Hoje, só para hoje.`,
              });
            }}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
});

/** "Fechar o dia": what expired, stalled or went silent, one at a time; then choose how tomorrow starts. */
export const CloseDayDialog = observer(function CloseDayDialog() {
  const store = useRadarMockup();
  const [handled, setHandled] = useState<string[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [blocking, setBlocking] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [reason, setReason] = useState("");
  const [proof, setProof] = useState("");
  const [tomorrow, setTomorrow] = useState<string | null>(null);
  const isOpen = store.ritual === "fechar";
  const queue = store.closeDay.filter((entry) => !handled.includes(entry.item.id));
  const size = total ?? store.closeDay.length;
  const current = queue[0];
  const close = () => {
    store.setRitual(null);
    setHandled([]);
    setTotal(null);
    setTomorrow(null);
  };
  /**
   * Each exception is handled in one step. What the rules can take back offers Desfazer, and undoing puts it
   * back in the queue; conclusions and blocks are recorded for good. Nothing leaves the queue if it did not apply.
   */
  const next = (title: string, change?: () => boolean | void, reversible = true) => {
    if (!current) return;
    const id = current.item.id;
    if (total === null) setTotal(store.closeDay.length);
    setBlocking(false);
    setCompleting(false);
    setReason("");
    setProof("");
    if (!change) {
      setHandled((list) => [...list, id]);
      setToast({ type: "info", title, message: current.item.title });
      return;
    }
    const apply = () => {
      const ok = change();
      if (ok !== false) setHandled((list) => [...list, id]);
      return ok;
    };
    if (reversible)
      withUndo(store, { title, message: current.item.title }, apply, {
        onUndo: () => setHandled((list) => list.filter((handledId) => handledId !== id)),
      });
    else commit(store, { title, message: current.item.title }, apply);
  };
  const candidates: TAttention[] = (store.hojeMine.views?.fazer ?? [])
    .concat(store.hojeMine.views?.decidir ?? [])
    .map(
      (item) => attentionFor(item, store.items, store.personName) ?? { item, severity: "neutral" as const, reason: "" }
    )
    .sort(byUrgency)
    .slice(0, 5);
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
      <DialogContent size="lg">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>Fechar o dia</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-4">
              <LinearProgress
                value={size ? Math.round(((size - queue.length) / size) * 100) : 100}
                size="sm"
                variant="brand"
                aria-label="Exceções tratadas"
              />
              {current ? (
                <div className="flex flex-col gap-3">
                  <span className="text-12 text-tertiary">
                    Exceção {size - queue.length + 1} de {size} · o que venceu, travou ou ficou sem resposta
                  </span>
                  <div className="flex items-start gap-3 rounded-lg border border-subtle p-3">
                    <KindIcon kind={current.item.kind} severity="warning" />
                    <div className="min-w-0 flex-1">
                      <p className="text-14 font-medium text-primary">{current.item.title}</p>
                      <p className="text-13 text-warning-primary">{current.reason}</p>
                      {current.item.deliverable && (
                        <p className="mt-1 text-12 text-tertiary">Entrega: {current.item.deliverable}</p>
                      )}
                    </div>
                    {current.item.withIds[0] && <PersonAvatar personId={current.item.withIds[0]} size="sm" />}
                  </div>
                  {blocking ? (
                    <div className="flex gap-2">
                      <Input
                        size="md"
                        // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
                        autoFocus
                        value={reason}
                        placeholder="O que impede avançar?"
                        aria-label="Motivo do bloqueio"
                        onChange={(event) => setReason(event.target.value)}
                      />
                      <Button
                        variant="primary"
                        size="md"
                        stretch="auto"
                        label="Marcar"
                        onClick={() => {
                          next(
                            "Marcado como bloqueado",
                            () => store.run(current.item.id, "block", { note: reason }),
                            false
                          );
                        }}
                      />
                    </div>
                  ) : completing ? (
                    <form
                      className="flex flex-col gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (!proof.trim()) return;
                        next("Concluído", () => store.run(current.item.id, "complete", { note: proof }), false);
                      }}
                    >
                      <TextArea
                        size="md"
                        surface="field"
                        autoResize
                        maxRows={3}
                        // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
                        autoFocus
                        value={proof}
                        placeholder="O que comprova a entrega? Link, documento ou confirmação com nome e data"
                        aria-label="Evidência da conclusão"
                        onChange={(event) => setProof(event.target.value)}
                      />
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-11 text-tertiary">Concluir fica registrado e não pode ser desfeito.</span>
                        <div className="flex gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            stretch="auto"
                            label="Voltar"
                            onClick={() => setCompleting(false)}
                          />
                          <Button
                            variant="primary"
                            size="sm"
                            stretch="auto"
                            type="submit"
                            label="Concluir"
                            disabled={!proof.trim()}
                          />
                        </div>
                      </div>
                    </form>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        size="md"
                        stretch="auto"
                        label="Chegou, concluir"
                        onClick={() => setCompleting(true)}
                      />
                      {current.item.withIds.length > 0 && (
                        <Button
                          variant="primary"
                          size="md"
                          stretch="auto"
                          label="Cobrar amanhã cedo"
                          onClick={() => {
                            next("Retorno marcado para amanhã", () =>
                              store.setFollowUp(current.item.id, addDays(store.today, 1))
                            );
                          }}
                        />
                      )}
                      <Button
                        variant="secondary"
                        size="md"
                        stretch="auto"
                        label="Bloqueado"
                        onClick={() => setBlocking(true)}
                      />
                      <Button
                        variant="secondary"
                        size="md"
                        stretch="auto"
                        label={`Adiar para ${dayMonth(nextMonday())}`}
                        disabled={!!current.item.dueConflict}
                        onClick={() => {
                          next("Adiado · prazo anterior guardado", () =>
                            store.run(current.item.id, "postpone", {
                              date: nextMonday(),
                              note: "renegociado no fechamento do dia",
                            })
                          );
                        }}
                      />
                      <Button
                        variant="ghost"
                        size="md"
                        stretch="auto"
                        label="Pular"
                        onClick={() => next("Fica para amanhã")}
                      />
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <span className="text-13 text-secondary">
                    {size ? "Exceções tratadas." : "Nada venceu nem ficou sem resposta hoje."} Amanhã começa por…
                  </span>
                  <div className="overflow-hidden rounded-lg border border-subtle">
                    {candidates.map(({ item, reason: why }) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setTomorrow(item.id)}
                        className={cn(
                          "flex w-full items-center gap-3 border-b border-subtle px-3 py-2 text-left last:border-b-0 hover:bg-layer-transparent-hover",
                          { "bg-accent-subtle": tomorrow === item.id }
                        )}
                      >
                        <KindIcon kind={item.kind} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-13 font-medium text-primary">{item.title}</span>
                          {why && <span className="block truncate text-12 text-tertiary">{why}</span>}
                        </span>
                        <DueChip due={item.due} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label="Sair" onClick={close} />
          {!current && (
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label="Fechar o dia"
              disabled={!tomorrow}
              onClick={() => {
                store.completeCloseDay(tomorrow);
                setToast({
                  type: "success",
                  title: "Dia fechado",
                  message: `Amanhã começa por: ${store.item(tomorrow)?.title}`,
                });
                close();
              }}
            />
          )}
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
});
