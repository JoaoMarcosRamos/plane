/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable unicorn/no-array-sort, unicorn/no-array-reverse, oxc/no-map-spread -- the app compiles with lib ES2022 (no toSorted/toReversed); every sort and reverse runs on a copy */

import { useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { LinearProgress } from "@makeplane/propel/components/linear-progress";
import { Tab, Tabs, TabsList } from "@makeplane/propel/components/tabs";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { AiStar1Outline, ChevronDownOutline, ProjectsOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import type { IBaseLayoutsBaseGroup } from "@plane/types";
import { BaseKanbanLayout } from "@/components/base-layouts/kanban/layout";
import { BaseListLayout } from "@/components/base-layouts/list/layout";
import type { TMockItem, TMockProject, TMockResult, TMockStatus } from "./mock-data";
import type { TStateGroup } from "./interaction-model";
import {
  STALL_CAUSES,
  STATE_GROUP,
  attentionFor,
  byUrgency,
  dayMonth,
  diffDays,
  isOpen,
  projectNextAction,
  resultProgress,
} from "./interaction-model";
import { ItemRow } from "./item-row";
import type { RadarMockupStore } from "./mockup.store";
import { useRadarMockup } from "./provider";
import { DueChip, KindIcon, MockupHeader, PartialNotice, PersonAvatar, ScenarioGate, useMockupBase } from "./ui";

function projectHealth(store: RadarMockupStore, project: TMockProject) {
  const items = store.itemsOfProject(project.id);
  const open = items.filter((item) => isOpen(item.status));
  return {
    items,
    late: open.filter((item) => item.kind === "action" && item.due && diffDays(item.due) < 0).length,
    decisions: open.filter((item) => item.kind === "decision").length,
    topRisk: Math.max(0, ...open.filter((item) => item.kind === "risk").map((item) => item.riskScore ?? 0)),
    nextAction: projectNextAction(store.items, project.id),
  };
}

/** The project's result, not the share of finished tasks (laws 1 and 2). */
function ResultMeter({ result, wide = false }: { result: TMockResult; wide?: boolean }) {
  const progress = resultProgress(result);
  if (!("measure" in result) || progress === null)
    return <span className="text-12 text-tertiary">Critério: {"criterion" in result ? result.criterion : ""}</span>;
  const { baseline, current, target, unit } = result.measure;
  return (
    <div className={wide ? "flex w-[260px] flex-col gap-1" : "flex flex-col gap-1"}>
      <LinearProgress value={progress} size="sm" variant="brand" aria-label={result.statement} />
      <span className="text-11 text-tertiary tabular-nums">
        {baseline}
        {unit} →{" "}
        <b className="text-secondary">
          {current}
          {unit}
        </b>{" "}
        · meta {target}
        {unit}
      </span>
    </div>
  );
}

/**
 * "Sem próxima ação" and "Em dia" are claims about everything in the project. They are only made when all of
 * it was loaded; with partial data the badge says so instead of guessing.
 */
function HealthBadges({
  health,
  active = true,
  complete = true,
}: {
  health: ReturnType<typeof projectHealth>;
  active?: boolean;
  complete?: boolean;
}) {
  if (!complete) return <Badge variant="warning" size="sm" label="Dados incompletos" />;
  const stalled = active && !health.nextAction;
  const calm = active && !health.late && !health.decisions && health.topRisk < 15 && !stalled;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {stalled && <Badge variant="danger" size="sm" label="Sem próxima ação" />}
      {health.late > 0 && (
        <Badge variant="danger" size="sm" label={`${health.late} atrasado${health.late > 1 ? "s" : ""}`} />
      )}
      {health.decisions > 0 && (
        <Badge
          variant="warning"
          size="sm"
          label={`${health.decisions} decisão${health.decisions > 1 ? "ões" : ""} pendente${health.decisions > 1 ? "s" : ""}`}
        />
      )}
      {health.topRisk >= 15 && <Badge variant="orange" size="sm" label={`Risco ${health.topRisk}`} />}
      {calm && <Badge variant="success" size="sm" label="Em dia" />}
    </div>
  );
}

export const RadarMockupProjects = observer(function RadarMockupProjects() {
  const store = useRadarMockup();
  const base = useMockupBase();
  return (
    <>
      <MockupHeader crumbs={[{ label: "Projetos", icon: <Icon icon={ProjectsOutline} /> }]} />
      <div className="mx-auto flex w-full max-w-[1040px] flex-col gap-6 px-4 py-6 md:px-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-20 font-semibold text-primary">Projetos</h1>
          <p className="text-13 text-secondary">
            O que está acontecendo em cada frente, sem precisar abrir uma por uma.
          </p>
        </header>
        <PartialNotice what="Parte dos itens dos projetos não carregou, então a saúde de cada projeto fica sem veredito." />
        <ScenarioGate>
          {store.projects.length === 0 && (
            <p className="rounded-lg border border-subtle px-4 py-8 text-center text-13 text-tertiary">
              Nenhum projeto ainda. Eles aparecem aqui quando forem importados ou criados.
            </p>
          )}
          <div className="overflow-hidden rounded-lg border border-subtle">
            {store.projects.map((project) => {
              const health = projectHealth(store, project);
              return (
                <Link
                  key={project.id}
                  href={`${base}/projetos/${project.id}/`}
                  className="flex min-h-[64px] items-center gap-4 border-b border-subtle px-4 py-3 last:border-b-0 hover:bg-layer-transparent-hover"
                >
                  <span className="grid size-8 shrink-0 place-items-center rounded-md bg-layer-2 text-11 font-semibold text-secondary">
                    {project.identifier}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 truncate text-13 font-medium text-primary">
                      {project.title}
                      {project.status === "on_hold" && <Badge variant="grey" size="xs" label="Pausado" />}
                    </p>
                    <p className="truncate text-12 text-tertiary">{project.objective}</p>
                  </div>
                  <div className="hidden w-[260px] md:block">
                    <HealthBadges health={health} active={project.status === "active"} complete={store.complete} />
                  </div>
                  <div className="hidden w-[180px] lg:block">
                    <ResultMeter result={project.result} />
                  </div>
                  <DueChip due={project.due} className="w-14 text-right" />
                  <PersonAvatar personId={project.ownerId} size="sm" />
                </Link>
              );
            })}
          </div>
        </ScenarioGate>
      </div>
    </>
  );
});

const LIST_GROUPS: IBaseLayoutsBaseGroup[] = [
  { id: "attention", name: "Precisa de atenção" },
  { id: "open", name: "Em andamento" },
  { id: "closed", name: "Concluído" },
];

const BOARD_GROUPS: (IBaseLayoutsBaseGroup & { states: TStateGroup[] })[] = [
  { id: "todo", name: "Planejado", states: ["backlog", "unstarted"] },
  { id: "doing", name: "Em andamento", states: ["started"] },
  { id: "done", name: "Concluído", states: ["completed", "cancelled"] },
];

/**
 * The status a drop into a board column asks for, for this kind of item. It is only a request: the rules
 * decide, exactly as for the buttons and the state selector.
 */
const statusForColumn = (item: TMockItem, column: string): TMockStatus | null => {
  const wanted: Record<string, Partial<Record<TMockItem["kind"], TMockStatus>>> = {
    todo: { action: "todo", decision: "proposed", risk: "identified" },
    doing: { action: "in_progress", risk: "mitigating" },
    done: { action: "done", decision: "decided", risk: "closed" },
  };
  return wanted[column]?.[item.kind] ?? null;
};

const ProjectListRow = observer(function ProjectListRow({ item }: { item: TMockItem }) {
  const store = useRadarMockup();
  const attention = attentionFor(item, store.items, store.personName);
  return <ItemRow item={item} showProject={false} severity={attention?.severity} reason={attention?.reason} />;
});

const BoardCard = observer(function BoardCard({ item }: { item: TMockItem }) {
  const store = useRadarMockup();
  const attention = attentionFor(item, store.items, store.personName);
  return (
    <button
      type="button"
      onClick={() => store.openItemById(item.id)}
      className="flex w-full flex-col gap-2 rounded-md border border-subtle bg-layer-2 p-3 text-left shadow-raised-100 hover:bg-layer-2-hover"
    >
      <span className="flex items-start gap-2">
        <KindIcon kind={item.kind} severity={attention?.severity ?? "neutral"} />
        <span className="line-clamp-2 text-13 font-medium text-primary">{item.title}</span>
      </span>
      <span className="flex items-center justify-between gap-2">
        <DueChip due={isOpen(item.status) ? item.due : null} />
        <PersonAvatar personId={item.withIds[0] ?? item.ownerId} size="xs" />
      </span>
    </button>
  );
});

export const RadarMockupProject = observer(function RadarMockupProject({ projectId }: { projectId: string }) {
  const store = useRadarMockup();
  const base = useMockupBase();
  const [view, setView] = useState<"list" | "board">("list");
  const [reviewing, setReviewing] = useState(false);
  const project = store.project(projectId);
  const items = project ? store.itemsOfProject(project.id) : [];
  const byId = Object.fromEntries(items.map((item) => [item.id, item]));
  if (!project) return <p className="p-8 text-13 text-secondary">Projeto não encontrado.</p>;
  const health = projectHealth(store, project);
  const next = health.nextAction;
  const unstall = (cause: (typeof STALL_CAUSES)[number]["key"]) => {
    const item = store.unstallProject(project.id, cause);
    setToast({ type: "success", title: "Combinado de desbloqueio criado", message: item?.title ?? "" });
    if (item) store.openItemById(item.id);
  };
  const listIds = {
    attention: items
      .map((item) => attentionFor(item, store.items, store.personName))
      .filter((entry) => !!entry)
      .sort(byUrgency)
      .map((entry) => entry.item.id),
    open: items
      .filter((item) => isOpen(item.status) && !attentionFor(item, store.items, store.personName))
      .map((item) => item.id),
    closed: items.filter((item) => !isOpen(item.status)).map((item) => item.id),
  };
  const boardIds = Object.fromEntries(
    BOARD_GROUPS.map((group) => [
      group.id,
      items.filter((item) => group.states.includes(STATE_GROUP[item.status])).map((item) => item.id),
    ])
  );
  const review = () => {
    setReviewing(true);
    window.setTimeout(() => {
      const result = store.reviewProjectRisks(project.id);
      setReviewing(false);
      if (result.ok)
        setToast({
          type: "success",
          title: "O RADAR terminou a revisão",
          message: "1 proposta foi para a sua Inbox, para você revisar.",
        });
      else setToast({ type: "error", title: "A revisão não foi feita", message: result.error });
    }, 1400);
  };
  return (
    <>
      <MockupHeader
        crumbs={[
          { label: "Projetos", href: `${base}/projetos/`, icon: <Icon icon={ProjectsOutline} /> },
          { label: project.title },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Tabs variant="contained" value={view} onValueChange={(value) => setView(value as "list" | "board")}>
              <TabsList>
                <Tab value="list" label="Lista" />
                <Tab value="board" label="Quadro" />
              </TabsList>
            </Tabs>
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              icon={<Icon icon={AiStar1Outline} />}
              label={reviewing ? "Revisando…" : "Revisar riscos"}
              disabled={reviewing || store.readOnly}
              onClick={review}
            />
          </div>
        }
      />
      <div className="flex min-h-0 flex-1 flex-col gap-5 px-4 py-6 md:px-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-20 font-semibold text-primary">{project.title}</h1>
            <p className="text-13 text-secondary">Objetivo: {project.objective}</p>
          </div>
          <div className="flex items-center gap-4">
            <HealthBadges health={health} active={project.status === "active"} complete={store.complete} />
            <PersonAvatar personId={project.ownerId} size="sm" />
          </div>
        </header>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-2 rounded-lg border border-subtle bg-layer-1 p-3">
            <span className="text-12 text-tertiary">Resultado esperado</span>
            <span className="text-14 font-medium text-primary">{project.result.statement}</span>
            <ResultMeter result={project.result} wide />
          </div>
          <div className="flex flex-col gap-2 rounded-lg border border-subtle bg-layer-1 p-3">
            <span className="text-12 text-tertiary">Próxima ação</span>
            {next ? (
              <button type="button" className="text-left" onClick={() => store.openItemById(next.id)}>
                <span className="block text-14 font-medium text-primary hover:underline">
                  {next.nextStep ?? next.title}
                </span>
                <span className="text-12 text-secondary">
                  {next.nextStep ? `${next.title} · ` : ""}
                  {next.withIds.length ? `com ${next.withIds.map(store.personName).join(", ")}` : "com você"}
                  {next.due ? ` · prazo ${dayMonth(next.due)}` : ""}
                </span>
              </button>
            ) : !store.complete ? (
              <span className="text-13 text-warning-primary">
                Não foi possível confirmar a próxima ação: os itens do projeto não carregaram por completo.
              </span>
            ) : (
              <span className="text-13 text-danger-primary">
                Nenhum combinado que alguém possa iniciar. Projeto sem próxima ação está parado, mesmo que o status diga
                o contrário.
              </span>
            )}
            <div>
              <Menu>
                <MenuTrigger
                  render={
                    <Button
                      variant={next ? "ghost" : "secondary"}
                      size="sm"
                      stretch="auto"
                      label="Projeto travado?"
                      icon={<Icon icon={ChevronDownOutline} />}
                      iconPosition="end"
                    />
                  }
                />
                <MenuContent side="bottom" align="start">
                  {STALL_CAUSES.map((cause) => (
                    <MenuItem key={cause.key} label={cause.label} onClick={() => unstall(cause.key)} />
                  ))}
                </MenuContent>
              </Menu>
            </div>
          </div>
        </div>
        {view === "list" ? (
          <div className="min-h-[360px] overflow-hidden rounded-lg border border-subtle">
            <BaseListLayout
              items={byId}
              groups={LIST_GROUPS}
              groupedItemIds={listIds}
              renderItem={(item) => <ProjectListRow item={byId[item.id]} />}
            />
          </div>
        ) : (
          <div className="h-[520px] overflow-hidden rounded-lg border border-subtle">
            <BaseKanbanLayout
              items={byId}
              groups={BOARD_GROUPS}
              groupedItemIds={boardIds}
              enableDragDrop
              groupClassName="w-[300px]"
              onDrop={async (sourceId, _destinationId, _sourceGroupId, destinationGroupId) => {
                const item = byId[sourceId];
                const status = item ? statusForColumn(item, destinationGroupId) : null;
                if (!item || !status) {
                  setToast({
                    type: "info",
                    title: "Movimento não se aplica",
                    message: "Este item não vai para essa coluna.",
                  });
                  return;
                }
                const result = store.moveStatus(item.id, status);
                // Moving is a request: concluding needs evidence, blocking a reason, deciding its conditions.
                if (result.kind === "flow") {
                  store.openItemById(item.id, { key: result.via });
                  setToast({ type: "info", title: "Falta um passo", message: result.note });
                } else if (result.kind === "refused")
                  setToast({ type: "info", title: "Esse movimento não está disponível", message: result.reason });
              }}
              renderItem={(item) => <BoardCard item={byId[item.id]} />}
            />
          </div>
        )}
      </div>
    </>
  );
});
