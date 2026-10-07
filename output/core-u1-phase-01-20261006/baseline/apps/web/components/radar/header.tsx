/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { RadarIcon } from "lucide-react";
import { useParams } from "next/navigation";
import { Breadcrumbs } from "@plane/blocks/breadcrumb";
import { Header } from "@plane/blocks/layout";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";

type TRadarCrumb = {
  label: string;
  href?: string;
};

type Props = {
  crumbs?: TRadarCrumb[];
};

export function RadarHeader({ crumbs = [] }: Props) {
  const { workspaceSlug } = useParams();

  return (
    <Header>
      <Header.LeftItem>
        <Breadcrumbs>
          <Breadcrumbs.Item
            component={
              <BreadcrumbLink
                label="RADAR"
                href={`/${workspaceSlug}/radar/`}
                icon={<RadarIcon className="size-4 text-secondary" />}
                isLast={crumbs.length === 0}
              />
            }
          />
          {crumbs.map((crumb, index) => (
            <Breadcrumbs.Item
              key={crumb.label}
              component={<BreadcrumbLink label={crumb.label} href={crumb.href} isLast={index === crumbs.length - 1} />}
            />
          ))}
        </Breadcrumbs>
      </Header.LeftItem>
    </Header>
  );
}
