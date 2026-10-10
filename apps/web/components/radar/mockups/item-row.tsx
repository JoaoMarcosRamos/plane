/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { AvatarGroup } from "@makeplane/propel/components/avatar-group";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { cn } from "@plane/utils";
import type { TMockItem } from "./mock-data";
import type { TSeverity, TVerb } from "./interaction-model";
import {
  KIND_LABEL,
  STATUS_LABEL,
  executorsOf,
  followUpState,
  isOpen,
  pendingInforms,
  primaryVerb,
  silentDays,
} from "./interaction-model";
import type { RadarMockupStore } from "./mockup.store";
import { useRadarMockup } from "./provider";
import { DueChip, KindIcon, PersonAvatar, Signal, StatusIcon, commit } from "./ui";

/** Verbs that need nothing else run straight from the row. They are state changes or recorded facts: no Undo. */
const INSTANT: Partial<Record<TVerb["key"], string>> = {
  start: "Iniciado",
  resume: "Retomado",
  confirm: "Confirmação registrada por você",
};

/**
 * One gesture per verb. Anything that needs a line of text, a person, a date, evidence or a prepared message
 * (decide, nudge, complete, delegate) opens the item with that verb ready: concluding always asks for the
 * evidence, so it is never a bare click.
 */
export function runVerbFromRow(store: RadarMockupStore, item: TMockItem, verb: TVerb) {
  if (!INSTANT[verb.key]) {
    store.openItemById(item.id, { key: verb.key, personId: verb.personId });
    return;
  }
  commit(store, { title: INSTANT[verb.key] ?? verb.label, message: item.title }, () =>
    store.run(item.id, verb.key, { personId: verb.personId })
  );
}

type Props = {
  item: TMockItem;
  severity?: TSeverity;
  reason?: string;
  showProject?: boolean;
  quiet?: boolean;
  /** Which secondary signal matters in this list. */
  signal?: "auto" | "followUp" | "inform" | "none";
  /** Chosen as one of today's focus items. */
  pinned?: boolean;
};

export const ItemRow = observer(function ItemRow({
  item,
  severity,
  reason,
  showProject = true,
  quiet = false,
  signal = "auto",
  pinned = false,
}: Props) {
  const store = useRadarMockup();
  const verb = primaryVerb(item, store.meId, store.personName);
  const project = store.project(item.projectId);
  const people = executorsOf(item);
  const open = isOpen(item.status);
  const silent = silentDays(item, store.meId);
  const followUp = followUpState(item);
  const informs = pendingInforms(item);
  const base =
    reason ??
    (item.status === "blocked"
      ? `Bloqueado · ${item.blockedReason ?? "motivo a confirmar"}`
      : item.kind === "action"
        ? STATUS_LABEL[item.status]
        : KIND_LABEL[item.kind]);
  const subtitle = [base, showProject ? project?.title : null].filter(Boolean).join(" · ");
  const secondary =
    signal === "none"
      ? null
      : signal === "inform" || (!open && informs.length)
        ? { label: `falta comunicar ${informs.map(store.personName).join(", ")}`, tone: "warn" as const }
        : signal === "followUp" && followUp
          ? followUp
          : silent
            ? { label: `sem notícias há ${silent} dias`, tone: "warn" as const }
            : open && item.confirmation?.state === "pending"
              ? { label: "aguardando confirmação", tone: "normal" as const }
              : followUp && signal === "auto" && followUp.tone !== "normal"
                ? followUp
                : null;
  const rowVerb = !open && informs.length ? { key: "inform" as const, label: "Comunicar" } : open ? verb : undefined;
  // Who executes and who answers, compactly: the executor is not necessarily the one responsible.
  const executes = item.withIds.filter((id) => id !== item.ownerId);
  const answers = item.ownerId !== store.meId || executes.length ? store.personName(item.ownerId) : null;
  const roles = [
    executes.length ? `Executa ${executes.map(store.personName).join(", ")}` : null,
    answers ? `Responde ${answers}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- a row holding another button cannot itself be a button
      role="button"
      tabIndex={0}
      aria-label={`Abrir ${item.title}`}
      onClick={() => store.openItemById(item.id)}
      onKeyDown={(event) => {
        // Only when the row itself has focus: the button inside handles its own keys.
        if ((event.key === "Enter" || event.key === " ") && event.target === event.currentTarget) {
          event.preventDefault();
          store.openItemById(item.id);
        }
      }}
      className={cn(
        "group flex min-h-[52px] w-full cursor-pointer items-center gap-3 border-b border-subtle bg-layer-transparent px-4 py-2 text-13 outline-none last:border-b-0 hover:bg-layer-transparent-hover focus-visible:bg-layer-transparent-hover",
        { "bg-layer-transparent-selected": store.openItemId === item.id }
      )}
    >
      <KindIcon kind={item.kind} severity={open ? (severity ?? "neutral") : "neutral"} />
      <div className="min-w-0 flex-1">
        <p className="flex min-w-0 items-center gap-2">
          {pinned && <Badge variant="brand" size="xs" label="Foco" />}
          <span
            className={cn("truncate font-medium text-primary", {
              "text-tertiary line-through": !open && !informs.length,
            })}
          >
            {item.title}
          </span>
        </p>
        <p className="flex min-w-0 items-center gap-2 text-12">
          <span
            className={cn("truncate", {
              "text-danger-primary": severity === "critical",
              "text-warning-primary": severity === "warning",
              "text-tertiary": !severity || severity === "neutral",
            })}
          >
            {subtitle}
          </span>
          {secondary && <Signal label={secondary.label} tone={secondary.tone} />}
          {roles && (
            <span className="hidden truncate text-11 text-tertiary lg:inline" data-testid="roles">
              {roles}
            </span>
          )}
        </p>
      </div>
      <div className="hidden items-center gap-3 sm:flex">
        <StatusIcon status={item.status} />
        <DueChip
          due={open ? item.due : null}
          className="w-16 text-right"
          missingLabel={open && item.kind === "decision" ? "prazo a definir" : undefined}
        />
        <AvatarGroup size="xs" max={2} label={roles || people.map(store.personName).join(", ")}>
          {people.map((id) => (
            <PersonAvatar key={id} personId={id} />
          ))}
        </AvatarGroup>
      </div>
      {rowVerb && (
        <div className={cn("w-[152px] shrink-0 text-right", { "opacity-0 group-hover:opacity-100": quiet })}>
          <Button
            variant={quiet ? "ghost" : "secondary"}
            size="sm"
            stretch="auto"
            label={rowVerb.label}
            disabled={store.readOnly}
            onClick={(event) => {
              event.stopPropagation();
              runVerbFromRow(store, item, rowVerb);
            }}
          />
        </div>
      )}
    </div>
  );
});
