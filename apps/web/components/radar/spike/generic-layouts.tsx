/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import { Badge } from "@makeplane/propel/components/badge";
import type { IBaseLayoutsBaseGroup } from "@plane/types";
import { cn } from "@plane/utils";
// components
import { BaseKanbanLayout } from "@/components/base-layouts/kanban/layout";
import { BaseListLayout } from "@/components/base-layouts/list/layout";
// local imports
import type { TRadarSpikeObject, TRadarSpikeStatus } from "./mock-data";
import {
  RADAR_SPIKE_STATUSES,
  RADAR_SPIKE_TYPES,
  getRadarSpikeStatusLabel,
  getRadarSpikeTypeLabel,
  groupRadarSpikeObjectIds,
} from "./mock-data";

const TYPE_GROUPS: IBaseLayoutsBaseGroup[] = RADAR_SPIKE_TYPES.map(({ key, label }) => ({ id: key, name: label }));
const STATUS_GROUPS: IBaseLayoutsBaseGroup[] = RADAR_SPIKE_STATUSES.map(({ key, label }) => ({ id: key, name: label }));

type SharedProps = {
  objects: TRadarSpikeObject[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onEvent: (message: string) => void;
};

type ObjectRowProps = {
  object: TRadarSpikeObject;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  variant: "row" | "card";
};

function RadarSpikeObjectItem({ object, isSelected, onSelect, onOpen, variant }: ObjectRowProps) {
  return (
    <button
      type="button"
      aria-pressed={isSelected}
      onClick={() => onSelect(object.id)}
      onDoubleClick={() => onOpen(object.id)}
      className={cn("flex w-full items-center justify-between gap-3 text-left text-13", {
        "border-b border-subtle px-6 py-2 hover:bg-layer-1-hover": variant === "row",
        "rounded-md border border-subtle bg-layer-2 p-3 shadow-raised-100 hover:bg-layer-2-hover": variant === "card",
        "bg-layer-transparent-selected": isSelected,
      })}
    >
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate font-medium text-primary">{object.title}</span>
        <span className="text-11 text-tertiary">{getRadarSpikeTypeLabel(object.type)}</span>
      </div>
      <Badge
        variant={object.status === "done" ? "success" : "neutral"}
        size="sm"
        label={getRadarSpikeStatusLabel(object.status)}
      />
    </button>
  );
}

/** Collapse state owned by the caller (the layouts' "external" mode) so toggles show up in the event log. */
const useLoggedCollapsedGroups = (layout: "list" | "kanban", onEvent: (message: string) => void) => {
  const [collapsedGroups, setCollapsedGroups] = useState<string[]>([]);
  const onToggleGroup = useCallback(
    (groupId: string) => {
      setCollapsedGroups((prev) => (prev.includes(groupId) ? prev.filter((id) => id !== groupId) : [...prev, groupId]));
      onEvent(`${layout}.onToggleGroup(${groupId})`);
    },
    [layout, onEvent]
  );
  return { collapsedGroups, onToggleGroup };
};

/** Plane's generic list layout, grouped by object type. */
export function RadarSpikeGenericList({ objects, selectedId, onSelect, onOpen, onEvent }: SharedProps) {
  const { collapsedGroups, onToggleGroup } = useLoggedCollapsedGroups("list", onEvent);
  const objectsById = useMemo(() => Object.fromEntries(objects.map((object) => [object.id, object])), [objects]);
  const groupedItemIds = useMemo(
    () =>
      groupRadarSpikeObjectIds(
        objects,
        "type",
        RADAR_SPIKE_TYPES.map(({ key }) => key)
      ),
    [objects]
  );

  return (
    <div className="h-80 overflow-hidden rounded-md border border-subtle">
      <BaseListLayout
        items={objectsById}
        groups={TYPE_GROUPS}
        groupedItemIds={groupedItemIds}
        collapsedGroups={collapsedGroups}
        onToggleGroup={onToggleGroup}
        renderItem={(item) => (
          <RadarSpikeObjectItem
            object={objectsById[item.id]}
            isSelected={selectedId === item.id}
            onSelect={onSelect}
            onOpen={onOpen}
            variant="row"
          />
        )}
      />
    </div>
  );
}

type KanbanProps = SharedProps & {
  onStatusChange: (id: string, status: TRadarSpikeStatus) => void;
};

/** Plane's generic kanban layout, grouped by a fake status, with cross-column drag and drop. */
export function RadarSpikeGenericKanban({
  objects,
  selectedId,
  onSelect,
  onOpen,
  onEvent,
  onStatusChange,
}: KanbanProps) {
  const { collapsedGroups, onToggleGroup } = useLoggedCollapsedGroups("kanban", onEvent);
  const objectsById = useMemo(() => Object.fromEntries(objects.map((object) => [object.id, object])), [objects]);
  const groupedItemIds = useMemo(
    () =>
      groupRadarSpikeObjectIds(
        objects,
        "status",
        RADAR_SPIKE_STATUSES.map(({ key }) => key)
      ),
    [objects]
  );

  const handleDrop = useCallback(
    async (sourceId: string, destinationId: string | null, sourceGroupId: string, destinationGroupId: string) => {
      onEvent(`kanban.onDrop(${sourceId}, ${destinationId}, ${sourceGroupId} → ${destinationGroupId})`);
      const status = RADAR_SPIKE_STATUSES.find(({ key }) => key === destinationGroupId)?.key;
      if (status) onStatusChange(sourceId, status);
    },
    [onEvent, onStatusChange]
  );

  return (
    <div className="h-96 overflow-hidden rounded-md border border-subtle">
      <BaseKanbanLayout
        items={objectsById}
        groups={STATUS_GROUPS}
        groupedItemIds={groupedItemIds}
        enableDragDrop
        onDrop={handleDrop}
        collapsedGroups={collapsedGroups}
        onToggleGroup={onToggleGroup}
        groupClassName="w-[280px]"
        renderItem={(item) => (
          <RadarSpikeObjectItem
            object={objectsById[item.id]}
            isSelected={selectedId === item.id}
            onSelect={onSelect}
            onOpen={onOpen}
            variant="card"
          />
        )}
      />
    </div>
  );
}
