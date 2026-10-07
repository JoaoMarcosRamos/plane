import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { RadarService } from "@/services/radar/radar.service";
import type { RadarOperationalKind } from "@/services/radar/operational.types";
import { RadarOperationalStore } from "@/store/radar/operational.store";
import { useRadarStore } from "@/store/radar/provider";
import { RadarChoiceField } from "./choice-field";
import { deadlineText, entrySummary, instantText, operationalActor } from "./operational-text";

export const RadarOperationalPanel = observer(function RadarOperationalPanel({
  objectId,
  objectVersion,
}: {
  objectId: string;
  objectVersion: number;
}) {
  const root = useRadarStore();
  const [store] = useState(() => new RadarOperationalStore(root.workspaceSlug, new RadarService()));
  const [timezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [kind, setKind] = useState<RadarOperationalKind | undefined>();
  useEffect(() => {
    void store.load(objectId, objectVersion, root.schemaRevision, timezone, kind);
    return () => store.clear();
  }, [store, objectId, objectVersion, root.schemaRevision, timezone, kind]);
  const deadline = store.snapshot?.deadline;
  const assignment = store.snapshot?.operation_data.assignment;
  return (
    <section
      aria-label="Histórico operacional"
      className="mt-8 flex flex-col gap-3 border-t border-subtle pt-5"
      aria-busy={store.loading}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-16 font-semibold">Histórico operacional</h2>
        <Button
          size="sm"
          stretch="auto"
          label="Atualizar histórico"
          variant="secondary"
          disabled={store.loading}
          onClick={() => {
            store.clear();
            void root
              .loadObjectSemantics(objectId)
              .then(() =>
                store.load(
                  objectId,
                  root.objects.get(objectId)?.version ?? objectVersion,
                  root.schemaRevision,
                  timezone,
                  kind
                )
              )
              .catch((cause: unknown) => {
                console.error("Operational refresh failed", cause);
                store.invalidate();
              });
          }}
        />
      </div>
      {store.error && (
        <p role="alert" className="text-13 text-danger-primary">
          {store.error}
        </p>
      )}
      {store.snapshot?.migration_required && (
        <p role="alert" className="text-13 text-warning-primary">
          Fatos legados aguardam reconciliação administrativa.
        </p>
      )}
      {deadline?.source && (
        <p data-testid="radar-effective-deadline" role={deadline.conflict ? "alert" : undefined} className="text-13">
          {deadlineText(deadline)}
        </p>
      )}
      {store.snapshot && store.snapshot.executors.length > 0 && (
        <p className="text-12 text-secondary">
          Executores correntes: {store.snapshot.executors.map((id) => root.objects.get(id)?.title ?? id).join(", ")}
        </p>
      )}
      {assignment?.terms_changed === true && (
        <p className="text-12 text-warning-primary">
          Prazo ou executores mudaram; aceitação anterior não representa os termos correntes.
        </p>
      )}
      <RadarChoiceField
        id="operational-history-kind"
        label="Filtrar histórico"
        value={kind ?? "all"}
        disabled={store.loading}
        options={[
          { value: "all", label: "Todos" },
          { value: "delegation", label: "Delegações" },
          { value: "review", label: "Reviews" },
          { value: "measurement", label: "Medições" },
        ]}
        onChange={(value) => setKind(value === "all" ? undefined : (value as RadarOperationalKind))}
      />
      {store.loading && (
        <p role="status" className="text-13">
          Carregando histórico…
        </p>
      )}
      {!store.loading && store.snapshot && store.entries.length === 0 && (
        <p className="text-13 text-tertiary">Nenhum registro operacional.</p>
      )}
      <ol className="divide-y divide-subtle" data-testid="radar-operational-history">
        {store.entries.map((entry) => (
          <li key={entry.id} className="py-3 text-13">
            <p>{entrySummary(entry, timezone)}</p>
            <p className="mt-1 text-12 text-secondary">
              {operationalActor(entry)} ·{" "}
              {entry.occurred_at ? instantText(entry.occurred_at, timezone) : "Data do fato desconhecida (legado)"}
            </p>
            <p className="text-11 text-tertiary">
              {entry.origin === "legacy" ? "Preservado do arquivo legado" : "Registrado por command"}
              {entry.object_version ? ` · Object v${entry.object_version}` : ""}
            </p>
          </li>
        ))}
      </ol>
      {store.cursor && (
        <Button
          size="sm"
          stretch="auto"
          label="Carregar mais registros"
          variant="secondary"
          disabled={store.loading}
          onClick={() => void store.loadMore()}
        />
      )}
    </section>
  );
});
