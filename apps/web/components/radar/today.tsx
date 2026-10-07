import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { RadarService } from "@/services/radar/radar.service";
import { useRadarStore } from "@/store/radar/provider";
import { RadarTodayStore } from "@/store/radar/today.store";
import { deadlineText } from "./operational-text";

function AttentionSection({
  title,
  empty,
  children,
  count,
}: {
  title: string;
  empty: string;
  children: ReactNode;
  count: number;
}) {
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <h2 className="text-14 font-semibold text-primary">{title}</h2>
      {count ? (
        <ul className="divide-y divide-subtle rounded-md border border-subtle">{children}</ul>
      ) : (
        <p className="text-13 text-tertiary">{empty}</p>
      )}
    </section>
  );
}

function AttentionItem({
  title,
  detail,
  href,
  label,
  badge,
}: {
  title: string;
  detail: string;
  href: string;
  label: string;
  badge: ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 px-3 py-3">
      <div className="min-w-0 flex-1 basis-52">
        <Link href={href} className="text-13 font-medium break-words text-primary hover:underline">
          {title}
        </Link>
        <p className="mt-1 text-12 break-words text-secondary">{detail}</p>
      </div>
      {badge}
      <Link href={href} aria-label={`${label}: ${title}`} className="text-13 text-accent-primary hover:underline">
        {label}
      </Link>
    </li>
  );
}

function displayDate(value: string) {
  // Date-only semantics: never shift a deadline through UTC parsing.
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

/** Four attention queues only. Decisions and commands stay on their existing review pages. */
export const RadarToday = observer(function RadarToday() {
  const { workspaceSlug } = useRadarStore();
  const [store] = useState(
    () => new RadarTodayStore(workspaceSlug, new RadarService(), Intl.DateTimeFormat().resolvedOptions().timeZone)
  );
  useEffect(() => {
    void store.load();
    const refresh = () => {
      if (document.visibilityState === "visible") void store.load();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [store]);
  const queue = store.queue;
  const base = `/${encodeURIComponent(workspaceSlug)}/radar`;
  const objectUrl = (id: string) => `${base}/objects/${encodeURIComponent(id)}/`;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 md:p-6" aria-busy={store.loading}>
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-20 font-semibold text-primary">Today</h1>
          <p className="mt-1 text-13 text-secondary">O que precisa da sua atenção gerencial.</p>
          {queue && (
            <p className="mt-1 text-11 text-tertiary">
              {displayDate(queue.date)} · {queue.timezone}
            </p>
          )}
        </div>
        <Button
          size="sm"
          stretch="auto"
          variant="secondary"
          label="Atualizar"
          disabled={store.loading}
          onClick={() => void store.load()}
        />
      </header>
      {store.loading && (
        <p role="status" className="text-13 text-secondary">
          Carregando atenção de hoje…
        </p>
      )}
      {store.error && (
        <p role="alert" className="text-13 text-danger-primary">
          {store.error}
        </p>
      )}
      {queue && (
        <>
          <AttentionSection
            title="Riscos relevantes"
            empty="Nenhum risco relevante no momento."
            count={queue.risks.length}
          >
            {queue.risks.map((item) => (
              <AttentionItem
                key={item.id}
                title={item.title}
                href={objectUrl(item.id)}
                label="Abrir risco"
                detail={[
                  item.score !== null ? `Score ${item.score}/25` : null,
                  item.review_overdue && item.review_date
                    ? `Revisão vencida em ${displayDate(item.review_date)}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                badge={<Badge variant="warning" size="sm" label={item.review_overdue ? "Revisar" : "Alto risco"} />}
              />
            ))}
          </AttentionSection>
          <AttentionSection title="Decisões pendentes" empty="Nenhuma decisão pendente." count={queue.decisions.length}>
            {queue.decisions.map((item) => (
              <AttentionItem
                key={item.id}
                title={item.title}
                href={objectUrl(item.id)}
                label="Abrir decisão"
                detail="Proposta aguardando decisão."
                badge={<Badge variant="info" size="sm" label="Pendente" />}
              />
            ))}
          </AttentionSection>
          <AttentionSection
            title="Prazos de ações"
            empty="Nenhum prazo vencido ou divergente."
            count={queue.overdue_actions.length}
          >
            {queue.overdue_actions.map((item) => (
              <AttentionItem
                key={item.id}
                title={item.title}
                href={objectUrl(item.id)}
                label="Abrir ação"
                detail={
                  item.deadline
                    ? deadlineText(item.deadline)
                    : item.due_date
                      ? `Prazo vencido em ${displayDate(item.due_date)}`
                      : "Prazo indisponível"
                }
                badge={
                  <Badge variant="warning" size="sm" label={item.deadline?.conflict ? "Revisar prazos" : "Vencida"} />
                }
              />
            ))}
          </AttentionSection>
          <AttentionSection
            title="Sugestões aguardando aprovação"
            empty="Nenhuma sugestão aguardando sua aprovação."
            count={queue.suggestions.length}
          >
            {queue.suggestions.map((item) => (
              <AttentionItem
                key={item.id}
                title={item.title}
                href={`${base}/risk-review/?proposal=${encodeURIComponent(item.id)}#risk-proposal-${item.id}`}
                label="Revisar sugestão"
                detail={`${item.component === "action" ? "Ação sugerida" : "Relação sugerida"} · ${item.explanation}`}
                badge={<Badge variant="neutral" size="sm" label="Aprovação pendente" />}
              />
            ))}
          </AttentionSection>
        </>
      )}
    </div>
  );
});
