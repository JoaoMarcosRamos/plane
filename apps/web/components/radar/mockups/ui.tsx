/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { TextArea } from "@makeplane/propel/components/text-area";
import { useParams } from "next/navigation";
import { Avatar } from "@makeplane/propel/components/avatar";
import { Icon } from "@makeplane/propel/components/icon";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import {
  AiStar1Outline,
  CheckSquareOutline,
  FlagOutline,
  InboxOutline,
  StateGroupIcon,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import { Breadcrumbs } from "@plane/blocks/breadcrumb";
import { setToast, toastManager } from "@plane/blocks/toast";
import { Header, Row } from "@plane/blocks/layout";
import type { MemberOption } from "@plane/blocks/property-select";
import { cn } from "@plane/utils";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import type { TMockKind, TMockStatus } from "./mock-data";
import { currentToday } from "./mock-data";
import type { TSeverity } from "./interaction-model";
import { KIND_LABEL, STATE_GROUP, STATUS_LABEL, relativeDue, statusColor } from "./interaction-model";
import { copyText } from "./clipboard";
import type { RadarMockupStore } from "./mockup.store";
import { useRadarMockup } from "./provider";

export const useMockupBase = () => {
  const { workspaceSlug } = useParams();
  return `/${workspaceSlug?.toString() ?? ""}/radar/mockups`;
};

const KIND_ICON = {
  action: CheckSquareOutline,
  decision: FlagOutline,
  risk: WarningTriangleOutline,
  issue: InboxOutline,
} satisfies Record<TMockKind, unknown>;

const SEVERITY_TONE: Record<TSeverity, string> = {
  critical: "bg-danger-subtle text-danger-primary",
  warning: "bg-warning-subtle text-warning-primary",
  neutral: "bg-layer-2 text-tertiary",
};

/** Kind glyph in the square slot Plane uses for work item rows, tinted by urgency. */
export function KindIcon({ kind, severity = "neutral" }: { kind: TMockKind; severity?: TSeverity }) {
  return (
    <Tooltip label={KIND_LABEL[kind]}>
      <span className={cn("grid size-7 shrink-0 place-items-center rounded-md", SEVERITY_TONE[severity])}>
        <Icon icon={KIND_ICON[kind]} />
      </span>
    </Tooltip>
  );
}

export function StatusIcon({ status }: { status: TMockStatus }) {
  return (
    <Tooltip label={STATUS_LABEL[status]}>
      <span className="grid size-4 shrink-0 place-items-center">
        <StateGroupIcon
          stateGroup={STATE_GROUP[status]}
          color={statusColor(status)}
          percentage={status === "waiting" || status === "blocked" ? 0.5 : undefined}
          size="lg"
        />
      </span>
    </Tooltip>
  );
}

const DUE_TONE = {
  late: "text-danger-primary font-medium",
  soon: "text-warning-primary font-medium",
  normal: "text-secondary",
  none: "text-placeholder",
};

export function DueChip({
  due,
  className,
  missingLabel,
}: {
  due: string | null;
  className?: string;
  /** What to say when there is no date and that is itself a pending matter ("prazo a definir"). */
  missingLabel?: string;
}) {
  const { label, tone } = relativeDue(due, currentToday());
  if (!due && missingLabel)
    return (
      <Tooltip label="Esta decisão ainda não tem prazo definido">
        <span className={cn("shrink-0 text-12 whitespace-nowrap", "font-medium text-warning-primary", className)}>
          {missingLabel}
        </span>
      </Tooltip>
    );
  return (
    <Tooltip label={due ? `Prazo: ${due.split("-").reverse().join("/")}` : "Sem prazo"}>
      <span className={cn("shrink-0 text-12 whitespace-nowrap tabular-nums", DUE_TONE[tone], className)}>{label}</span>
    </Tooltip>
  );
}

const initials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

/** Without `size`, an enclosing AvatarGroup decides it. */
export const PersonAvatar = observer(function PersonAvatar({
  personId,
  size,
}: {
  personId: string;
  size?: "xs" | "sm" | "md" | "lg";
}) {
  const store = useRadarMockup();
  const person = store.person(personId);
  if (!person) return null;
  return <Avatar size={size} alt={person.name} fallback={initials(person.name)} tooltip={person.name} />;
});

/** Paginated fetcher shape expected by Plane's MemberSelect block, served from mock people. */
export const useMemberOptions = () => {
  const store = useRadarMockup();
  const options: MemberOption[] = store.people.map((person) => ({
    id: person.id,
    display_name:
      person.id === store.meId
        ? `${person.display_name} (você)`
        : person.organization
          ? `${person.display_name} · ${person.organization}`
          : person.display_name,
    name: person.name,
  }));
  return {
    options,
    getValues: async () => ({ results: options }),
    find: (id: string | null | undefined) => options.find((option) => option.id === id) ?? null,
  };
};

type TCrumb = { label: string; href?: string; icon?: ReactNode };

/** Same chrome as AppHeader + RadarHeader, without the stores they read. */
export function MockupHeader({ crumbs, actions }: { crumbs: TCrumb[]; actions?: ReactNode }) {
  return (
    <Row className="flex h-11 w-full shrink-0 items-center gap-2 border-b border-subtle bg-surface-1">
      <Header>
        <Header.LeftItem>
          <Breadcrumbs>
            {crumbs.map((crumb, index) => (
              <Breadcrumbs.Item
                key={crumb.label}
                component={
                  <BreadcrumbLink
                    label={crumb.label}
                    href={crumb.href}
                    icon={crumb.icon}
                    isLast={index === crumbs.length - 1}
                  />
                }
              />
            ))}
          </Breadcrumbs>
        </Header.LeftItem>
        {actions && <Header.RightItem>{actions}</Header.RightItem>}
      </Header>
    </Row>
  );
}

export function SectionTitle({ title, count, trailing }: { title: string; count?: number; trailing?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-1">
      <h2 className="flex items-center gap-2 text-14 font-semibold text-primary">
        {title}
        {count !== undefined && <span className="text-13 font-medium text-tertiary tabular-nums">{count}</span>}
      </h2>
      {trailing}
    </div>
  );
}

/** Copies and says what happened: a success only when the text really reached the clipboard. */
export async function copyWithFeedback(text: string) {
  const copied = await copyText(text);
  if (copied)
    setToast({ type: "success", title: "Mensagem copiada", message: "Cole no seu canal. O RADAR não envia." });
  else
    setToast({
      type: "error",
      title: "Não foi possível copiar",
      message: "Selecione o texto da mensagem e copie manualmente.",
    });
  return copied;
}

/**
 * A message drafted by the agent. Copying it is one thing and recording that it happened is another: the
 * runtime does not send, and the record only appears when the manager says the conversation took place.
 */
export const PreparedMessage = observer(function PreparedMessage({
  to,
  text,
  onChange,
  recordLabel,
  onRecord,
  onCancel,
  hint,
}: {
  to: string;
  text: string;
  onChange: (text: string) => void;
  /** The fact to register after talking to the person, e.g. "Registrar consulta realizada". */
  recordLabel: string;
  onRecord: () => void;
  onCancel: () => void;
  /** Replaces the line about the record, when nothing is recorded (a notice only to be copied). */
  hint?: string;
}) {
  const store = useRadarMockup();
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-subtle bg-layer-1 p-3">
      <div className="flex flex-col gap-2">
        <span className="flex items-center gap-1.5 text-11 font-medium text-tertiary">
          <Icon icon={AiStar1Outline} />
          Mensagem preparada para {to} · o RADAR não envia; copie para o seu canal
        </span>
        <TextArea
          size="md"
          surface="field"
          autoResize
          maxRows={6}
          value={text}
          onChange={(event) => onChange(event.target.value)}
          aria-label={`Mensagem para ${to}`}
        />
        <div className="flex justify-end">
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Copiar mensagem"
            onClick={() => void copyWithFeedback(text)}
          />
        </div>
      </div>
      <div className="flex flex-col gap-2 border-t border-subtle pt-3">
        <span className="text-12 text-secondary">
          {hint ?? `Já falou com ${to}? O registro leva o seu nome e a data de hoje (${dayMonthOf(store.today)}).`}
        </span>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="ghost" size="sm" stretch="auto" label="Cancelar" onClick={onCancel} />
          <Button variant="primary" size="sm" stretch="auto" label={recordLabel} onClick={onRecord} />
        </div>
      </div>
    </div>
  );
});

const dayMonthOf = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

const TONE_CLASS = {
  late: "text-danger-primary",
  soon: "text-warning-primary",
  normal: "text-tertiary",
  warn: "text-warning-primary",
};

/** Small inline signal: "sem notícias há 4 dias", "retorno hoje", "aguardando confirmação". */
export function Signal({ label, tone }: { label: string; tone: keyof typeof TONE_CLASS }) {
  return <span className={cn("shrink-0 text-12 whitespace-nowrap", TONE_CLASS[tone])}>{label}</span>;
}

const UNDO_TIMEOUT = 10_000;

type TToast = { title: string; message?: string };

/**
 * Runs a change that the current rules allow to be taken back, and offers "Desfazer". The undo reverses only
 * what this change did (see undo.ts): later changes, on this item or any other, are kept. Returns false when
 * the change did not apply.
 */
export function withUndo(
  store: RadarMockupStore,
  toast: TToast,
  change: () => boolean | void,
  options: {
    onUndo?: () => void;
    /** When the change did not apply, say it your own way instead of the default "Nada mudou". */
    onSkipped?: () => void;
  } = {}
): boolean {
  const outcome: { ok: boolean | void } = { ok: true };
  const { changed, undo } = store.track(() => {
    outcome.ok = change();
  });
  if (outcome.ok === false || !changed) {
    if (options.onSkipped) options.onSkipped();
    else setToast({ type: "info", title: "Nada mudou", message: toast.message });
    return false;
  }
  const id = setToast({
    type: "success",
    title: toast.title,
    message: toast.message,
    actionItems: [
      {
        label: "Desfazer",
        primary: true,
        onClick: () => {
          const result = undo();
          options.onUndo?.();
          // Undoing a creation can remove the item the panel is showing.
          if (store.openItemId && !store.item(store.openItemId)) store.closeItem();
          if (result.conflicts.length)
            setToast({
              type: "warning",
              title: "Desfeito em parte",
              message: result.conflicts.join(" "),
            });
          else setToast({ type: "info", title: "Desfeito", message: toast.message });
        },
      },
    ],
  });
  // Success toasts close after Base UI's 5s default, too short to read the change and reach "Desfazer".
  toastManager.update(id, { timeout: UNDO_TIMEOUT });
  return true;
}

/**
 * Runs a change that is not taken back: conclusions, approvals, state changes, recorded facts. The toast says
 * so instead of offering an Undo the rules would not honor; a mistake is corrected with a new record.
 */
export function commit(store: RadarMockupStore, toast: TToast, change: () => boolean | void): boolean {
  void store;
  if (change() === false) {
    setToast({ type: "info", title: "Nada mudou", message: toast.message });
    return false;
  }
  setToast({ type: "success", title: toast.title, message: toast.message });
  return true;
}

// ---------------------------------------------------------------- demonstration scenarios (loading, error, partial)

function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Carregando"
      className="overflow-hidden rounded-lg border border-subtle bg-surface-1"
    >
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="flex min-h-[52px] items-center gap-3 border-b border-subtle px-4 py-2 last:border-b-0"
        >
          <span className="size-7 shrink-0 animate-pulse rounded-md bg-layer-3" />
          <span className="flex flex-1 flex-col gap-1.5">
            <span className="h-3 w-2/3 animate-pulse rounded bg-layer-3" />
            <span className="h-2.5 w-1/3 animate-pulse rounded bg-layer-3" />
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * Wraps the content of a screen for the demonstration scenarios. Loading shows placeholders and says nothing
 * about the work; an error says nothing was shown and offers to try again. Neither is ever read as "no
 * pendências".
 */
export const ScenarioGate = observer(function ScenarioGate({ children }: { children: ReactNode }) {
  const store = useRadarMockup();
  if (store.demo.scenario === "loading")
    return (
      <div className="flex flex-col gap-3">
        <p className="px-1 text-13 text-secondary">Carregando o que depende de você…</p>
        <LoadingRows />
      </div>
    );
  if (store.demo.scenario === "error")
    return (
      <Banner
        placement="inline"
        variant="danger"
        title="Não foi possível carregar esta tela"
        description="Nada foi mostrado: isso não quer dizer que não haja pendências. Tente de novo."
        actions={
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label="Tentar novamente"
            onClick={() => store.setScenario("normal")}
          />
        }
      />
    );
  return <>{children}</>;
});

/** Shown over the screens when the data came back incomplete: absence in the lists proves nothing. */
export const PartialNotice = observer(function PartialNotice({ what }: { what: string }) {
  const store = useRadarMockup();
  if (store.demo.scenario !== "partial") return null;
  return (
    <Banner
      placement="inline"
      variant="warning"
      title="Carregamento incompleto"
      description={`${what} Não dá para dizer que não há pendências nas partes que faltam.`}
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label="Carregar de novo"
          onClick={() => store.setScenario("normal")}
        />
      }
    />
  );
});
