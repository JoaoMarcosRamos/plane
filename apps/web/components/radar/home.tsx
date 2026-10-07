/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge } from "@makeplane/propel/components/badge";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUser } from "@/hooks/store/user";

type TCheckStatus = "pass" | "test" | "not_implemented";

type TShellCheck = {
  label: string;
  status: TCheckStatus;
  detail?: string;
};

const STATUS_BADGE: Record<TCheckStatus, { label: string; variant: "success" | "info" | "neutral" }> = {
  pass: { label: "✓", variant: "success" },
  test: { label: "test", variant: "info" },
  not_implemented: { label: "not implemented", variant: "neutral" },
};

/** Phase 0 landing page: states plainly that this is the shell spike, not the RADAR product. */
export const RadarHome = observer(function RadarHome() {
  const { workspaceSlug } = useParams();
  const { currentWorkspace } = useWorkspace();
  const { data: currentUser } = useUser();

  // The first rows pass by construction: this component only renders inside the workspace and
  // authentication wrappers, under the (radar) route group and next to the RADAR sidebar.
  const checks: TShellCheck[] = [
    { label: "Workspace shell", status: "pass", detail: currentWorkspace?.name },
    { label: "Authentication", status: "pass", detail: currentUser?.email },
    { label: "RADAR routing", status: "pass", detail: `/${workspaceSlug}/radar` },
    { label: "RADAR sidebar", status: "pass" },
    { label: "Generic components", status: "test", detail: "see Spike Components" },
    { label: "RADAR Core", status: "pass", detail: "Objects persisted through commands" },
    { label: "Agent", status: "not_implemented" },
  ];

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-semibold text-primary">RADAR</h1>
        <p className="text-16 text-secondary">Human–Agent Operating System</p>
        <p className="text-13 text-tertiary">Phase 0 — Core Foundation</p>
      </header>

      <div className="rounded-md border border-subtle bg-layer-1 p-3 text-13 text-secondary">
        Create and edit workspace objects. Your changes are persisted in RADAR Core.
      </div>

      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="radar-shell-checks">
        {checks.map((check) => {
          const badge = STATUS_BADGE[check.status];
          return (
            <li
              key={check.label}
              className="flex items-center justify-between gap-3 rounded-md border border-subtle px-3 py-2.5"
            >
              <div className="flex min-w-0 flex-col">
                <span className="text-13 font-medium text-primary">{check.label}</span>
                {check.detail && <span className="truncate text-11 text-tertiary">{check.detail}</span>}
              </div>
              <Badge variant={badge.variant} size="sm" label={badge.label} />
            </li>
          );
        })}
      </ul>

      <Link href={`/${workspaceSlug}/radar/objects/`} className="text-13 text-accent-primary underline">
        Open Objects
      </Link>
    </div>
  );
});
