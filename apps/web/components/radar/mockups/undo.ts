/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Undo by effect, not by snapshot. An action is recorded as what it changed (what it created, removed and
 * which fields it moved). Undoing it reverses only those effects, field by field, against the state as it is
 * now: whatever happened afterwards, to the same item or to others, stays. A field someone changed again after
 * the action is left alone and reported, instead of being overwritten.
 */

export type TEntity = { id: string; [key: string]: unknown };

/** The state the undo cares about: collections of entities with ids, plus loose values. */
export type TUndoState = {
  collections: Record<string, TEntity[]>;
  values: Record<string, unknown>;
};

type TFieldChange = { key: string; before: unknown; after: unknown };

export type TDelta = {
  created: { collection: string; value: TEntity }[];
  removed: { collection: string; value: TEntity; index: number }[];
  changed: { collection: string; id: string; fields: TFieldChange[] }[];
  values: TFieldChange[];
};

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const keyOf = (value: unknown) => JSON.stringify(value);
const labelOf = (entity: TEntity) => String(entity.title ?? entity.id);
const clone = <T>(value: T): T => structuredClone(value);

export const isEmptyDelta = (delta: TDelta) =>
  !delta.created.length && !delta.removed.length && !delta.changed.length && !delta.values.length;

/** What `after` did to `before`. */
export function diffStates(before: TUndoState, after: TUndoState): TDelta {
  const delta: TDelta = { created: [], removed: [], changed: [], values: [] };
  const names = new Set([...Object.keys(before.collections), ...Object.keys(after.collections)]);
  for (const collection of names) {
    const was = before.collections[collection] ?? [];
    const now = after.collections[collection] ?? [];
    const wasById = new Map(was.map((entity) => [entity.id, entity]));
    const nowById = new Map(now.map((entity) => [entity.id, entity]));
    now.forEach((entity) => {
      if (!wasById.has(entity.id)) delta.created.push({ collection, value: clone(entity) });
    });
    was.forEach((entity, index) => {
      if (!nowById.has(entity.id)) delta.removed.push({ collection, value: clone(entity), index });
    });
    now.forEach((entity) => {
      const previous = wasById.get(entity.id);
      if (!previous) return;
      const fields: TFieldChange[] = [];
      for (const key of new Set([...Object.keys(previous), ...Object.keys(entity)])) {
        if (!same(previous[key], entity[key]))
          fields.push({ key, before: clone(previous[key]), after: clone(entity[key]) });
      }
      if (fields.length) delta.changed.push({ collection, id: entity.id, fields });
    });
  }
  for (const key of new Set([...Object.keys(before.values), ...Object.keys(after.values)])) {
    if (!same(before.values[key], after.values[key]))
      delta.values.push({ key, before: clone(before.values[key]), after: clone(after.values[key]) });
  }
  return delta;
}

export type TUndoResult = {
  state: TUndoState;
  /** How many of the action's effects were reversed. */
  reverted: number;
  /** Effects left as they are, because they were changed again afterwards. */
  conflicts: string[];
};

/**
 * Reverses `delta` against `current`. `onReverted` runs for each entity that had something reversed, so the
 * caller can record in its history that the action was undone (the history itself is never erased).
 */
export function revertDelta(
  current: TUndoState,
  delta: TDelta,
  onReverted?: (collection: string, entity: TEntity) => void
): TUndoResult {
  const state = clone(current);
  const conflicts: string[] = [];
  let reverted = 0;
  const find = (collection: string, id: string) => state.collections[collection]?.find((entity) => entity.id === id);

  // 1. What the action created goes away, unless it was changed since.
  for (const { collection, value } of delta.created) {
    const entity = find(collection, value.id);
    if (!entity) continue;
    if (same(entity, value)) {
      state.collections[collection] = state.collections[collection].filter((candidate) => candidate.id !== value.id);
      reverted += 1;
    } else conflicts.push(`${labelOf(entity)} foi alterado depois e continua.`);
  }

  // 2. What it removed comes back, unless something with the same identity exists again.
  for (const { collection, value, index } of delta.removed) {
    if (find(collection, value.id)) continue;
    const list = state.collections[collection] ?? (state.collections[collection] = []);
    list.splice(Math.min(index, list.length), 0, clone(value));
    reverted += 1;
  }

  // 3. Fields it moved go back, field by field.
  for (const { collection, id, fields } of delta.changed) {
    const entity = find(collection, id);
    if (!entity) {
      conflicts.push("Um item mudou ou saiu depois e não foi alterado.");
      continue;
    }
    let touched = false;
    for (const change of fields) {
      if (Array.isArray(change.before) && Array.isArray(change.after)) {
        // Lists are reversed by element, so what others added meanwhile is kept. History is never trimmed.
        if (change.key === "activity") continue;
        const afterKeys = new Set(change.after.map(keyOf));
        const beforeKeys = new Set(change.before.map(keyOf));
        const added = change.after.filter((value) => !beforeKeys.has(keyOf(value)));
        const removedValues = change.before.filter((value) => !afterKeys.has(keyOf(value)));
        const addedKeys = new Set(added.map(keyOf));
        const now = Array.isArray(entity[change.key]) ? (entity[change.key] as unknown[]) : [];
        const next = now.filter((value) => !addedKeys.has(keyOf(value)));
        for (const value of removedValues) if (!next.some((candidate) => same(candidate, value))) next.push(value);
        entity[change.key] = next;
        touched = touched || added.length > 0 || removedValues.length > 0;
      } else if (same(entity[change.key], change.after)) {
        if (change.before === undefined) delete entity[change.key];
        else entity[change.key] = clone(change.before);
        touched = true;
      } else conflicts.push(`${labelOf(entity)}: “${change.key}” foi alterado depois e continua.`);
    }
    if (touched) {
      reverted += 1;
      onReverted?.(collection, entity);
    }
  }

  // 4. Loose values (today's focus, tomorrow's first item).
  for (const change of delta.values) {
    if (same(state.values[change.key], change.after)) {
      state.values[change.key] = clone(change.before);
      reverted += 1;
    } else conflicts.push(`“${change.key}” foi alterado depois e continua.`);
  }

  return { state, reverted, conflicts };
}
