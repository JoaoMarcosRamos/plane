/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";

type Props = {
  title: string;
  /** Plane source the section exercises, shown so reviewers can trace what is being reused. */
  source: string;
  children: ReactNode;
};

export function RadarSpikeSection({ title, source, children }: Props) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-subtle p-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-14 font-semibold text-primary">{title}</h2>
        <code className="text-11 text-tertiary">{source}</code>
      </header>
      {children}
    </section>
  );
}
