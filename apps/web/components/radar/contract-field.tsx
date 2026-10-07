import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { RadarObjectPicker } from "./object-picker";
import { RadarChoiceField } from "./choice-field";
import type { RadarFormField } from "./capability-form";
import { semanticLabel } from "./semantic-utils";

/** Renders one capability input field; references list Objects of the hinted types only. */
export function RadarContractField({
  id,
  field,
  value,
  onChange,
  exclude,
  disabled,
}: {
  id: string;
  field: RadarFormField;
  value: string | string[];
  onChange: (value: string | string[]) => void;
  exclude?: string;
  disabled: boolean;
}) {
  const label = field.required ? field.label : `${field.label} (optional)`;
  const single = Array.isArray(value) ? (value[0] ?? "") : value;
  if (field.kind === "object" || field.kind === "objects") {
    return (
      <RadarObjectPicker
        id={id}
        label={label}
        value={value}
        onChange={onChange}
        query={{ type_keys: field.objectTypes.includes("*") ? undefined : field.objectTypes.join(","), exclude }}
        multiple={field.kind === "objects"}
        disabled={disabled}
      />
    );
  }
  if (field.kind === "choice" || field.kind === "boolean") {
    const options =
      field.kind === "boolean"
        ? [
            { value: "true", label: "Yes" },
            { value: "false", label: "No" },
          ]
        : field.choices.map((item) => ({ value: item, label: semanticLabel(item) }));
    return (
      <RadarChoiceField
        id={id}
        label={label}
        value={single}
        options={options}
        onChange={onChange}
        disabled={disabled}
      />
    );
  }
  if (field.kind === "text") {
    return (
      <TextAreaField
        id={id}
        label={label}
        value={single}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        size="lg"
        rows={2}
      />
    );
  }
  return (
    <InputField
      id={id}
      label={label}
      size="lg"
      orientation="vertical"
      type={field.kind === "datetime" ? "datetime-local" : field.kind === "unsupported" ? "text" : "number"}
      step={field.kind === "integer" ? 1 : "any"}
      value={single}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled || field.kind === "unsupported"}
    />
  );
}
