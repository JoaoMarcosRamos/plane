import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useRouter } from "next/navigation";
import { InputField } from "@makeplane/propel/components/input-field";
import { semanticError } from "./semantic-utils";
import { Button } from "@makeplane/propel/components/button";
import { BaseListLayout } from "@/components/base-layouts/list/layout";
import { useRadarStore } from "@/store/radar/provider";
import { RadarCreateObjectDialog } from "./create-object-dialog";

export const RadarObjectsList = observer(function RadarObjectsList({ typeKey }: { typeKey?: string }) {
  const store = useRadarStore();
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedType = store.objectTypes.find((type) => type.key === typeKey);
  const revision = store.schemaRevision;
  useEffect(() => {
    let active = true;
    setStatus("loading");
    const timer = window.setTimeout(() => {
      void store
        .loadTypes()
        .then(() => {
          const type = store.objectTypes.find((item) => item.key === typeKey);
          if (typeKey && !type) return;
          return store.loadList({ q: search, ...(type ? { object_type: type.id } : {}) });
        })
        .then(() => {
          if (active) setStatus("ready");
          return undefined;
        })
        .catch((error: unknown) => {
          console.error("RADAR list failed", error);
          if (active) {
            setStatus("error");
            setError(semanticError(error));
          }
        });
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [store, retry, typeKey, search, revision]);
  const objects = store.listedObjects.filter((object) => !typeKey || object.object_type === selectedType?.id);
  const items = Object.fromEntries(objects.map((object) => [object.id, { ...object }]));
  const groups = store.objectTypes
    .filter((type) => !typeKey || type.key === typeKey)
    .map((type) => ({ id: type.id, name: type.name }));
  const groupedItemIds = Object.fromEntries(
    groups.map((group) => [
      group.id,
      objects.filter((object) => object.object_type === group.id).map((object) => object.id),
    ])
  );
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-24 font-semibold">{selectedType?.name ?? "Objects"}</h1>
        <Button
          stretch="auto"
          variant="primary"
          size="md"
          label="Create object"
          onClick={() => setCreating(true)}
          disabled={status !== "ready" || !store.canWrite || (!!typeKey && !selectedType)}
        />
      </div>
      {status === "ready" && store.schemaStatus === "uninitialized" && (
        <p role="status">The workspace schema has not been installed. A workspace admin must provision it.</p>
      )}
      <InputField
        id="radar-object-search"
        label="Search objects"
        size="lg"
        orientation="vertical"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {status === "ready" && typeKey && !selectedType && <p role="status">This object type is unavailable.</p>}
      {status === "loading" && <p role="status">Loading objects…</p>}
      {status === "error" && (
        <div role="alert">
          Could not load objects. {error}{" "}
          <button onClick={() => setRetry((value) => value + 1)} className="underline">
            Retry
          </button>
        </div>
      )}
      {status === "ready" && (
        <>
          <p className="text-13 text-secondary">{objects.length} objects loaded</p>
          <div className="min-h-0 flex-1 rounded-md border border-subtle">
            <BaseListLayout
              items={items}
              groups={groups}
              groupedItemIds={groupedItemIds}
              showEmptyGroups
              renderItem={(item) => (
                <button
                  className="w-full border-b border-subtle px-6 py-3 text-left hover:bg-layer-1-hover"
                  onClick={() => router.push(`/${store.workspaceSlug}/radar/objects/${item.id}/`)}
                >
                  {items[item.id].title}
                </button>
              )}
            />
          </div>
        </>
      )}
      {store.listCursor && (!typeKey || selectedType) && (
        <Button
          label="More objects"
          variant="secondary"
          size="md"
          stretch="auto"
          disabled={loadingMore || status !== "ready"}
          onClick={() => {
            setLoadingMore(true);
            void store
              .loadList(
                {
                  q: search,
                  ...(selectedType ? { object_type: selectedType.id } : {}),
                  cursor: store.listCursor ?? undefined,
                },
                true
              )
              .catch((cause: unknown) => {
                setError(semanticError(cause));
                setStatus("error");
              })
              .finally(() => setLoadingMore(false));
          }}
        />
      )}
      {creating && <RadarCreateObjectDialog onClose={() => setCreating(false)} />}
    </div>
  );
});
