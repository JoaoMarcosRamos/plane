import { useState } from "react";
import { toJS } from "mobx";
import { Button } from "@makeplane/propel/components/button";
import { CheckboxField } from "@makeplane/propel/components/checkbox-field";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import type { RadarAgentConfigEntry, RadarAgentConfiguration } from "@/services/radar/agent-config.types";
import type { RadarAgentConfigStore } from "@/store/radar/agent-config.store";
import { configUpdate } from "./agent-config-input";
import { semanticError, semanticLabel } from "./semantic-utils";

export function AgentConfigurationForm({
  entry,
  store,
}: {
  entry: RadarAgentConfigEntry;
  store: RadarAgentConfigStore;
}) {
  const [draft, setDraft] = useState<RadarAgentConfiguration>(() => structuredClone(toJS(entry.configuration)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const disabled = busy || !entry.can_edit;
  const change = (configuration: RadarAgentConfiguration) => {
    setDraft(configuration);
    setError(null);
    setSaved(false);
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      const result = await store.save(entry.binding_id, configUpdate(draft));
      setDraft(structuredClone(result.configuration));
      setSaved(true);
    } catch (cause) {
      setError(semanticError(cause));
    } finally {
      setBusy(false);
    }
  };
  const reload = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await store.refresh(entry.binding_id);
      setDraft(structuredClone(result.configuration));
      setSaved(false);
    } catch (cause) {
      setError(semanticError(cause));
    } finally {
      setBusy(false);
    }
  };
  const scopeKeys = ["object_types", "fields"] as const;
  return (
    <form
      onSubmit={save}
      className="flex flex-col gap-5 rounded-lg border border-subtle p-5"
      data-testid="agent-config-form"
    >
      <div>
        <h2 className="text-16 font-semibold">{entry.configuration.identity.name}</h2>
        <p className="text-13 text-secondary">
          {entry.context} · Version {draft.version}
        </p>
        {!entry.can_edit && (
          <p className="text-13 text-secondary">A workspace administrator can edit this configuration.</p>
        )}
      </div>
      <fieldset className="flex flex-col gap-3" disabled={disabled}>
        <legend className="mb-2 text-14 font-semibold">Identity / Soul</legend>
        <InputField
          size="lg"
          orientation="vertical"
          id={`identity-${entry.binding_id}`}
          label="Name"
          value={draft.identity.name}
          maxLength={100}
          onChange={(event) => change({ ...draft, identity: { ...draft.identity, name: event.target.value } })}
        />
        <TextAreaField
          size="lg"
          id={`soul-${entry.binding_id}`}
          label="Principles and personality"
          value={draft.identity.soul}
          rows={3}
          maxLength={2000}
          onChange={(event) => change({ ...draft, identity: { ...draft.identity, soul: event.target.value } })}
        />
      </fieldset>
      <fieldset className="flex flex-col gap-3" disabled={disabled}>
        <legend className="mb-2 text-14 font-semibold">Role</legend>
        <InputField
          size="lg"
          orientation="vertical"
          id={`role-${entry.binding_id}`}
          label="Role name"
          value={draft.role.name}
          maxLength={100}
          onChange={(event) => change({ ...draft, role: { ...draft.role, name: event.target.value } })}
        />
        <TextAreaField
          size="lg"
          id={`purpose-${entry.binding_id}`}
          label="Purpose"
          value={draft.role.purpose}
          rows={3}
          maxLength={2000}
          onChange={(event) => change({ ...draft, role: { ...draft.role, purpose: event.target.value } })}
        />
      </fieldset>
      <fieldset className="flex flex-col gap-3" disabled={disabled}>
        <legend className="mb-2 text-14 font-semibold">Policies</legend>
        <TextAreaField
          size="lg"
          id={`guidelines-${entry.binding_id}`}
          label="Guidelines"
          hint="One guideline per line. Up to 20, with 500 characters each."
          value={draft.policies.guidelines.join("\n")}
          rows={4}
          onChange={(event) =>
            change({ ...draft, policies: { ...draft.policies, guidelines: event.target.value.split("\n") } })
          }
        />
        <p className="text-13 text-secondary">Execution is read-only. Domain changes require human approval.</p>
      </fieldset>
      <fieldset className="flex flex-col gap-3" disabled={disabled}>
        <legend className="mb-2 text-14 font-semibold">Permissions</legend>
        <p className="text-13 text-secondary">
          Selections are limited by the administrative grant and the authorized context.
        </p>
        <div className="flex flex-col gap-2">
          <span className="text-13 font-medium">Commands eligible for future proposals</span>
          {[...new Set([...entry.grant_ceiling.commands, ...draft.permissions.commands])].map((command) => (
            <CheckboxField
              size="lg"
              key={command}
              name={`${entry.binding_id}-${command}`}
              label={command}
              checked={draft.permissions.commands.includes(command)}
              disabled={disabled}
              onCheckedChange={(checked) =>
                change({
                  ...draft,
                  permissions: {
                    ...draft.permissions,
                    commands: checked
                      ? [...draft.permissions.commands, command]
                      : draft.permissions.commands.filter((item) => item !== command),
                  },
                })
              }
            />
          ))}
        </div>
        {scopeKeys.map((key) => (
          <TextAreaField
            size="lg"
            key={key}
            id={`${key}-${entry.binding_id}`}
            label={semanticLabel(key)}
            rows={2}
            hint={`One key per line. Grant allows: ${entry.grant_ceiling[key].join(", ") || "none"}. Use * only if listed.`}
            value={draft.permissions[key].join("\n")}
            onChange={(event) =>
              change({ ...draft, permissions: { ...draft.permissions, [key]: event.target.value.split("\n") } })
            }
          />
        ))}
        <CheckboxField
          size="lg"
          name={`all-objects-${entry.binding_id}`}
          label="Use all Objects in the authorized context"
          checked={draft.permissions.object_ids === null}
          disabled={disabled}
          onCheckedChange={(checked) =>
            change({ ...draft, permissions: { ...draft.permissions, object_ids: checked ? null : [] } })
          }
        />
        {draft.permissions.object_ids !== null && (
          <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
            {[
              ...entry.object_options,
              ...draft.permissions.object_ids
                .filter((id) => !entry.object_options.some((object) => object.id === id))
                .map((id) => ({ id, title: "Previously selected Object", type: "unavailable" })),
            ].map((object) => (
              <CheckboxField
                size="lg"
                key={object.id}
                name={`${entry.binding_id}-${object.id}`}
                label={`${object.title || "Untitled Object"} (${object.type})`}
                checked={draft.permissions.object_ids?.includes(object.id)}
                disabled={disabled}
                onCheckedChange={(checked) =>
                  change({
                    ...draft,
                    permissions: {
                      ...draft.permissions,
                      object_ids: checked
                        ? [...(draft.permissions.object_ids ?? []), object.id]
                        : (draft.permissions.object_ids?.filter((id) => id !== object.id) ?? []),
                    },
                  })
                }
              />
            ))}
            {entry.objects_truncated && (
              <p className="text-13 text-secondary">Showing the first 100 available Objects.</p>
            )}
          </div>
        )}
      </fieldset>
      <div className="flex gap-2">
        {entry.can_edit && (
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            type="submit"
            label={busy ? "Saving…" : "Save configuration"}
            disabled={busy}
          />
        )}
        <Button
          size="sm"
          stretch="auto"
          type="button"
          variant="secondary"
          label="Reload saved configuration"
          disabled={busy}
          onClick={() => void reload()}
        />
      </div>
      {error && (
        <p role="alert" className="text-13 text-danger-primary">
          {error === "agent_config_stale"
            ? "Configuration changed in another session. Your draft is preserved; reload before editing again."
            : error}
        </p>
      )}
      {saved && (
        <p role="status" className="text-13 text-secondary">
          Configuration saved. New executions use this version.
        </p>
      )}
    </form>
  );
}
