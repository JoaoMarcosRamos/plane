import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useRouter } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { BaseListLayout } from "@/components/base-layouts/list/layout";
import { useRadarStore } from "@/store/radar/provider";
import { RadarCreateObjectDialog } from "./create-object-dialog";

export const RadarObjectsList = observer(function RadarObjectsList() {
  const store = useRadarStore();
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setStatus("loading");
    Promise.all([store.loadTypes(), store.loadList()])
      .then(() => {
        if (active) setStatus("ready");
        return undefined;
      })
      .catch((error: unknown) => {
        console.error("RADAR list failed", error);
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [store, retry]);
  const objects = store.listedObjects;
  const items = Object.fromEntries(objects.map((object) => [object.id, { ...object }]));
  const groups = store.objectTypes.map((type) => ({ id: type.id, name: type.name }));
  const groupedItemIds = Object.fromEntries(
    groups.map((group) => [
      group.id,
      objects.filter((object) => object.object_type === group.id).map((object) => object.id),
    ])
  );
  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-24 font-semibold">Objects</h1>
        <Button
          stretch="auto"
          variant="primary"
          size="md"
          label="Create object"
          onClick={() => setCreating(true)}
          disabled={status !== "ready"}
        />
      </div>
      {status === "loading" && <p role="status">Loading objects…</p>}
      {status === "error" && (
        <div role="alert">
          Could not load objects.{" "}
          <button onClick={() => setRetry((value) => value + 1)} className="underline">
            Retry
          </button>
        </div>
      )}
      {status === "ready" && (
        <>
          <p className="text-13 text-secondary">{objects.length} objects in this workspace</p>
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
      {creating && <RadarCreateObjectDialog onClose={() => setCreating(false)} />}
    </div>
  );
});
