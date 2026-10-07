/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Button } from "@makeplane/propel/components/button";
import { Tab, Tabs, TabsList } from "@makeplane/propel/components/tabs";
import { DateSelect } from "@plane/blocks/property-select";
import { setToast } from "@plane/blocks/toast";
import { renderFormattedPayloadDate } from "@plane/utils";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// local imports
import { RadarSpikeGenericKanban, RadarSpikeGenericList } from "./generic-layouts";
import type { TRadarSpikeObject, TRadarSpikeStatus } from "./mock-data";
import { RADAR_SPIKE_OBJECTS } from "./mock-data";
import { RadarSpikeNotesEditor } from "./notes-editor";
import { RadarSpikeCreateObjectDialog, RadarSpikeObjectDrawer } from "./overlays";
import { RadarSpikeSection } from "./section";

type TLayoutTab = "list" | "kanban";

const MAX_LOGGED_EVENTS = 8;

/**
 * Phase 0 component playground. Every block below mounts a Plane component against fake RADAR data,
 * with no project, work item or persistence involved.
 */
export function RadarSpikePlayground() {
  const { workspaceSlug } = useParams();
  // fake objects (local only)
  const [objects, setObjects] = useState<TRadarSpikeObject[]>(RADAR_SPIKE_OBJECTS);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerObjectId, setDrawerObjectId] = useState<string | null>(null);
  const [layoutTab, setLayoutTab] = useState<TLayoutTab>("list");
  const [events, setEvents] = useState<{ id: number; message: string }[]>([]);
  const eventCounter = useRef(0);
  // fake fields
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [dueDate, setDueDate] = useState<Date | null>(new Date(2026, 9, 1));
  const [notesHtml, setNotesHtml] = useState("<p></p>");
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const logEvent = useCallback((message: string) => {
    eventCounter.current += 1;
    const event = { id: eventCounter.current, message };
    setEvents((prev) => [event, ...prev].slice(0, MAX_LOGGED_EVENTS));
  }, []);

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      logEvent(`select(${id})`);
    },
    [logEvent]
  );

  const handleOpen = useCallback(
    (id: string) => {
      setDrawerObjectId(id);
      logEvent(`open(${id})`);
    },
    [logEvent]
  );

  const handleStatusChange = useCallback((id: string, status: TRadarSpikeStatus) => {
    setObjects((prev) => prev.map((object) => (object.id === id ? { ...object, status } : object)));
  }, []);

  const sharedLayoutProps = {
    objects,
    selectedId,
    onSelect: handleSelect,
    onOpen: handleOpen,
    onEvent: logEvent,
  };

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-18 font-semibold text-primary">Spike Components</h1>
        <p className="text-13 text-secondary">
          Plane components mounted against fake RADAR data. Nothing here is persisted and no Plane project is involved.{" "}
          <Link href={`/${workspaceSlug}/radar/spike/object/`} className="text-accent-primary underline">
            Open the mock object page
          </Link>
        </p>
      </div>

      <RadarSpikeSection title="Generic List / Kanban" source="components/base-layouts/{list,kanban}">
        <Tabs variant="underline" value={layoutTab} onValueChange={(value) => setLayoutTab(value as TLayoutTab)}>
          <TabsList>
            <Tab value="list" label="List (grouped by type)" />
            <Tab value="kanban" label="Kanban (grouped by status)" />
          </TabsList>
        </Tabs>
        {layoutTab === "list" ? (
          <RadarSpikeGenericList {...sharedLayoutProps} />
        ) : (
          <RadarSpikeGenericKanban {...sharedLayoutProps} onStatusChange={handleStatusChange} />
        )}
        <p className="text-11 text-tertiary">
          Click selects, double-click opens the drawer, group headers collapse, kanban cards drag across columns.
        </p>
        <div className="rounded-md bg-layer-1 p-3">
          <div className="text-11 font-medium text-secondary">
            Callback log · selected: <code>{selectedId ?? "none"}</code>
          </div>
          <ul className="font-mono mt-1 flex flex-col gap-0.5 text-11 text-tertiary" data-testid="radar-spike-events">
            {events.length === 0 ? (
              <li>(no events yet)</li>
            ) : (
              events.map((event) => <li key={event.id}>{event.message}</li>)
            )}
          </ul>
        </div>
      </RadarSpikeSection>

      <RadarSpikeSection title="Rich Text (no project)" source="components/editor/rich-text">
        <RadarSpikeNotesEditor id="radar-spike-notes" onChange={setNotesHtml} />
        <p className="text-11 text-tertiary">
          Local state only · {notesHtml.length} chars of HTML · uploads disabled · non-collaborative
        </p>
      </RadarSpikeSection>

      <RadarSpikeSection title="Fields" source="components/dropdowns/member · @plane/blocks/property-select">
        <div className="grid grid-cols-[120px_1fr] items-center gap-3 text-13">
          <span className="text-secondary">Owner</span>
          <div className="w-64">
            <MemberSelect
              variant="select-md"
              value={ownerId}
              onChange={(id) => {
                setOwnerId(id);
                logEvent(`owner(${id})`);
              }}
              placeholder="Workspace member"
              clearable
            />
          </div>
          <span className="text-secondary">Date</span>
          <div className="w-64">
            <DateSelect
              variant="select-md"
              value={dueDate}
              onChange={(date) => {
                setDueDate(date);
                logEvent(`date(${date ? renderFormattedPayloadDate(date) : "null"})`);
              }}
              placeholder="Pick a date"
              clearable
            />
          </div>
        </div>
      </RadarSpikeSection>

      <RadarSpikeSection title="Modal / Drawer / Toast" source="@makeplane/propel · @plane/blocks/toast">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label="Create Object"
            onClick={() => setIsCreateOpen(true)}
          />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label="Open object in drawer"
            onClick={() => handleOpen(selectedId ?? objects[0].id)}
          />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label="Success toast"
            onClick={() => setToast({ type: "success", title: "RADAR", message: "Toast raised from the RADAR app." })}
          />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label="Error toast"
            onClick={() => setToast({ type: "error", title: "RADAR", message: "Simulated failure." })}
          />
        </div>
      </RadarSpikeSection>

      <RadarSpikeCreateObjectDialog isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
      <RadarSpikeObjectDrawer
        object={objects.find((object) => object.id === drawerObjectId)}
        onClose={() => setDrawerObjectId(null)}
      />
    </div>
  );
}
