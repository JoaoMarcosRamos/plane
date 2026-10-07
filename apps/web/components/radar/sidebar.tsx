/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { CalendarOutline, CubeOutline, SandboxOutline, WarningTriangleOutline } from "@makeplane/propel/icons";
import { SIDEBAR_WIDTH } from "@plane/constants";
import { useLocalStorage } from "@plane/hooks";
// components
import { ResizableSidebar } from "@/components/sidebar/resizable-sidebar";
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
import { SidebarWrapper } from "@/components/sidebar/sidebar-wrapper";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
// local imports
import type { TRadarSectionKey } from "./sections";
import { useRadarStore } from "@/store/radar/provider";
import { RADAR_SECTIONS, radarTypeSection } from "./sections";

const SECTION_ICONS: Record<TRadarSectionKey, ReactNode> = {
  today: <CalendarOutline className="size-4" />,
  objects: <CubeOutline className="size-4" />,
  "risk-review": <WarningTriangleOutline className="size-4" />,
  "agent-config": <SandboxOutline className="size-4" />,
};

type NavLinkProps = {
  href: string;
  label: string;
  icon: ReactNode;
};

const RadarSidebarLink = observer(function RadarSidebarLink({ href, label, icon }: NavLinkProps) {
  const pathname = usePathname();
  const { toggleSidebar } = useAppTheme();

  return (
    <Link
      href={href}
      onClick={() => {
        if (window.innerWidth < 768) toggleSidebar();
      }}
    >
      <SidebarNavItem isActive={pathname.startsWith(href)}>
        <div className="flex items-center gap-1.5 py-[1px]">
          {icon}
          <p className="text-13 leading-5 font-medium">{label}</p>
        </div>
      </SidebarNavItem>
    </Link>
  );
});

/**
 * RADAR app sidebar. Reuses the shell's resizable sidebar, `SidebarWrapper` and nav item styling, and
 * the theme store's collapse/peek state; it reads nothing from project or work item stores.
 */
export const RadarAppSidebar = observer(function RadarAppSidebar() {
  const { workspaceSlug } = useParams();
  const store = useRadarStore();
  const { sidebarCollapsed, toggleSidebar, sidebarPeek, toggleSidebarPeek, isAnySidebarDropdownOpen } = useAppTheme();
  const { storedValue, setValue } = useLocalStorage("sidebarWidth", SIDEBAR_WIDTH);
  const [sidebarWidth, setSidebarWidth] = useState<number>(storedValue ?? SIDEBAR_WIDTH);

  const radarBasePath = `/${workspaceSlug}/radar`;

  return (
    <ResizableSidebar
      showPeek={sidebarPeek}
      defaultWidth={storedValue ?? 250}
      width={sidebarWidth}
      setWidth={setSidebarWidth}
      defaultCollapsed={sidebarCollapsed}
      peekDuration={1500}
      onWidthChange={setValue}
      onCollapsedChange={toggleSidebar}
      isCollapsed={sidebarCollapsed}
      toggleCollapsed={toggleSidebar}
      togglePeek={toggleSidebarPeek}
      isAnySidebarDropdownOpen={isAnySidebarDropdownOpen}
    >
      <SidebarWrapper title="RADAR">
        <nav className="flex flex-col gap-0.5" aria-label="RADAR">
          {RADAR_SECTIONS.map((section) => (
            <RadarSidebarLink
              key={section.key}
              href={`${radarBasePath}/${section.key}/`}
              label={section.label}
              icon={SECTION_ICONS[section.key]}
            />
          ))}
        </nav>
        <div className="mx-2 border-t border-subtle" />
        <nav className="flex flex-col gap-0.5" aria-label="Object types">
          {store.objectTypes.map((type) => (
            <RadarSidebarLink
              key={type.id}
              href={`${radarBasePath}/${radarTypeSection(type.key)}/`}
              label={type.name}
              icon={<CubeOutline className="size-4" />}
            />
          ))}
        </nav>
        <nav className="flex flex-col gap-0.5" aria-label="RADAR spike">
          <RadarSidebarLink
            href={`${radarBasePath}/spike/`}
            label="Spike Components"
            icon={<SandboxOutline className="size-4" />}
          />
        </nav>
      </SidebarWrapper>
    </ResizableSidebar>
  );
});
