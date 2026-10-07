/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useParams, usePathname } from "next/navigation";

/**
 * Custom hook to detect different workspace paths
 * @returns Object containing boolean flags for different workspace paths
 */
export const useWorkspacePaths = () => {
  const { workspaceSlug } = useParams();
  const pathname = usePathname();

  const isSettingsPath = pathname.includes(`/${workspaceSlug}/settings`);
  const isWikiPath = pathname.includes(`/${workspaceSlug}/wiki`);
  const isAiPath = pathname.includes(`/${workspaceSlug}/pi-chat`);
  const isRadarPath = pathname.includes(`/${workspaceSlug}/radar`);
  const isProjectsPath =
    pathname.includes(`/${workspaceSlug}/`) && !isWikiPath && !isAiPath && !isRadarPath && !isSettingsPath;
  const isNotificationsPath = pathname.includes(`/${workspaceSlug}/notifications`);

  return {
    isSettingsPath,
    isWikiPath,
    isAiPath,
    isRadarPath,
    isProjectsPath,
    isNotificationsPath,
  };
};
