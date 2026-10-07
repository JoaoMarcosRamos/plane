import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { RadarObjectProperty, RadarPropertyType } from "../../services/radar/types";
import { RadarPropertyEditor } from "./property-editor";

vi.mock("@makeplane/propel/components/input-field", () => ({
  InputField: (props: { id: string; type: string; value: string; disabled: boolean }) =>
    createElement("input", {
      id: props.id,
      type: props.type,
      value: props.value,
      disabled: props.disabled,
      readOnly: true,
    }),
}));
vi.mock("@makeplane/propel/components/text-area-field", () => ({
  TextAreaField: (props: { value: string; disabled: boolean }) =>
    createElement("textarea", { value: props.value, disabled: props.disabled, readOnly: true }),
}));
vi.mock("@makeplane/propel/components/button", () => ({
  Button: (props: { label: string; disabled: boolean; "aria-label"?: string }) =>
    createElement("button", { disabled: props.disabled, "aria-label": props["aria-label"] }, props.label),
}));
vi.mock("./choice-field", () => ({
  RadarChoiceField: (props: { value: string; disabled: boolean; options: { value: string; label: string }[] }) =>
    createElement(
      "select",
      { value: props.value, disabled: props.disabled, onChange: () => undefined },
      props.options.map((option) => createElement("option", { key: option.value, value: option.value }, option.label))
    ),
}));
vi.mock("@/components/dropdowns/member/member-select", () => ({
  MemberSelect: (props: { value: string; disabled: boolean }) =>
    createElement("input", {
      "data-control": "workspace-member",
      value: props.value,
      disabled: props.disabled,
      readOnly: true,
    }),
}));

const row = (value_type: RadarPropertyType, value: RadarObjectProperty["value"]): RadarObjectProperty => ({
  definition: {
    id: "def",
    workspace: "workspace",
    object_type: "type",
    key: "property",
    name: "Property",
    value_type,
    config: { choices: ["active"] },
    is_required: false,
    is_active: true,
    is_system: true,
  },
  stored_value: null,
  has_value: value !== null,
  value,
});
const render = (property: RadarObjectProperty, canWrite = true, busy = false) =>
  renderToStaticMarkup(
    createElement(RadarPropertyEditor, { row: property, canWrite, busy, onSave: vi.fn(), onRemove: vi.fn() })
  );

describe("generic semantic property controls", () => {
  it.each([
    ["number", 1.5, 'type="number"'],
    ["integer", 3, 'type="number"'],
    ["date", "2026-10-03", 'type="date"'],
    ["datetime", "2026-10-03T13:00:00Z", 'type="datetime-local"'],
    ["email", "user@example.com", 'type="email"'],
    ["uri", "https://example.com", 'type="url"'],
    ["user", "member-id", 'data-control="workspace-member"'],
    ["string", "Text", "<textarea"],
    ["string_list", ["First", "Second"], "<textarea"],
    ["enum", "active", "<select"],
    ["boolean", false, "<select"],
  ] satisfies [RadarPropertyType, RadarObjectProperty["value"], string][])(
    "renders %s from its persisted definition",
    (type, value, marker) => {
      const property = row(type, value);
      expect(render(property)).toContain(marker);
    }
  );
  it("shows a false boolean as No rather than an unset value", () => {
    expect(render(row("boolean", false))).toContain('value="false" selected="">No');
  });
  it("disables guest input and omits mutation controls", () => {
    const html = render(row("string", "Text"), false);
    expect(html).toContain('disabled=""');
    expect(html).not.toContain("Save Property");
    expect(html).not.toContain("Clear Property");
  });
  it("offers clear only for persisted optional values without a default", () => {
    const property = row("date", "2026-10-03");
    property.stored_value = {
      id: "value",
      workspace: "workspace",
      object: "object",
      definition: "def",
      value: "2026-10-03",
      created_by: null,
      updated_by: null,
      created_at: "",
      updated_at: "",
    };
    expect(render(property)).toContain("Clear Property");
    property.definition.config.default = "2026-10-03";
    expect(render(property)).not.toContain("Clear Property");
    delete property.definition.config.default;
    property.definition.is_required = true;
    expect(render(property)).not.toContain("Clear Property");
  });
});
