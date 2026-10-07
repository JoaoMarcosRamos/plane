import { v4 as uuidv4 } from "uuid";
import type { RadarMutationContext, RadarPendingCommand } from "../../services/radar/types";

type Intent = {
  signature: string;
  payload: unknown;
  context: RadarMutationContext;
  busy: boolean;
  approval?: RadarPendingCommand;
};

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    // eslint-disable-next-line unicorn/no-array-sort -- ES2022 target; this array is allocated locally.
    entries.sort(([a], [b]) => a.localeCompare(b));
    return Object.fromEntries(entries.map(([key, item]) => [key, canonical(item)]));
  }
  return value;
}

/** In-memory only: one workspace/session owns these exact retry envelopes. */
export class RadarMutationIntents {
  private readonly intents = new Map<string, Intent>();

  resume(approvalId: string) {
    const intent = [...this.intents.values()].find((item) => item.approval?.approval_id === approvalId);
    if (!intent || intent.busy) throw new Error("Load and review the pending intention before resuming it.");
    intent.context.approval_id = approvalId;
  }

  async run<Input, Result>(
    slot: string,
    payload: Input,
    context: () => RadarMutationContext,
    operation: (payload: Input, context: RadarMutationContext) => Promise<Result>
  ): Promise<Result> {
    const signature = JSON.stringify(canonical(payload));
    let intent = this.intents.get(slot);
    if (intent?.busy) throw new Error("This change is already being submitted.");
    if (!intent || intent.signature !== signature) {
      intent = {
        signature,
        payload: JSON.parse(JSON.stringify(payload)) as Input,
        context: { ...context(), idempotency_key: uuidv4() },
        busy: false,
      };
      this.intents.set(slot, intent);
    }
    intent.busy = true;
    try {
      const result = await operation(intent.payload as Input, intent.context);
      this.intents.delete(slot);
      return result;
    } catch (cause) {
      const pending = (cause as { command?: RadarPendingCommand } | null)?.command;
      if (pending?.status === "pending_approval") intent.approval = pending;
      else {
        const status = (cause as { response?: { status?: number } } | null)?.response?.status;
        // A timeout/server error may follow a commit. Retry it with its original payload and versions.
        if (status !== undefined && status >= 400 && status < 500 && ![408, 429].includes(status))
          this.intents.delete(slot);
      }
      throw cause;
    } finally {
      intent.busy = false;
    }
  }
}
