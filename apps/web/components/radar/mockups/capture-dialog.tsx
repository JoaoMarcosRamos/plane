/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Dialog, DialogActions, DialogBody, DialogContent, DialogMain } from "@makeplane/propel/components/dialog";
import { Icon } from "@makeplane/propel/components/icon";
import { Input } from "@makeplane/propel/components/input";
import { Shortcut } from "@makeplane/propel/components/shortcut";
import { AiStar1Outline, DueDateOutline, InboxOutline, ProjectsOutline, RefreshOutline } from "@makeplane/propel/icons";
import { KIND_LABEL, captureGap, dayMonth, parseCapture, relativeDue } from "./interaction-model";
import { useRadarMockup } from "./provider";
import { PersonAvatar, withUndo } from "./ui";

const EXAMPLES = [
  "Carlos organizar a terceirização do suporte até o fim do mês",
  "Cobrar Carlos sobre o orçamento até sexta",
  "Decidir amanhã se seguimos com a XPTO",
  "Risco: ERP pode atrasar por falta de dados",
  "Ideia para o comitê de IA",
];

/** "+ Novo": one field, never a form (§8). Guesses are shown, never required. */
export const RadarMockupCaptureDialog = observer(function RadarMockupCaptureDialog() {
  const store = useRadarMockup();
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  // The answer to the one gap question; cleared whenever the text changes.
  const [answer, setAnswer] = useState<{ field: "followUp" | "due"; value: string } | null>(null);
  const parsed = parseCapture(text, store.people, store.projects, store.meId);
  const guess = {
    ...parsed,
    ...(answer?.field === "due" ? { due: answer.value } : {}),
    ...(answer?.field === "followUp" ? { followUp: answer.value } : {}),
  };
  const gap = answer ? null : captureGap(parsed, store.personName);
  const project = store.project(guess.projectId);
  const close = () => {
    setText("");
    setAnswer(null);
    store.setCaptureOpen(false);
  };
  const submit = () => {
    if (!guess.title) return;
    const where = guess.kind && guess.kind !== "issue" ? "item" : "inbox";
    withUndo(
      store,
      {
        title: where === "inbox" ? "Guardado na Inbox" : `${KIND_LABEL[guess.kind ?? "issue"]} criado`,
        message: guess.title,
      },
      () => {
        const result = store.capture(guess);
        if (result.where === "item") store.openItemById(result.id);
      }
    );
    close();
  };
  return (
    <Dialog
      open={store.captureOpen}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent size="lg">
        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <DialogMain>
            <DialogBody>
              <div className="flex flex-col gap-3 pt-2">
                <Input
                  ref={inputRef}
                  size="xl"
                  // oxlint-disable-next-line jsx-a11y/no-autofocus -- the field was just opened by the user's own action
                  autoFocus
                  value={text}
                  onChange={(event) => {
                    setText(event.target.value);
                    setAnswer(null);
                  }}
                  placeholder="Escreva qualquer coisa. O RADAR organiza depois."
                  aria-label="Capturar"
                />
                {text.trim() ? (
                  <div className="flex min-h-6 flex-wrap items-center gap-2" aria-live="polite">
                    {guess.kind ? (
                      <Badge variant="brand" size="sm" label={KIND_LABEL[guess.kind]} />
                    ) : (
                      <Badge
                        variant="neutral"
                        size="sm"
                        startIcon={<Icon icon={InboxOutline} />}
                        label="Vai para a Inbox"
                      />
                    )}
                    {guess.due && (
                      <Badge
                        variant="neutral"
                        size="sm"
                        startIcon={<Icon icon={DueDateOutline} />}
                        label={`${relativeDue(guess.due).label} · ${guess.due.split("-").reverse().slice(0, 2).join("/")}`}
                      />
                    )}
                    {guess.personIds.map((id) => (
                      <span key={id} className="flex items-center gap-1 text-12 text-secondary">
                        <PersonAvatar personId={id} size="xs" />
                        {store.personName(id)}
                      </span>
                    ))}
                    {project && (
                      <Badge
                        variant="neutral"
                        size="sm"
                        startIcon={<Icon icon={ProjectsOutline} />}
                        label={project.title}
                      />
                    )}
                    {guess.followUp && (
                      <Badge
                        variant="neutral"
                        size="sm"
                        startIcon={<Icon icon={RefreshOutline} />}
                        label={`retorno ${dayMonth(guess.followUp)}`}
                      />
                    )}
                  </div>
                ) : null}
                {text.trim() && gap && (
                  <div className="flex flex-wrap items-center gap-2 rounded-md bg-layer-1 px-3 py-2">
                    <span className="flex items-center gap-1.5 text-13 text-primary">
                      <Icon icon={AiStar1Outline} />
                      {gap.text}
                    </span>
                    {gap.options.map((option) => (
                      <Button
                        key={option.label}
                        variant="secondary"
                        size="sm"
                        stretch="auto"
                        label={option.label}
                        onClick={() => {
                          setAnswer({ field: gap.field, value: option.value });
                          // The option disappears once answered: keep Enter working on the field.
                          inputRef.current?.focus();
                        }}
                      />
                    ))}
                    <span className="text-11 text-tertiary">ou deixe para depois</span>
                  </div>
                )}
                {!text.trim() && (
                  <div className="flex flex-wrap gap-1.5">
                    {EXAMPLES.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => setText(example)}
                        className="rounded-full border border-subtle px-2.5 py-1 text-12 text-secondary hover:bg-layer-transparent-hover"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <div className="flex w-full items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-11 text-tertiary">
                <Icon icon={AiStar1Outline} />
                Tipo, prazo, pessoas e projeto são sugestões. Clique no item criado para corrigir.
              </span>
              <div className="flex items-center gap-2">
                <Shortcut keys="Esc" />
                <Button
                  variant="primary"
                  size="md"
                  stretch="auto"
                  type="submit"
                  label="Criar"
                  disabled={!guess.title}
                />
              </div>
            </div>
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
