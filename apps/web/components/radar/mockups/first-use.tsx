/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Input } from "@makeplane/propel/components/input";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { CheckSquareOutline, CloseOutline, HomeOutline } from "@makeplane/propel/icons";
import { DateSelect, MemberSelect } from "@plane/blocks/property-select";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { cn } from "@plane/utils";
import type { TMockKind, TMockProject } from "./mock-data";
import { KIND_LABEL, fromLocalDate, toLocalDate } from "./interaction-model";
import type { TOnboardingRow } from "./mockup.store";
import { useRadarMockup } from "./provider";
import { MockupHeader, useMemberOptions } from "./ui";

function Step({
  index,
  minutes,
  title,
  done,
  children,
}: {
  index: number;
  minutes: number;
  title: string;
  done: boolean;
  children: ReactNode;
}) {
  return (
    <section className={cn("flex gap-4 rounded-lg border p-4", done ? "border-success-subtle" : "border-subtle")}>
      <span
        className={cn(
          "grid size-7 shrink-0 place-items-center rounded-full text-12 font-semibold",
          done ? "bg-success-primary text-white" : "bg-layer-2 text-secondary"
        )}
      >
        {done ? <Icon icon={CheckSquareOutline} /> : index}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-14 font-semibold text-primary">{title}</h2>
          <span className="text-12 text-tertiary">{minutes} min</span>
        </div>
        {children}
      </div>
    </section>
  );
}

const TIME_OPTIONS = {
  abrir: ["08:00", "08:30", "09:00"],
  fechar: ["17:00", "17:30", "18:00"],
  semanal: ["sex 16:00", "seg 08:30"],
} as const;

const RITUAL_NAMES = { abrir: "Abrir o dia", fechar: "Fechar o dia", semanal: "Revisão semanal" } as const;

const KIND_OPTIONS: { id: TMockKind | "inbox"; label: string }[] = [
  { id: "action", label: KIND_LABEL.action },
  { id: "decision", label: KIND_LABEL.decision },
  { id: "risk", label: KIND_LABEL.risk },
  { id: "inbox", label: "Só guardar na Inbox" },
];

/** Without a vault, the context starts from what the manager names: nothing is invented for them. */
const BlankContext = observer(function BlankContext() {
  const store = useRadarMockup();
  const [project, setProject] = useState("");
  const [person, setPerson] = useState("");
  const [external, setExternal] = useState(false);
  const [organization, setOrganization] = useState("");
  const others = store.people.filter((candidate) => candidate.id !== store.meId);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-13 text-secondary">
        Sem vault, você começa do zero: dê nome aos projetos e às pessoas de que o seu trabalho depende. Dá para
        acrescentar mais depois.
      </p>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          store.addProject(project);
          setProject("");
        }}
      >
        <Input
          size="md"
          value={project}
          placeholder="Nome de um projeto"
          aria-label="Nome do projeto"
          onChange={(event) => setProject(event.target.value)}
        />
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          type="submit"
          label="Adicionar projeto"
          disabled={!project.trim()}
        />
      </form>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          store.addPerson(person, external ? "externa" : "equipe", organization);
          setPerson("");
          setOrganization("");
          setExternal(false);
        }}
      >
        <div className="min-w-[180px] flex-1">
          <Input
            size="md"
            value={person}
            placeholder="Nome de uma pessoa"
            aria-label="Nome da pessoa"
            onChange={(event) => setPerson(event.target.value)}
          />
        </div>
        {/* oxlint-disable-next-line jsx-a11y/label-has-associated-control -- the checkbox is inside the label */}
        <label className="flex items-center gap-1.5 text-13 text-secondary">
          <Checkbox checked={external} aria-label="Pessoa externa" onCheckedChange={(value) => setExternal(!!value)} />
          Externa
        </label>
        {external && (
          <div className="min-w-[160px]">
            <Input
              size="md"
              value={organization}
              placeholder="Organização"
              aria-label="Organização"
              onChange={(event) => setOrganization(event.target.value)}
            />
          </div>
        )}
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          type="submit"
          label="Adicionar pessoa"
          disabled={!person.trim()}
        />
      </form>
      <div className="flex flex-wrap gap-1.5">
        {store.projects.map((entry) => (
          <Badge key={entry.id} variant="neutral" size="sm" label={entry.title} />
        ))}
        {others.map((entry) => (
          <Badge
            key={entry.id}
            variant={entry.affiliation === "externa" ? "orange" : "neutral"}
            size="sm"
            label={entry.affiliation === "externa" ? `${entry.display_name} · externa` : entry.display_name}
          />
        ))}
        {!store.projects.length && !others.length && (
          <span className="text-12 text-tertiary">Nada adicionado ainda.</span>
        )}
      </div>
    </div>
  );
});

/** One pending line: what the RADAR understood, correctable before anything is created, and how it went. */
const PendingRow = observer(function PendingRow({ row }: { row: TOnboardingRow }) {
  const store = useRadarMockup();
  const members = useMemberOptions();
  const created = row.result?.status === "created";
  const failed = row.result?.status === "failed";
  const kind = row.guess.kind ?? "inbox";
  const projectOption = store.project(row.guess.projectId) ?? null;
  return (
    <li className="flex flex-col gap-1.5 rounded-md border border-subtle px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 text-13 font-medium text-primary">{row.guess.title}</span>
        {created && <Badge variant="success" size="sm" label={row.result?.where === "inbox" ? "Na Inbox" : "Criado"} />}
        {failed && <Badge variant="danger" size="sm" label="Não foi criado" />}
      </div>
      {failed && <p className="text-12 text-danger-primary">{row.result?.error}</p>}
      {/* A line already created is not edited here: it would no longer be the same thing. */}
      <div
        className={cn(
          "grid grid-cols-1 items-center gap-1 sm:grid-cols-2 lg:grid-cols-4",
          created && "pointer-events-none opacity-60"
        )}
        inert={created}
      >
        <Select<(typeof KIND_OPTIONS)[number]>
          getValues={() => KIND_OPTIONS}
          value={KIND_OPTIONS.find((option) => option.id === kind) ?? null}
          onChange={(id) => store.correctRow(row.key, { kind: id === "inbox" ? null : (id as TMockKind) })}
          getOptionValue={(option) => option.id}
          getOptionLabel={(option) => option.label}
          showSearch={false}
          pinSelected={false}
        >
          <Select.Trigger variant="select-ghost-md">
            <span className="truncate text-13">{KIND_OPTIONS.find((option) => option.id === kind)?.label}</span>
          </Select.Trigger>
        </Select>
        <div className="flex min-w-0 items-center">
          <MemberSelect
            variant="select-ghost-md"
            getValues={members.getValues}
            value={members.find(row.guess.personIds[0])}
            placeholder="Sem pessoa"
            filterOption={(member) => member.id !== store.meId}
            onChange={(id) => store.correctRow(row.key, { personIds: id ? [id] : [] })}
          />
          {row.guess.personIds.length > 0 && (
            <IconButton
              variant="ghost"
              size="sm"
              aria-label="Tirar a pessoa"
              icon={<Icon icon={CloseOutline} />}
              onClick={() => store.correctRow(row.key, { personIds: [] })}
            />
          )}
        </div>
        <Select<TMockProject>
          getValues={() => store.projects}
          value={projectOption}
          onChange={(id) => store.correctRow(row.key, { projectId: id })}
          getOptionValue={(option) => option.id}
          getOptionLabel={(option) => option.title}
          showSearch={false}
          pinSelected={false}
        >
          <Select.Trigger variant="select-ghost-md">
            <span className="truncate text-13">{projectOption?.title ?? "Sem projeto"}</span>
          </Select.Trigger>
        </Select>
        <DateSelect
          variant="select-ghost-md"
          value={toLocalDate(row.guess.due)}
          placeholder="Sem data"
          clearable
          formatToken="dd/MM/yyyy"
          onChange={(value) => store.correctRow(row.key, { due: fromLocalDate(value) })}
        />
      </div>
    </li>
  );
});

/**
 * "Comece com a sua semana real" (Guia básico §01): about fifteen minutes, and every step creates real work.
 * Nothing here models the area or configures types (RADAR_UX_VIEW §22). The progress lives in the store, so
 * leaving for another screen and coming back picks up where it stopped.
 */
export const RadarMockupFirstUse = observer(function RadarMockupFirstUse() {
  const store = useRadarMockup();
  const { onboarding } = store;
  const [result, setResult] = useState({ title: "", howWeKnow: "" });
  const rows = store.onboardingRows;
  const created = rows.filter((row) => row.result?.status === "created");
  const failed = rows.filter((row) => row.result?.status === "failed");
  const waiting = rows.filter((row) => !row.result || row.result.status === "failed");
  const others = store.people.filter((person) => person.id !== store.meId);
  const vault = onboarding.path !== "blank";
  const done = [
    onboarding.contextConfirmed,
    store.weekResults.length > 0,
    rows.length > 0 && waiting.length === 0,
    onboarding.prefsSaved,
  ];

  return (
    <>
      <MockupHeader crumbs={[{ label: "Hoje", icon: <Icon icon={HomeOutline} /> }]} />
      <div className="mx-auto flex w-full max-w-[820px] flex-col gap-5 px-4 py-6 md:px-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-20 font-semibold text-primary">Comece com a sua semana real</h1>
          <p className="text-13 text-secondary">
            Uns 15 minutos. Nada aqui é configuração: cada passo já vira trabalho no seu Hoje. Você pode sair e voltar:
            o que já fez fica guardado.
          </p>
          <span className="text-12 text-tertiary">{done.filter(Boolean).length} de 4 passos</span>
        </header>

        <Step index={1} minutes={3} title="Confira o seu contexto" done={onboarding.contextConfirmed}>
          {vault ? (
            <>
              <p className="text-13 text-secondary">
                Do seu vault vieram {store.projects.length} projetos e {others.length} pessoas, entre equipe e externas.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {store.projects.map((project) => (
                  <Badge key={project.id} variant="neutral" size="sm" label={project.title} />
                ))}
              </div>
            </>
          ) : (
            <BlankContext />
          )}
          {/* Keep the row in place once confirmed, so the steps below do not jump. */}
          <div className="flex min-h-7 items-center gap-2">
            {onboarding.contextConfirmed ? (
              <span className="text-13 text-success-primary">Confirmado</span>
            ) : (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  stretch="auto"
                  label={vault ? "Está certo" : "Continuar"}
                  onClick={store.confirmContext}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  label={vault ? "Corrijo depois" : "Pular por agora"}
                  onClick={store.confirmContext}
                />
              </>
            )}
          </div>
        </Step>

        <Step
          index={2}
          minutes={4}
          title="Escolha até 3 resultados para esta semana"
          done={store.weekResults.length > 0}
        >
          <p className="text-13 text-secondary">
            O que precisa estar diferente até sexta? Se ainda não sabe como reconhecer a entrega, deixe em branco: fica
            marcado como “a confirmar”.
          </p>
          {store.weekResults.map((entry) => (
            <div key={entry.id} className="flex items-center gap-2 rounded-md bg-layer-1 px-3 py-2 text-13">
              <span className="min-w-0 flex-1">
                <span className="font-medium text-primary">{entry.title}</span>
                {entry.howWeKnow ? (
                  <span className="text-tertiary"> · como saberemos: {entry.howWeKnow}</span>
                ) : (
                  <span className="text-warning-primary"> · como saberemos: a confirmar</span>
                )}
              </span>
              <IconButton
                variant="ghost"
                size="sm"
                aria-label={`Remover ${entry.title}`}
                icon={<Icon icon={CloseOutline} />}
                onClick={() => store.removeWeekResult(entry.id)}
              />
            </div>
          ))}
          {store.weekResults.length < 3 && (
            <div className="flex flex-col gap-2">
              <InputField
                id="first-use-result"
                label="Resultado"
                orientation="vertical"
                size="lg"
                value={result.title}
                placeholder="Proposta revisada e enviada ao cliente"
                onChange={(event) => setResult({ ...result, title: event.target.value })}
              />
              <InputField
                id="first-use-how"
                label="Como saberemos?"
                orientation="vertical"
                size="lg"
                value={result.howWeKnow}
                placeholder="Cliente confirmou o recebimento até sexta"
                onChange={(event) => setResult({ ...result, howWeKnow: event.target.value })}
              />
              <div>
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label="Adicionar resultado"
                  disabled={!result.title.trim()}
                  onClick={() => {
                    store.addWeekResult(result.title, result.howWeKnow);
                    setResult({ title: "", howWeKnow: "" });
                  }}
                />
              </div>
            </div>
          )}
        </Step>

        <Step
          index={3}
          minutes={5}
          title="Traga as pendências importantes"
          done={rows.length > 0 && waiting.length === 0}
        >
          <TextAreaField
            id="first-use-pending"
            label="Uma por linha: o que você precisa fazer, decidir ou receber de alguém"
            size="lg"
            rows={4}
            value={onboarding.draft}
            placeholder={
              "Cobrar Carlos sobre o comparativo até sexta\nDecidir amanhã se seguimos com a XPTO\nVer com jurídico a cláusula de reajuste"
            }
            onChange={(event) => store.setDraft(event.target.value)}
          />
          {rows.length > 0 && (
            <>
              <p className="text-12 text-tertiary">
                Confira o que o RADAR entendeu e corrija o tipo, a pessoa, o projeto ou a data antes de organizar.
              </p>
              <ul className="flex flex-col gap-2" aria-label="Pendências entendidas">
                {rows.map((row) => (
                  <PendingRow key={row.key} row={row} />
                ))}
              </ul>
            </>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label={failed.length ? `Tentar de novo (${failed.length})` : "Organizar"}
              disabled={!waiting.length || store.readOnly}
              onClick={() => {
                const outcome = store.organizeDraft();
                const ok = outcome.filter((entry) => entry.status === "created").length;
                const bad = outcome.filter((entry) => entry.status === "failed").length;
                setToast({
                  type: bad ? "warning" : "success",
                  title: bad ? `${ok} criado${ok === 1 ? "" : "s"}, ${bad} não` : "Pendências organizadas",
                  message: bad
                    ? "As que não foram criadas continuam aqui. Tente de novo: as criadas não se repetem."
                    : "Os itens com outra pessoa já pedem o retorno combinado.",
                });
              }}
            />
            {created.length > 0 && (
              <span className="text-12 text-secondary">
                {created.length} de {rows.length} criado{created.length === 1 ? "" : "s"}
                {failed.length ? ` · ${failed.length} com falha` : ""}
              </span>
            )}
          </div>
          {/* oxlint-disable-next-line jsx-a11y/label-has-associated-control -- the checkbox is inside the label */}
          <label className="flex items-center gap-2 text-12 text-tertiary">
            <Checkbox
              checked={store.demo.failBatchLine}
              aria-label="Simular falha em uma linha"
              onCheckedChange={() => store.toggleDemo("failBatchLine")}
            />
            Demonstração: fazer a segunda linha falhar na próxima tentativa, para ver o resultado parcial
          </label>
        </Step>

        <Step index={4} minutes={3} title="Escolha quando revisar" done={onboarding.prefsSaved}>
          {(Object.keys(TIME_OPTIONS) as (keyof typeof TIME_OPTIONS)[]).map((ritual) => (
            <div key={ritual} className="flex flex-wrap items-center gap-2">
              <span className="w-36 text-13 text-secondary">{RITUAL_NAMES[ritual]}</span>
              {TIME_OPTIONS[ritual].map((time) => (
                <Button
                  key={time}
                  variant={store.ritualTimes[ritual] === time ? "primary" : "secondary"}
                  size="sm"
                  stretch="auto"
                  label={time}
                  onClick={() => store.setRitualTime(ritual, time)}
                />
              ))}
            </div>
          ))}
          <p className="text-12 text-tertiary">
            O RADAR usa estes horários para sugerir o ritual na hora certa. Nenhum compromisso é criado na sua agenda: é
            só uma preferência.
          </p>
          <div className="flex min-h-7 items-center">
            {onboarding.prefsSaved ? (
              <span className="text-13 text-success-primary">Preferências guardadas</span>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label="Guardar preferências"
                onClick={store.savePreferences}
              />
            )}
          </div>
        </Step>

        <div className="flex items-center justify-between gap-3 border-t border-subtle pt-4">
          <span className="text-12 text-tertiary">Dá para pular passos e voltar depois.</span>
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label="Ir para Hoje"
            disabled={!store.weekResults.length && !created.length}
            onClick={() => {
              store.finishFirstUse();
              setToast({
                type: "success",
                title: "Seu Hoje está pronto",
                message: onboarding.prefsSaved
                  ? `O RADAR vai sugerir abrir o dia às ${store.ritualTimes.abrir}.`
                  : "Você pode escolher os horários dos rituais depois.",
              });
            }}
          />
        </div>
      </div>
    </>
  );
});
