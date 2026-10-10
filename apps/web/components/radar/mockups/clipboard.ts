/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Copies text. Resolves to false when the browser refuses, so nobody is told it worked when it did not. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (!globalThis.navigator?.clipboard) return false;
    await globalThis.navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
