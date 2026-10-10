/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { Tab, Tabs, TabsList } from "@makeplane/propel/components/tabs";
import {
  AiStar1Outline,
  CheckSquareOutline,
  HistoryOutline,
  HomeOutline,
  MoreHorizontalOutline,
} from "@makeplane/propel/icons";
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import { cn } from "@plane/utils";
import { Input } from "@makeplane/propel/components/input";
import type { TMockItem, TMockWeekResult } from "./mock-data";
import type { TRelational, TRitual } from "./interaction-model";
import {
  RELATIONAL,
  RITUAL_LABEL,
  attentionFor,
  byWhen,
  dayMonth,
  diffDays,
  greeting,
  isOpen,
  longDate,
} from "./interaction-model";
import { RadarMockupFirstUse } from "./first-use";
import { ItemRow } from "./item-row";
import { useRadarMockup } from "./provider";
import { MockupHeader, PartialNotice, PersonAvatar, ScenarioGate, SectionTitle, useMockupBase } from "./ui";

/** Views the "partial" scenario leaves out: absence there proves nothing. */
const UNLOADED_WHEN_PARTIAL = new Set<TRelational>(["aguardando", "informar"]);

type TView = "atencao" | TRelational;

function List({ children }: { children: ReactNode }) {
  return <div className="overflow-hidden rounded-lg border border-subtle bg-surface-1">{children}</div>;
}

const WithAttention = observer(function WithAttention({
  items,
  quiet,
  signal,
}: {
  items: TMockItem[];
  quiet?: boolean;
  signal?: "auto" | "followUp" | "inform";
}) {
  const store = useRadarMockup();
  return (
    <List>
      {items.map((item) => {
        const attention = attentionFor(item, store.items, store.personName);
        return (
          <ItemRow
            key={item.id}
            item={item}
            severity={attention?.severity}
            reason={attention?.reason}
            quiet={quiet}
            signal={signal}
            pinned={store.isFocus(item.id)}
          />
        );
      })}
    </List>
  );
});

const RESULT_STATE: Record<TMockWeekResult["state"], { label: string; dot: string }> = {
  open: { label: "Em curso", dot: "bg-accent-primary" },
  met: { label: "Atingido", dot: "bg-success-primary" },
  partial: { label: "Parcial", dot: "bg-warning-primary" },
  missed: { label: "Não atingido", dot: "bg-danger-primary" },
};

/** One result: a single line that opens to the full sentence, or to the gap when "how we will know" is missing. */
const ResultRow = observer(function ResultRow({ result }: { result: TMockWeekResult }) {
  const store = useRadarMockup();
  const [open, setOpen] = useState(false);
  const [how, setHow] = useState("");
  const project = store.project(result.projectId);
  const gap = !result.howWeKnow;
  return (
    <div className="border-b border-subtle last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-layer-transparent-hover"
      >
        <span className={cn("size-2 shrink-0 rounded-full", RESULT_STATE[result.state].dot)} />
        <span className="min-w-0 flex-1 truncate text-13">
          <span className="font-medium text-primary">{result.title}</span>
          {gap ? (
            <span className="text-warning-primary"> · como saberemos: a confirmar</span>
          ) : (
            <span className="text-tertiary"> · como saberemos: {result.howWeKnow}</span>
          )}
        </span>
        {project && <span className="hidden truncate text-12 text-tertiary md:inline">{project.title}</span>}
        <span className="w-20 shrink-0 text-right text-12 text-secondary">{RESULT_STATE[result.state].label}</span>
      </button>
      {open && (
        <div className="flex flex-col gap-2 bg-layer-1 px-4 py-3 text-13">
          {gap ? (
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (!how.trim()) return;
                store.setWeekResultHow(result.id, how);
                setHow("");
              }}
            >
              <Input
                size="md"
                value={how}
                placeholder="Como saberemos que deu certo? Um número ou um critério observável"
                aria-label="Como saberemos"
                onChange={(event) => setHow(event.target.value)}
              />
              <Button
                variant="secondary"
                size="md"
                stretch="auto"
                type="submit"
                label="Salvar"
                disabled={!how.trim()}
              />
            </form>
          ) : (
            <p className="text-secondary">
              <span className="font-medium text-primary">Como saberemos:</span> {result.howWeKnow}
            </p>
          )}
        </div>
      )}
    </div>
  );
});

/** Up to three results for the week, one line each (Metodologia §02, Guia §01). */
const WeekResults = observer(function WeekResults() {
  const store = useRadarMockup();
  const base = useMockupBase();
  if (!store.weekResults.length) return null;
  return (
    <section className="flex flex-col gap-1.5" aria-label="Resultados da semana">
      <SectionTitle
        title="Resultados da semana"
        trailing={
          store.weekResults.length < 3 ? (
            <Link href={`${base}/revisao/`} className="text-12 text-accent-primary hover:underline">
              + resultado
            </Link>
          ) : null
        }
      />
      <List>
        {store.weekResults.map((result) => (
          <ResultRow key={result.id} result={result} />
        ))}
      </List>
    </section>
  );
});

/** Only after a real gap: two days or more without a review (Guia §05, "Fiquei alguns dias sem usar"). */
const SinceLastReview = observer(function SinceLastReview() {
  const store = useRadarMockup();
  const { expired, silent } = store.since;
  const last = store.lastReview;
  const away = last ? diffDays(store.today, last) : 0;
  if (!last || store.sinceDismissed || away < 2 || (!expired.length && !silent.length)) return null;
  return (
    <Banner
      placement="inline"
      variant="info"
      icon={<Icon icon={HistoryOutline} />}
      title={`Você não revisa desde ${dayMonth(last)} (${away} dias)`}
      description={[
        expired.length ? `${expired.length} combinados venceram` : null,
        silent.length ? `${silent.length} sem notícias de quem executa` : null,
      ]
        .filter(Boolean)
        .join(" · ")}
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label="Retomar"
          onClick={() => store.setRitual("fechar")}
        />
      }
      dismissLabel="Dispensar"
      onDismiss={store.dismissSince}
    />
  );
});

/**
 * One ritual offered for the moment of the day, from the times chosen in the first use and what was already
 * done; the others stay one click away in the menu. A ritual done in its period stops being offered.
 */
const RitualControl = observer(function RitualControl() {
  const store = useRadarMockup();
  const base = useMockupBase();
  const router = useRouter();
  const { now, reviewDue, weeklyDoneOn } = store.ritualNow;
  const open = (ritual: TRitual) => (ritual === "revisao" ? router.push(`${base}/revisao/`) : store.setRitual(ritual));
  const describe = (ritual: TRitual) => {
    if (ritual === "revisao")
      return reviewDue ? "Pendente" : weeklyDoneOn ? `Concluída em ${dayMonth(weeklyDoneOn)}` : undefined;
    const done = ritual === "abrir" ? store.marks.openedOn : store.marks.closedOn;
    return done === store.today ? "Feito hoje" : undefined;
  };
  return (
    <div className="flex items-center gap-1">
      {now && (
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={RITUAL_LABEL[now]}
          disabled={store.readOnly}
          onClick={() => open(now)}
        />
      )}
      <Menu>
        <MenuTrigger
          render={
            <IconButton variant="ghost" size="sm" aria-label="Rituais" icon={<Icon icon={MoreHorizontalOutline} />} />
          }
        />
        <MenuContent side="bottom" align="end">
          {(Object.keys(RITUAL_LABEL) as TRitual[]).map((ritual) => (
            <MenuItem
              key={ritual}
              label={RITUAL_LABEL[ritual]}
              description={describe(ritual)}
              onClick={() => open(ritual)}
            />
          ))}
        </MenuContent>
      </Menu>
    </div>
  );
});

export const RadarMockupToday = observer(function RadarMockupToday() {
  const store = useRadarMockup();
  const base = useMockupBase();
  const [scope, setScope] = useState<"me" | "team">("me");
  const [view, setView] = useState<TView>("atencao");
  const hoje = scope === "me" ? store.hojeMine : store.hojeTeam;
  const views = hoje.views;
  const partial = store.demo.scenario === "partial";
  const suggestions = store.visibleInbox.filter(
    (entry) => entry.source === "agente" && !!entry.suggestion?.relation
  ).length;
  const owners = [...new Set(hoje.attention.map((entry) => entry.item.ownerId))];
  const tomorrow = store.tomorrowFirstItem;
  const { focusOpen, focusDone, alerts, count } = store.atencao;
  // Consultar and Informar only appear when they hold something (§23.5, few mental objects).
  const tabs = RELATIONAL.filter(
    (entry) =>
      !views ||
      views[entry.key].length > 0 ||
      entry.key === view ||
      !["consultar", "informar"].includes(entry.key) ||
      (partial && UNLOADED_WHEN_PARTIAL.has(entry.key))
  );
  const hint =
    view === "atencao"
      ? "Decisões que vencem, atrasos, bloqueios, retornos sem resposta, riscos em acompanhamento e prazos divergentes."
      : RELATIONAL.find((entry) => entry.key === view)?.hint;
  const unloaded = (key: TRelational) => partial && UNLOADED_WHEN_PARTIAL.has(key);
  const checked = `Conferido às ${store.now.time} com todas as fontes carregadas.`;

  if (scope === "me" && store.firstUse) return <RadarMockupFirstUse />;

  return (
    <>
      <MockupHeader
        crumbs={[{ label: "Hoje", icon: <Icon icon={HomeOutline} /> }]}
        actions={
          <Tabs variant="contained" value={scope} onValueChange={(value) => setScope(value as "me" | "team")}>
            <TabsList>
              <Tab value="me" label="Meu" />
              <Tab value="team" label="Equipe" />
            </TabsList>
          </Tabs>
        }
      />
      <div className="mx-auto flex w-full max-w-[960px] flex-col gap-5 px-4 py-6 md:px-8">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h1 className="text-20 font-semibold text-primary">
              {scope === "me" ? `${greeting(store.now.time)}, ${store.person(store.meId)?.display_name}` : "Equipe"}
            </h1>
            <p className="text-13 text-secondary">
              {longDate(store.today)} ·{" "}
              {!store.complete
                ? "aguardando a leitura completa dos dados"
                : (scope === "me" ? count : hoje.attention.length) === 0
                  ? "nada pede atenção agora"
                  : `${scope === "me" ? count : hoje.attention.length} ${(scope === "me" ? count : hoje.attention.length) === 1 ? "item precisa" : "itens precisam"} de ${scope === "me" ? "você" : "atenção"}`}
            </p>
          </div>
          {scope === "me" && <RitualControl />}
        </header>

        <PartialNotice what="Aguardando e Informar não foram carregados." />

        <ScenarioGate>
          {scope === "me" && views ? (
            <>
              <SinceLastReview />
              <WeekResults />
              <section className="flex flex-col gap-2" aria-label="O que depende de você">
                <Tabs variant="underline" value={view} onValueChange={(value) => setView(value as TView)}>
                  <TabsList>
                    <Tab value="atencao" label={`Atenção · ${count}`} />
                    {tabs.map((entry) => (
                      <Tab
                        key={entry.key}
                        value={entry.key}
                        label={`${entry.label} · ${unloaded(entry.key) ? "?" : views[entry.key].length}`}
                      />
                    ))}
                  </TabsList>
                </Tabs>
                <p className="px-1 text-12 text-tertiary">{hint}</p>
                {!store.hasFocusToday && tomorrow && view === "atencao" && (
                  <p className="px-1 text-13 text-secondary">
                    {store.tomorrowFirst.on === store.today ? "Amanhã começa por" : "Você combinou começar por"}:{" "}
                    <b className="font-medium text-primary">{tomorrow.title}</b>
                  </p>
                )}
                {view === "atencao" &&
                  (count || focusDone.length ? (
                    <div className="flex flex-col gap-3">
                      {(focusOpen.length > 0 || focusDone.length > 0) && (
                        <div className="flex flex-col gap-1.5" aria-label="Foco de hoje">
                          <p className="flex items-center gap-2 px-1 text-12 font-medium text-secondary">
                            Foco de hoje
                            <span className="text-tertiary">
                              {focusDone.length} de {focusOpen.length + focusDone.length} cumprido
                              {focusDone.length === 1 ? "" : "s"}
                            </span>
                          </p>
                          {focusOpen.length > 0 && (
                            <List>
                              {focusOpen.map((item) => {
                                const entry = attentionFor(item, store.items, store.personName);
                                return (
                                  <ItemRow
                                    key={item.id}
                                    item={item}
                                    severity={entry?.severity}
                                    reason={entry?.reason}
                                    pinned
                                  />
                                );
                              })}
                            </List>
                          )}
                          {focusDone.map((item) => (
                            <p key={item.id} className="flex items-center gap-2 px-1 text-13 text-success-primary">
                              <Icon icon={CheckSquareOutline} />
                              <span className="truncate">{item.title}</span>
                              <span className="text-12 text-tertiary">cumprido</span>
                            </p>
                          ))}
                        </div>
                      )}
                      {alerts.length > 0 && (
                        <div className="flex flex-col gap-1.5" aria-label="Alertas">
                          {(focusOpen.length > 0 || focusDone.length > 0) && (
                            <p className="px-1 text-12 font-medium text-secondary">Alertas</p>
                          )}
                          <List>
                            {alerts.map((entry) => (
                              <ItemRow
                                key={entry.item.id}
                                item={entry.item}
                                severity={entry.severity}
                                reason={entry.reason}
                              />
                            ))}
                          </List>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-subtle py-8">
                      <EmptyStateCompact
                        title="Nada pede sua atenção agora"
                        description={
                          partial
                            ? "Parte dos dados não carregou: isso não confirma que não há pendências."
                            : `Decisões, atrasos e riscos aparecem aqui. ${checked}`
                        }
                      />
                    </div>
                  ))}
                {view === "fazer" && <FazerList items={views.fazer} checked={checked} />}
                {view !== "atencao" &&
                  view !== "fazer" &&
                  (unloaded(view) ? (
                    <p className="rounded-lg border border-warning-subtle bg-warning-subtle px-4 py-6 text-center text-13 text-primary">
                      Esta lista não carregou. Não dá para dizer se há algo aqui.
                    </p>
                  ) : views[view].length ? (
                    <WithAttention
                      items={views[view]}
                      signal={view === "aguardando" ? "followUp" : view === "informar" ? "inform" : "auto"}
                    />
                  ) : (
                    <p className="rounded-lg border border-subtle px-4 py-6 text-center text-13 text-tertiary">
                      Nada pendente aqui. {checked}
                    </p>
                  ))}
                {suggestions > 0 && (
                  <Link
                    href={`${base}/inbox/`}
                    className="flex items-center gap-2 rounded-lg border border-accent-subtle bg-accent-subtle px-4 py-2.5 text-13 text-accent-primary hover:bg-accent-subtle-hover"
                  >
                    <Icon icon={AiStar1Outline} />
                    <span className="flex-1">
                      O RADAR deixou {suggestions} {suggestions === 1 ? "proposta" : "propostas"} para você revisar na
                      Inbox
                    </span>
                    <span className="font-medium">Revisar</span>
                  </Link>
                )}
              </section>
            </>
          ) : (
            <>
              <section className="flex flex-col gap-2" aria-label="Precisa de atenção na equipe">
                <SectionTitle
                  title="Precisa de atenção na equipe"
                  count={hoje.attention.length}
                  trailing={
                    <div className="flex items-center gap-1">
                      {owners.map((id) => (
                        <PersonAvatar key={id} personId={id} size="xs" />
                      ))}
                    </div>
                  }
                />
                <List>
                  {hoje.attention.map((entry) => (
                    <ItemRow key={entry.item.id} item={entry.item} severity={entry.severity} reason={entry.reason} />
                  ))}
                </List>
              </section>
              <section className="flex flex-col gap-2" aria-label="Concluído recentemente">
                <SectionTitle title="Concluído recentemente" />
                <WithAttention items={store.items.filter((item) => !isOpen(item.status)).slice(-4)} quiet />
              </section>
            </>
          )}
        </ScenarioGate>
      </div>
    </>
  );
});

/** "Preciso fazer", by when it is due. */
function FazerList({ items, checked }: { items: TMockItem[]; checked: string }) {
  const { today, week, later } = byWhen(items);
  if (!items.length)
    return (
      <p className="rounded-lg border border-subtle px-4 py-6 text-center text-13 text-tertiary">
        Nada para você executar. {checked}
      </p>
    );
  return (
    <div className="flex flex-col gap-3">
      {today.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="px-1 text-12 font-medium text-secondary">Hoje ou atrasado</p>
          <WithAttention items={today} quiet />
        </div>
      )}
      {week.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="px-1 text-12 font-medium text-secondary">Esta semana</p>
          <WithAttention items={week} quiet />
        </div>
      )}
      {later.length > 0 && (
        <Collapsible trigger={<span className="text-12 font-medium text-secondary">Depois · {later.length}</span>}>
          <WithAttention items={later} quiet />
        </Collapsible>
      )}
    </div>
  );
}
