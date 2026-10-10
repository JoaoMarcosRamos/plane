/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useRouter } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { AiStar1Outline, HomeOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { cn } from "@plane/utils";
import type { TMockItem, TMockWeekResult } from "./mock-data";
import { addDays, attentionFor, dayMonth, diffDays, executorsOf, isOpen, silentDays } from "./interaction-model";
import { ItemRow } from "./item-row";
import { useRadarMockup } from "./provider";
import { MockupHeader, PersonAvatar, SectionTitle, useMockupBase } from "./ui";

/** "Como saberemos" is never filled with a guess: empty reads as a gap. */
const HowWeKnow = ({ value }: { value: string }) =>
  value ? <>{value}</> : <span className="text-warning-primary">a confirmar</span>;

const STEPS = [
  "Resultados × evidências",
  "Delegações, decisões e riscos",
  "Carga registrada",
  "Próxima semana",
  "O método está ajudando?",
];

const QUESTIONS = [
  "Tenho mais clareza? Consigo dizer os resultados prioritários e o próximo passo de cada assunto importante?",
  "Há mais continuidade? Sei o que estou aguardando, de quem e quando devo intervir? Os vencidos foram tratados?",
  "Houve resultado e aprendizado? O que foi entregue atende ao combinado? Que ajuste melhora a próxima semana?",
];

const STATE_BUTTONS: { state: TMockWeekResult["state"]; label: string }[] = [
  { state: "met", label: "Atingido" },
  { state: "partial", label: "Parcial" },
  { state: "missed", label: "Não atingido" },
];

const Rows = observer(function Rows({ items, empty }: { items: TMockItem[]; empty: string }) {
  const store = useRadarMockup();
  if (!items.length) return <p className="px-1 text-13 text-tertiary">{empty}</p>;
  return (
    <div className="overflow-hidden rounded-lg border border-subtle">
      {items.map((item) => {
        const attention = attentionFor(item, store.items, store.personName);
        return <ItemRow key={item.id} item={item} severity={attention?.severity} reason={attention?.reason} quiet />;
      })}
    </div>
  );
});

/** Revisão semanal (Guia básico §05): 30–45 minutes, ends with priorities and the pilot diary. */
export const RadarMockupReview = observer(function RadarMockupReview() {
  const store = useRadarMockup();
  const base = useMockupBase();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [keep, setKeep] = useState<string[]>(
    store.weekResults.filter((result) => result.state !== "met").map((result) => result.id)
  );
  const [picked, setPicked] = useState<string[]>([]);
  const [draft, setDraft] = useState({ title: "", howWeKnow: "" });
  const [extra, setExtra] = useState<{ title: string; howWeKnow: string }[]>([]);
  const [answers, setAnswers] = useState(["", "", ""]);

  const views = store.hojeMine.views;
  const weekStart = addDays(store.today, -6);
  // Closed this week means a conclusion recorded this week, not any activity on an item that is closed.
  const doneThisWeek = store.items.filter(
    (item) =>
      !isOpen(item.status) &&
      item.activity.some(
        (entry) => entry.at.slice(0, 10) >= weekStart && /^(concluiu|aprovou|encerrou)/.test(entry.text)
      )
  );
  const late = store.items.filter(
    (item) =>
      item.kind === "action" && isOpen(item.status) && item.ownerId === store.meId && item.due && diffDays(item.due) < 0
  );
  const silent = store.items.filter((item) => silentDays(item, store.meId));
  const myRisks = store.items.filter(
    (item) => item.kind === "risk" && isOpen(item.status) && item.ownerId === store.meId
  );
  const suggestions = (views?.decidir ?? []).map((item) => ({
    id: item.id,
    title: `Decidir: ${item.title}`,
    howWeKnow: "Decisão registrada e comunicada a quem precisa saber",
    projectId: item.projectId,
  }));
  const kept = store.weekResults.filter((result) => keep.includes(result.id));
  const chosen = [
    ...kept.map((result) => ({ title: result.title, howWeKnow: result.howWeKnow, projectId: result.projectId })),
    ...suggestions.filter((suggestion) => picked.includes(suggestion.id)),
    ...extra.map((result) => ({ ...result, projectId: null })),
  ];
  const full = chosen.length >= 3;
  const team = store.people.filter((person) => person.affiliation === "equipe");
  const load = (personId: string) =>
    store.items.filter(
      (item) =>
        isOpen(item.status) &&
        item.kind !== "issue" &&
        executorsOf(item).includes(personId) &&
        item.due &&
        diffDays(item.due) <= 7
    ).length;

  const finish = () => {
    store.saveWeeklyReview({
      states: Object.fromEntries(store.weekResults.map((result) => [result.id, result.state])),
      next: chosen,
      answers,
    });
    setToast({
      type: "success",
      title: "Revisão semanal registrada",
      message: "Respostas guardadas no diário do piloto.",
    });
    router.push(`${base}/hoje/`);
  };

  return (
    <>
      <MockupHeader
        crumbs={[
          { label: "Hoje", href: `${base}/hoje/`, icon: <Icon icon={HomeOutline} /> },
          { label: "Revisão semanal" },
        ]}
      />
      <div className="mx-auto flex w-full max-w-[960px] flex-col gap-6 px-4 py-6 md:px-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-20 font-semibold text-primary">Revisão semanal</h1>
          <p className="text-13 text-secondary">
            30 a 45 minutos. Compare o que combinamos com o que aconteceu e escolha a próxima semana.
          </p>
        </header>

        <ol className="flex flex-wrap gap-2" aria-label="Passos">
          {STEPS.map((label, index) => (
            <li key={label}>
              <button
                type="button"
                onClick={() => setStep(index)}
                className={cn(
                  "rounded-full border px-3 py-1 text-12 font-medium",
                  index === step
                    ? "border-accent-strong bg-accent-subtle text-accent-primary"
                    : "border-subtle text-secondary hover:bg-layer-transparent-hover",
                  index < step && "text-tertiary"
                )}
              >
                {index + 1} · {label}
              </button>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <section className="flex flex-col gap-3">
            <SectionTitle title="Os resultados desta semana aconteceram?" />
            {store.weekResults.map((result) => {
              const evidence = doneThisWeek.filter((item) => item.projectId === result.projectId);
              return (
                <div key={result.id} className="flex flex-col gap-2 rounded-lg border border-subtle p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-14 font-medium text-primary">{result.title}</p>
                      <p className="text-12 text-secondary">
                        Como saberemos: <HowWeKnow value={result.howWeKnow} />
                      </p>
                    </div>
                    <div className="flex gap-1.5">
                      {STATE_BUTTONS.map((button) => (
                        <Button
                          key={button.state}
                          variant={result.state === button.state ? "primary" : "secondary"}
                          size="sm"
                          stretch="auto"
                          label={button.label}
                          onClick={() => store.setWeekResultState(result.id, button.state)}
                        />
                      ))}
                    </div>
                  </div>
                  <p className="text-12 text-tertiary">
                    Entregas da semana no mesmo projeto:{" "}
                    {evidence.length
                      ? evidence
                          .map((item) => `${item.title} (${item.evidence[0]?.label ?? "sem evidência anexada"})`)
                          .join("; ")
                      : "nenhuma; confira a evidência combinada com quem executa"}
                  </p>
                </div>
              );
            })}
          </section>
        )}

        {step === 1 && (
          <section className="flex flex-col gap-4">
            <div className="flex flex-col gap-2 rounded-lg border border-accent-subtle bg-accent-subtle p-4">
              <span className="flex items-center gap-1.5 text-11 font-semibold tracking-wide text-accent-primary uppercase">
                <Icon icon={AiStar1Outline} /> Resumo preparado pelo RADAR
              </span>
              <ul className="flex flex-col gap-1 text-13 text-primary">
                <li>
                  {doneThisWeek.length}{" "}
                  {doneThisWeek.length === 1 ? "entrega ou decisão fechada" : "entregas e decisões fechadas"} desde{" "}
                  {dayMonth(weekStart)}
                  <span className="text-tertiary"> · fonte: histórico dos itens</span>
                </li>
                <li>
                  {late.length} combinados atrasados: {late.map((item) => item.title).join("; ")}
                  <span className="text-tertiary"> · fonte: prazos combinados</span>
                </li>
                <li>
                  {silent.length} sem notícias de quem executa há 3 dias ou mais
                  <span className="text-tertiary"> · fonte: atividade registrada</span>
                </li>
                <li>
                  {views?.decidir.length ?? 0} decisões pendentes e {views?.informar.length ?? 0} comunicação pendente
                </li>
              </ul>
              <p className="text-11 text-tertiary">
                O agente só usa o que está registrado. Confirme o que parecer desatualizado.
              </p>
            </div>
            <SectionTitle title="Delegações e o que você aguarda" count={views?.aguardando.length} />
            <Rows items={views?.aguardando ?? []} empty="Nada aguardando outras pessoas." />
            <SectionTitle title="Decisões" count={views?.decidir.length} />
            <Rows items={views?.decidir ?? []} empty="Nenhuma decisão pendente." />
            <SectionTitle title="Riscos" count={myRisks.length} />
            <Rows items={myRisks} empty="Nenhum risco aberto sob sua responsabilidade." />
          </section>
        )}

        {step === 2 && (
          <section className="flex flex-col gap-3">
            <SectionTitle title="Carga registrada nos próximos 7 dias" />
            <p className="px-1 text-12 text-tertiary">
              Itens em aberto que cada pessoa executa e vencem até {dayMonth(addDays(store.today, 7))}. É o que está
              registrado: o RADAR não sabe o esforço de cada item nem a disponibilidade de cada pessoa, então isto não
              mede capacidade.
            </p>
            <div className="overflow-hidden rounded-lg border border-subtle">
              {team.map((person) => {
                const count = load(person.id);
                return (
                  <div
                    key={person.id}
                    className="flex items-center gap-3 border-b border-subtle px-4 py-2.5 last:border-b-0"
                  >
                    <PersonAvatar personId={person.id} size="sm" />
                    <span className="w-44 truncate text-13 text-primary">
                      {person.id === store.meId ? "Você" : person.name}
                    </span>
                    <span className="flex-1 text-right text-13 text-secondary tabular-nums">
                      {count} {count === 1 ? "item registrado" : "itens registrados"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="flex flex-col gap-3">
            <SectionTitle
              title="Até 3 resultados para a próxima semana"
              trailing={
                <span className={cn("text-12", full ? "text-warning-primary" : "text-tertiary")}>
                  {chosen.length} de 3
                </span>
              }
            />
            <div className="overflow-hidden rounded-lg border border-subtle">
              {store.weekResults.map((result) => (
                <label
                  key={result.id}
                  className="flex cursor-pointer items-center gap-3 border-b border-subtle px-4 py-2.5 last:border-b-0"
                >
                  <Checkbox
                    checked={keep.includes(result.id)}
                    disabled={!keep.includes(result.id) && full}
                    aria-label={`Manter ${result.title}`}
                    onCheckedChange={(value) =>
                      setKeep((list) => (value ? [...list, result.id] : list.filter((id) => id !== result.id)))
                    }
                  />
                  <span className="min-w-0 flex-1 text-13 text-primary">{result.title}</span>
                  <span className="text-12 text-tertiary">continua desta semana</span>
                </label>
              ))}
              {suggestions.map((suggestion) => (
                <label
                  key={suggestion.id}
                  className="flex cursor-pointer items-center gap-3 border-b border-subtle px-4 py-2.5 last:border-b-0"
                >
                  <Checkbox
                    checked={picked.includes(suggestion.id)}
                    disabled={!picked.includes(suggestion.id) && full}
                    aria-label={`Escolher ${suggestion.title}`}
                    onCheckedChange={(value) =>
                      setPicked((list) =>
                        value ? [...list, suggestion.id] : list.filter((id) => id !== suggestion.id)
                      )
                    }
                  />
                  <span className="min-w-0 flex-1 text-13 text-primary">{suggestion.title}</span>
                  <span className="text-12 text-tertiary">sugerido pelo RADAR</span>
                </label>
              ))}
              {extra.map((result) => (
                <div
                  key={result.title}
                  className="flex items-center gap-3 border-b border-subtle px-4 py-2.5 last:border-b-0"
                >
                  <span className="min-w-0 flex-1 text-13 text-primary">{result.title}</span>
                  <span className="text-12 text-tertiary">novo</span>
                </div>
              ))}
            </div>
            {!full && (
              <div className="flex flex-col gap-2 rounded-lg border border-dashed border-subtle p-3">
                <InputField
                  id="review-new-result"
                  label="Novo resultado"
                  orientation="vertical"
                  size="lg"
                  value={draft.title}
                  placeholder="O que precisa estar diferente?"
                  onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                />
                <InputField
                  id="review-how-we-know"
                  label="Como saberemos que deu certo?"
                  orientation="vertical"
                  size="lg"
                  value={draft.howWeKnow}
                  placeholder="Um número ou um critério observável"
                  onChange={(event) => setDraft({ ...draft, howWeKnow: event.target.value })}
                />
                <div>
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label="Adicionar"
                    disabled={!draft.title.trim()}
                    onClick={() => {
                      setExtra((list) => [...list, { title: draft.title.trim(), howWeKnow: draft.howWeKnow.trim() }]);
                      setDraft({ title: "", howWeKnow: "" });
                    }}
                  />
                </div>
              </div>
            )}
            {full && (
              <p className="px-1 text-12 text-warning-primary">
                A semana está cheia. Para incluir outro resultado, escolha qual sai: a nova prioridade precisa de espaço
                real na agenda.
              </p>
            )}
            <p className="px-1 text-12 text-tertiary">
              Fica para depois:{" "}
              {[
                ...store.weekResults.filter((result) => !keep.includes(result.id)).map((result) => result.title),
                ...suggestions
                  .filter((suggestion) => !picked.includes(suggestion.id))
                  .map((suggestion) => suggestion.title),
              ].join("; ") || "nada"}
            </p>
          </section>
        )}

        {step === 4 && (
          <section className="flex flex-col gap-3">
            <SectionTitle title="O método está ajudando você a gerir?" />
            <p className="px-1 text-12 text-tertiary">
              Responda com exemplos reais. As respostas vão para o diário do piloto.
            </p>
            {QUESTIONS.map((question, index) => (
              <TextAreaField
                key={question}
                id={`review-question-${index}`}
                label={question}
                size="lg"
                rows={2}
                value={answers[index]}
                onChange={(event) =>
                  setAnswers((list) =>
                    list.map((answer, position) => (position === index ? event.target.value : answer))
                  )
                }
              />
            ))}
            <p className="px-1 text-12 text-tertiary">
              Se o método estiver pesado, reduza campos, fontes e rotinas. Preserve resultado, responsável, próximo
              passo e retorno.
            </p>
          </section>
        )}

        <div className="flex justify-between gap-2 border-t border-subtle pt-4">
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label="Anterior"
            disabled={step === 0}
            onClick={() => setStep(step - 1)}
          />
          {step < STEPS.length - 1 ? (
            <Button variant="primary" size="md" stretch="auto" label="Próximo" onClick={() => setStep(step + 1)} />
          ) : (
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label="Concluir revisão"
              disabled={!chosen.length}
              onClick={finish}
            />
          )}
        </div>
      </div>
    </>
  );
});
