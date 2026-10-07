import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { InputField } from "@makeplane/propel/components/input-field";
import { Button } from "@makeplane/propel/components/button";
import { Select } from "@plane/blocks/select";
import type { RadarObjectQuery, RadarObjectSummary } from "@/services/radar/types";
import { useRadarStore } from "@/store/radar/provider";
import { semanticError } from "./semantic-utils";

type Option = { value: string; label: string };

/** Bounded server search shared by relation and capability reference fields. */
export const RadarObjectPicker = observer(function RadarObjectPicker({
  id,
  label,
  value,
  onChange,
  query,
  multiple = false,
  disabled = false,
}: {
  id: string;
  label: string;
  value: string | string[];
  onChange: (value: string | string[]) => void;
  query: RadarObjectQuery;
  multiple?: boolean;
  disabled?: boolean;
}) {
  const store = useRadarStore();
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<RadarObjectSummary[]>([]);
  const [selectedOptions, setSelectedOptions] = useState<Option[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const queryKey = JSON.stringify(query);
  const revision = store.schemaRevision;
  useEffect(() => {
    let active = true;
    generation.current++;
    setRows([]);
    setCursor(null);
    setLoading(true);
    const timer = window.setTimeout(() => {
      store
        .searchObjects({ ...(JSON.parse(queryKey) as RadarObjectQuery), q: search })
        .then((result) => {
          if (!active) return;
          setRows(result);
          setCursor(result.next_cursor ?? null);
          setError(null);
        })
        .catch((cause: unknown) => {
          if (active) setError(semanticError(cause));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 200);
    return () => {
      active = false;
      generation.current++;
      window.clearTimeout(timer);
    };
  }, [store, queryKey, search, revision, retry]);
  const options = rows.map((row) => ({
    value: row.id,
    label: `${store.objectTypes.find((type) => type.id === row.object_type)?.name ?? "Object"} · ${row.title}`,
  }));
  const selected = Array.isArray(value) ? value : value ? [value] : [];
  const allOptions = Array.from(
    new Map([...selectedOptions, ...options].map((option) => [option.value, option])).values()
  );
  const choose = (ids: string | string[] | null) => {
    const values = Array.isArray(ids) ? ids : ids ? [ids] : [];
    setSelectedOptions(allOptions.filter((option) => values.includes(option.value)));
    onChange(multiple ? values : (values[0] ?? ""));
  };
  const loadMore = async () => {
    if (!cursor || loading) return;
    setLoading(true);
    const request = generation.current;
    try {
      const result = await store.searchObjects({ ...query, q: search, cursor });
      if (request !== generation.current) return;
      setRows((previous) => Array.from(new Map([...previous, ...result].map((row) => [row.id, row])).values()));
      setCursor(result.next_cursor ?? null);
    } catch (cause) {
      if (request === generation.current) setError(semanticError(cause));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  };
  return (
    <div className="flex flex-col gap-2" data-testid={id}>
      <InputField
        id={`${id}-search`}
        label={`Search ${label}`}
        size="lg"
        orientation="vertical"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        disabled={disabled || (loading && !!cursor)}
      />
      <span className="text-13 font-medium">{label}</span>
      {multiple ? (
        <Select<Option>
          multiple
          getValues={() => allOptions}
          value={allOptions.filter((option) => selected.includes(option.value))}
          onChange={choose}
          getOptionValue={(option) => option.value}
          getOptionLabel={(option) => option.label}
          disabled={disabled || loading}
          pinSelected={false}
        >
          <Select.Trigger variant="select-md" aria-label={label}>
            <span>{selected.length ? `${selected.length} selected` : `Select ${label}`}</span>
          </Select.Trigger>
        </Select>
      ) : (
        <Select<Option>
          getValues={() => allOptions}
          value={allOptions.find((option) => option.value === value) ?? null}
          onChange={choose}
          getOptionValue={(option) => option.value}
          getOptionLabel={(option) => option.label}
          disabled={disabled || loading}
          pinSelected={false}
        >
          <Select.Trigger variant="select-md" aria-label={label}>
            <span>{allOptions.find((option) => option.value === value)?.label ?? `Select ${label}`}</span>
          </Select.Trigger>
        </Select>
      )}
      {loading && <p role="status">Searching…</p>}
      {!loading && !rows.length && !error && <p role="status">No matching objects.</p>}
      {error && (
        <p role="alert">
          {error}{" "}
          <button type="button" className="underline" onClick={() => setRetry((value) => value + 1)}>
            Retry
          </button>
        </p>
      )}
      {cursor && (
        <Button
          type="button"
          label="More results"
          variant="secondary"
          size="sm"
          stretch="auto"
          disabled={disabled || loading}
          onClick={() => void loadMore()}
        />
      )}
    </div>
  );
});
