import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";

export function RadarChoiceField({
  id,
  label,
  value,
  options,
  onChange,
  disabled = false,
  placeholder = "Select…",
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label id={`${id}-label`} className="text-13 font-medium" htmlFor={id}>
        {label}
      </label>
      <Select value={value || null} onValueChange={(next) => onChange(next ?? "")} items={options} disabled={disabled}>
        <SelectTrigger id={id} aria-labelledby={`${id}-label`} size="md" placeholder={placeholder} />
        <SelectContent>
          <SelectList>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value} label={option.label} size="md" />
            ))}
          </SelectList>
        </SelectContent>
      </Select>
    </div>
  );
}
