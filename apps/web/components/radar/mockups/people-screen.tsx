/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Badge } from "@makeplane/propel/components/badge";
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { Icon } from "@makeplane/propel/components/icon";
import { Tab, Tabs, TabsList } from "@makeplane/propel/components/tabs";
import { MembersOutline } from "@makeplane/propel/icons";
import { EmptyStateCompact } from "@plane/blocks/empty-state";
import type { TMockPerson } from "./mock-data";
import { attentionFor, diffDays, executorsOf, isOpen } from "./interaction-model";
import { ItemRow } from "./item-row";
import { useRadarMockup } from "./provider";
import { MockupHeader, PartialNotice, PersonAvatar, ScenarioGate } from "./ui";

type TFilter = "todas" | TMockPerson["affiliation"];

const PersonBlock = observer(function PersonBlock({ person }: { person: TMockPerson }) {
  const store = useRadarMockup();
  const open = store.items.filter((item) => isOpen(item.status) && item.kind !== "issue");
  const withThem = open.filter((item) => executorsOf(item).includes(person.id));
  const late = withThem.filter((item) => item.due && diffDays(item.due) < 0);
  // Decisions of mine they take part in (execute, are consulted or must be informed): they wait on me.
  const waitingOnMe = open.filter(
    (item) =>
      item.kind === "decision" &&
      item.ownerId === store.meId &&
      [...item.withIds, ...(item.consultIds ?? []), ...(item.informIds ?? [])].includes(person.id)
  );
  return (
    <div className="border-b border-subtle px-4 py-1 last:border-b-0">
      <Collapsible
        trigger={
          <span className="flex min-w-0 items-center gap-3 py-2">
            <PersonAvatar personId={person.id} size="md" />
            <span className="min-w-0">
              <span className="flex items-center gap-2 truncate text-13 font-medium text-primary">
                {person.name}
                {person.affiliation === "externa" && <Badge variant="orange" size="xs" label="Externa" />}
              </span>
              <span className="block truncate text-12 text-tertiary">
                {[person.role, person.organization].filter(Boolean).join(" · ")}
              </span>
            </span>
          </span>
        }
        trailing={
          <span className="flex flex-wrap items-center justify-end gap-1.5">
            <Badge
              variant="neutral"
              size="sm"
              label={`${withThem.length} ${withThem.length === 1 ? "item registrado" : "itens registrados"}`}
            />
            {late.length > 0 && (
              <Badge variant="danger" size="sm" label={`${late.length} atrasada${late.length > 1 ? "s" : ""}`} />
            )}
            {waitingOnMe.length > 0 && (
              <Badge variant="warning" size="sm" label={`aguarda você em ${waitingOnMe.length}`} />
            )}
          </span>
        }
      >
        <div className="mb-3 overflow-hidden rounded-lg border border-subtle">
          {withThem.length === 0 && waitingOnMe.length === 0 && (
            <p className="px-4 py-3 text-13 text-tertiary">Nada em aberto com {person.display_name}.</p>
          )}
          {[...waitingOnMe, ...withThem.filter((item) => !waitingOnMe.includes(item))].map((item) => {
            const attention = attentionFor(item, store.items, store.personName);
            return (
              <ItemRow
                key={item.id}
                item={item}
                severity={attention?.severity}
                reason={waitingOnMe.includes(item) ? "Aguarda sua decisão" : attention?.reason}
              />
            );
          })}
        </div>
      </Collapsible>
    </div>
  );
});

/**
 * Everyone the work depends on, inside the team or not (§13: same data, another perspective). External
 * people carry deadlines too: a supplier's schedule or counsel's opinion can block a decision.
 */
export const RadarMockupPeople = observer(function RadarMockupPeople() {
  const store = useRadarMockup();
  const [filter, setFilter] = useState<TFilter>("todas");
  const others = store.people.filter((person) => person.id !== store.meId);
  const count = (affiliation: TMockPerson["affiliation"]) =>
    others.filter((person) => person.affiliation === affiliation).length;
  const shown = filter === "todas" ? others : others.filter((person) => person.affiliation === filter);
  return (
    <>
      <MockupHeader
        crumbs={[{ label: "Pessoas", icon: <Icon icon={MembersOutline} /> }]}
        actions={
          <Tabs variant="contained" value={filter} onValueChange={(value) => setFilter(value as TFilter)}>
            <TabsList>
              <Tab value="todas" label={`Todas · ${others.length}`} />
              <Tab value="equipe" label={`Equipe · ${count("equipe")}`} />
              <Tab value="externa" label={`Externas · ${count("externa")}`} />
            </TabsList>
          </Tabs>
        }
      />
      <div className="mx-auto flex w-full max-w-[960px] flex-col gap-6 px-4 py-6 md:px-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-20 font-semibold text-primary">Pessoas</h1>
          <p className="text-13 text-secondary">
            {filter === "externa"
              ? "Fornecedores, consultores e parceiros: o que está com eles e o que pode travar seu trabalho."
              : filter === "equipe"
                ? "Sua equipe: o que está com cada pessoa e quem aguarda uma decisão sua."
                : "Quem está com algo seu, dentro ou fora da equipe, e quem aguarda uma decisão sua."}{" "}
            As contagens mostram o que está registrado com cada pessoa; não dizem quanto ela consegue assumir.
          </p>
        </header>
        <PartialNotice what="Parte dos itens não carregou, então as contagens podem estar menores que o real." />
        <ScenarioGate>
          {shown.length ? (
            <div className="overflow-hidden rounded-lg border border-subtle">
              {shown.map((person) => (
                <PersonBlock key={person.id} person={person} />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-subtle py-10">
              <EmptyStateCompact title="Ninguém aqui" description="Nenhuma pessoa neste filtro." />
            </div>
          )}
        </ScenarioGate>
      </div>
    </>
  );
});
