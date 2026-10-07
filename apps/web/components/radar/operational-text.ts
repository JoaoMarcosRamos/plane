import type { RadarDeadline, RadarOperationalEntry } from "../../services/radar/operational.types";

export function dateText(value: string) {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}
export function instantText(value: string, timezone: string) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium", timeZone: timezone }).format(
    new Date(value)
  );
}
export function deadlineText(deadline: RadarDeadline) {
  if (deadline.conflict)
    return `Prazos divergentes: data ${dateText(deadline.due_date!)}; delegação ${instantText(deadline.due_at!, deadline.timezone)} · ${deadline.timezone}`;
  if (deadline.effective_at) return `${instantText(deadline.effective_at, deadline.timezone)} · ${deadline.timezone}`;
  return deadline.effective_date ? dateText(deadline.effective_date) : "Sem prazo definido";
}
export function entrySummary(entry: RadarOperationalEntry, timezone: string) {
  if (entry.kind === "review") return String(entry.payload.assessment);
  if (entry.kind === "measurement")
    return `Medição ${entry.payload.value} · ${instantText(String(entry.payload.measured_at), timezone)}`;
  return `Delegação · ${instantText(String(entry.payload.due_at), timezone)} · ${Array.isArray(entry.payload.executor_ids) ? entry.payload.executor_ids.length : 0} executor(es)`;
}
export function operationalActor(entry: RadarOperationalEntry) {
  if (entry.actor_type === "unknown") return "Autoria original desconhecida (legado)";
  const label = { human: "Humano", agent: "Agente", system: "Sistema", integration: "Integração" }[entry.actor_type];
  return `${label} · ${entry.actor_id}`;
}
