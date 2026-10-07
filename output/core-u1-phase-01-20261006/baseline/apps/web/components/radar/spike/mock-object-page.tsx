/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Badge } from "@makeplane/propel/components/badge";
import { DateSelect } from "@plane/blocks/property-select";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// hooks
import { useUser } from "@/hooks/store/user";
// local imports
import type { TRadarSpikeObject, TRadarSpikeRelation } from "./mock-data";
import { RADAR_SPIKE_OBJECTS, RADAR_SPIKE_RELATIONS, getRadarSpikeTypeLabel } from "./mock-data";
import { RadarSpikeNotesEditor } from "./notes-editor";

const OBJECT_ID = "decision-github-enterprise";

const INITIAL_CONTEXT =
  "<p>Os times precisam de um ambiente governado para experimentar IA generativa sobre código interno. " +
  "O GitHub Enterprise concentra repositórios, políticas de acesso e auditoria num só lugar.</p>";

const getObject = (id: string) => RADAR_SPIKE_OBJECTS.find((object) => object.id === id);

type RelationRowProps = {
  relation: TRadarSpikeRelation;
  other: TRadarSpikeObject | undefined;
  direction: "outgoing" | "incoming";
};

function RelationRow({ relation, other, direction }: RelationRowProps) {
  return (
    <li className="flex items-center gap-2 text-13">
      <span className="text-tertiary">{direction === "outgoing" ? "→" : "←"}</span>
      <code className="rounded-sm bg-layer-1 px-1.5 py-0.5 text-11 text-secondary">{relation.type}</code>
      <span className="text-tertiary">{other ? getRadarSpikeTypeLabel(other.type) : "Unknown"}:</span>
      <span className="font-medium text-primary">{other?.title ?? relation.targetId}</span>
    </li>
  );
}

/**
 * Visual mock of a RADAR object page. Outgoing relations and backlinks are derived from the same
 * hardcoded relation list, which is all the domain logic this page has.
 */
export const RadarSpikeMockObjectPage = observer(function RadarSpikeMockObjectPage() {
  const { data: currentUser } = useUser();
  const object = getObject(OBJECT_ID);
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [date, setDate] = useState<Date | null>(new Date(2026, 9, 1));

  if (!object) return null;

  const outgoing = RADAR_SPIKE_RELATIONS.filter((relation) => relation.sourceId === object.id);
  const backlinks = RADAR_SPIKE_RELATIONS.filter((relation) => relation.targetId === object.id);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-2">
        <span className="text-12 font-medium tracking-wide text-tertiary uppercase">
          {getRadarSpikeTypeLabel(object.type)}
        </span>
        <h1 className="text-24 font-semibold text-primary">{object.title}</h1>
      </header>

      <section className="grid grid-cols-[120px_1fr] items-center gap-x-4 gap-y-3 text-13">
        <span className="text-secondary">Status</span>
        <div>
          <Badge variant="success" size="sm" label="Approved" />
        </div>
        <span className="text-secondary">Owner</span>
        <div className="w-64">
          <MemberSelect
            variant="select-ghost-md"
            value={ownerId ?? currentUser?.id}
            onChange={setOwnerId}
            placeholder="Owner"
          />
        </div>
        <span className="text-secondary">Date</span>
        <div className="w-64">
          <DateSelect variant="select-ghost-md" value={date} onChange={setDate} placeholder="Date" />
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-14 font-semibold text-primary">Context</h2>
        <RadarSpikeNotesEditor id={`radar-spike-${object.id}-context`} initialValue={INITIAL_CONTEXT} />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-14 font-semibold text-primary">Relations</h2>
        <ul className="flex flex-col gap-1.5">
          {outgoing.map((relation) => (
            <RelationRow
              key={relation.id}
              relation={relation}
              other={getObject(relation.targetId)}
              direction="outgoing"
            />
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-14 font-semibold text-primary">Backlinks</h2>
        <ul className="flex flex-col gap-1.5">
          {backlinks.map((relation) => (
            <RelationRow
              key={relation.id}
              relation={relation}
              other={getObject(relation.sourceId)}
              direction="incoming"
            />
          ))}
        </ul>
      </section>

      <p className="text-11 text-tertiary">
        Mock page for the Phase 0 shell spike. Properties, relations and backlinks are hardcoded; nothing is saved.
      </p>
    </div>
  );
});
