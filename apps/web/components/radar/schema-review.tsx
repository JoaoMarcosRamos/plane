import { useEffect, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { useRadarStore } from "@/store/radar/provider";

/** Keeps drafts in place while an explicit review accepts the new definitions/authority. */
export function useRadarSchemaReview() {
  const store = useRadarStore();
  const current = `${store.schemaRevision}:${store.authorityRevision}`;
  const [reviewed, setReviewed] = useState<string | null>(store.schemaRevision === 0 ? null : current);
  useEffect(() => {
    if (reviewed === null && store.schemaRevision > 0) setReviewed(current);
  }, [reviewed, current, store.schemaRevision]);
  const pending = reviewed !== null && reviewed !== current;
  return { pending, canWrite: store.canWrite && !pending, review: () => setReviewed(current) };
}

export function RadarSchemaReview({ pending, onReview }: { pending: boolean; onReview: () => void }) {
  if (!pending) return null;
  return (
    <div role="alert" className="my-4 rounded-md border border-subtle p-3 text-13" data-testid="radar-schema-review">
      <p>The workspace definitions or permissions changed. Review your draft using the current fields before saving.</p>
      <Button
        stretch="auto"
        type="button"
        variant="secondary"
        size="sm"
        label="I reviewed the changes"
        onClick={onReview}
      />
    </div>
  );
}
