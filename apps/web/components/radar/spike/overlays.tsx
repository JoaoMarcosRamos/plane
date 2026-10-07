/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import {
  Drawer,
  DrawerBody,
  DrawerClose,
  DrawerHeader,
  DrawerHeaderActions,
  DrawerHeaderContent,
  DrawerPanel,
  DrawerTitle,
} from "@makeplane/propel/components/drawer";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { InputField } from "@makeplane/propel/components/input-field";
import { CloseOutline } from "@makeplane/propel/icons";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
// local imports
import type { TRadarSpikeObject, TRadarSpikeObjectType } from "./mock-data";
import { RADAR_SPIKE_TYPES, getRadarSpikeStatusLabel, getRadarSpikeTypeLabel } from "./mock-data";

type TTypeOption = (typeof RADAR_SPIKE_TYPES)[number];

type CreateObjectDialogProps = {
  isOpen: boolean;
  onClose: () => void;
};

/** Fake "Create Object" form: nothing is persisted, submit only raises a toast. */
export function RadarSpikeCreateObjectDialog({ isOpen, onClose }: CreateObjectDialogProps) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState<TRadarSpikeObjectType>("decision");
  const selectedType = RADAR_SPIKE_TYPES.find((option) => option.key === type) ?? null;

  const handleClose = () => {
    setTitle("");
    setType("decision");
    onClose();
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setToast({
      type: "info",
      title: "Not persisted",
      message: `${getRadarSpikeTypeLabel(type)} "${title || "Untitled"}" exists only in this spike.`,
    });
    handleClose();
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>Create object</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-4">
                <InputField
                  id="radar-spike-object-title"
                  type="text"
                  size="xl"
                  orientation="vertical"
                  label="Title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Adotar GitHub Enterprise"
                />
                <div className="flex flex-col gap-1.5">
                  <span className="text-13 font-medium text-secondary">Type</span>
                  <Select<TTypeOption>
                    getValues={() => RADAR_SPIKE_TYPES}
                    value={selectedType}
                    onChange={(value) => {
                      const next = RADAR_SPIKE_TYPES.find((option) => option.key === value);
                      if (next) setType(next.key);
                    }}
                    getOptionValue={(option) => option.key}
                    getOptionLabel={(option) => option.label}
                    showSearch={false}
                    pinSelected={false}
                    placeholder="Select a type"
                  >
                    <Select.Trigger variant="select-md">
                      <span className="text-13">{selectedType?.label ?? "Select a type"}</span>
                    </Select.Trigger>
                  </Select>
                </div>
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" onClick={handleClose} label="Cancel" />
            <Button variant="primary" size="md" stretch="auto" type="submit" label="Create" />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type ObjectDrawerProps = {
  object: TRadarSpikeObject | undefined;
  onClose: () => void;
};

/** Read-only peek of a fake object, built from propel's Drawer primitive (no Plane peek-overview). */
export function RadarSpikeObjectDrawer({ object, onClose }: ObjectDrawerProps) {
  return (
    <Drawer
      open={!!object}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      modal
      swipeDirection="right"
    >
      <DrawerPanel variant="overlay" side="end" size="md" backdrop>
        <DrawerHeader>
          <DrawerHeaderContent>
            <DrawerTitle>{object?.title}</DrawerTitle>
          </DrawerHeaderContent>
          <DrawerHeaderActions side="end">
            <DrawerClose
              render={<IconButton variant="ghost" size="md" aria-label="Close" icon={<Icon icon={CloseOutline} />} />}
            />
          </DrawerHeaderActions>
        </DrawerHeader>
        <DrawerBody>
          {object && (
            <dl className="grid grid-cols-[120px_1fr] gap-y-3 text-13">
              <dt className="text-tertiary">Type</dt>
              <dd>{getRadarSpikeTypeLabel(object.type)}</dd>
              <dt className="text-tertiary">Status</dt>
              <dd>
                <Badge variant="neutral" size="sm" label={getRadarSpikeStatusLabel(object.status)} />
              </dd>
              <dt className="text-tertiary">Id</dt>
              <dd>
                <code className="text-11">{object.id}</code>
              </dd>
            </dl>
          )}
        </DrawerBody>
      </DrawerPanel>
    </Drawer>
  );
}
