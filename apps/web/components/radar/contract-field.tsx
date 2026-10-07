import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { Select } from "@plane/blocks/select";
import type { RadarObject } from "@/services/radar/types";
import { RadarChoiceField } from "./choice-field";
import { objectOptions } from "./capability-form";
import type { RadarFormField } from "./capability-form";
import { semanticLabel } from "./semantic-utils";

/** Renders one capability input field; references list Objects of the hinted types only. */
export function RadarContractField({
  id,
  field,
  value,
  onChange,
  objects,
  exclude,
  disabled,
}: {
  id: string;
  field: RadarFormField;
  value: string | string[];
  onChange: (value: string | string[]) => void;
  objects: RadarObject[];
  exclude?: string;
  disabled: boolean;
}) {
  const label = field.required ? field.label : `${field.label} (optional)`;
  const single = Array.isArray(value) ? (value[0] ?? "") : value;
  if (field.kind === "object" || field.kind === "choice" || field.kind === "boolean") {
    const options =
      field.kind === "object"
        ? objectOptions(objects, field.objectTypes, exclude)
        : field.kind === "boolean"
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
  if (field.kind === "objects") {
    const options = objectOptions(objects, field.objectTypes, exclude);
    const selected = Array.isArray(value) ? value : value ? [value] : [];
    return (
      <div className="flex flex-col gap-1.5" data-testid={id}>
        <span className="text-13 font-medium">{label}</span>
        <Select<{ value: string; label: string }>
          multiple
          getValues={() => options}
          value={options.filter((option) => selected.includes(option.value))}
          onChange={(ids) => onChange(ids)}
          getOptionValue={(option) => option.value}
          getOptionLabel={(option) => option.label}
          disabled={disabled}
          pinSelected={false}
        >
          <Select.Trigger variant="select-md">
            <span>{selected.length ? `${selected.length} selected` : "Select objects"}</span>
          </Select.Trigger>
        </Select>
      </div>
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
