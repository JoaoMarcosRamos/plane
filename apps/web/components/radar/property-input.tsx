import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { MemberSelect } from "@/components/dropdowns/member/member-select";
import type { RadarPropertyDefinition } from "@/services/radar/types";
import { RadarChoiceField } from "./choice-field";
import { semanticLabel } from "./semantic-utils";

/** One control per supported kind, shared by the property editor and the creation form. */
export function RadarPropertyInput({
  definition,
  id,
  label,
  value,
  onChange,
  disabled,
  options,
  rows,
  hint,
}: {
  definition: RadarPropertyDefinition;
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  /** Restricts enum choices, e.g. to the lifecycle targets available to this actor. */
  options?: string[] | null;
  rows?: number;
  hint?: string;
}) {
  if (definition.value_type === "enum" || definition.value_type === "boolean") {
    const choices =
      definition.value_type === "boolean"
        ? [
            { value: "true", label: "Yes" },
            { value: "false", label: "No" },
          ]
        : (options ?? definition.config.choices ?? []).map((item) => ({ value: item, label: semanticLabel(item) }));
    return (
      <RadarChoiceField id={id} label={label} value={value} options={choices} onChange={onChange} disabled={disabled} />
    );
  }
  if (definition.value_type === "user") {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-13 font-medium">{label}</span>
        <MemberSelect
          testId={id}
          variant="select-md"
          value={value || null}
          onChange={onChange}
          disabled={disabled}
          clearable={false}
          placeholder="Select member"
        />
      </div>
    );
  }
  if (definition.value_type === "string_list" || definition.value_type === "string") {
    return (
      <TextAreaField
        id={id}
        label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        size="lg"
        rows={rows ?? (definition.value_type === "string_list" ? 2 : 3)}
        hint={hint ?? (definition.value_type === "string_list" ? "One item per line." : undefined)}
      />
    );
  }
  const type = {
    number: "number",
    integer: "number",
    date: "date",
    datetime: "datetime-local",
    email: "email",
    uri: "url",
  }[definition.value_type];
  return (
    <InputField
      id={id}
      label={label}
      size="lg"
      orientation="vertical"
      type={type}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      min={definition.config.min}
      max={definition.config.max}
      step={definition.value_type === "integer" ? 1 : "any"}
      hint={hint}
    />
  );
}
