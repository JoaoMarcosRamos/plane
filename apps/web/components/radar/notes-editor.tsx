/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// components
import { RichTextEditor } from "@/components/editor/rich-text";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
// services
import { WorkspaceService } from "@/services/workspace.service";

const workspaceService = new WorkspaceService();

// Uploads are out of scope for the Core slice; the image extension is disabled below, so these only
// guard against a paste/drop path that still reaches the handler.
const rejectFileOperation = async (): Promise<string> => {
  throw new Error("File uploads are not part of the RADAR Core slice.");
};

type Props = {
  id: string;
  initialValue?: string;
  placeholder?: string;
  onChange?: (html: string) => void;
  editable?: boolean;
};

/**
 * Plane's non-collaborative rich text editor, mounted without a project: mentions search the workspace
 * roster and HTML is saved by the Object command through the caller.
 */
export const RadarNotesEditor = observer(function RadarNotesEditor(props: Props) {
  const { id, initialValue = "<p></p>", placeholder, onChange, editable = true } = props;
  const { workspaceSlug } = useParams();
  const { currentWorkspace } = useWorkspace();

  if (!workspaceSlug || !currentWorkspace) return null;

  return (
    <RichTextEditor
      id={id}
      editable={editable}
      initialValue={initialValue}
      workspaceSlug={workspaceSlug.toString()}
      workspaceId={currentWorkspace.id}
      disabledExtensions={["image"]}
      dragDropEnabled={editable}
      placeholder={placeholder ?? "Write here. Select text to format, type / for blocks, @ to mention a member."}
      onChange={(_json, html) => onChange?.(html)}
      searchMentionCallback={async (payload) => await workspaceService.searchEntity(workspaceSlug.toString(), payload)}
      uploadFile={rejectFileOperation}
      duplicateFile={rejectFileOperation}
      containerClassName="min-h-[140px] rounded-md border border-subtle px-1 pt-2"
    />
  );
});
