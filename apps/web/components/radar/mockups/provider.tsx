/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";
import { RadarMockupStore } from "./mockup.store";

const RadarMockupContext = createContext<RadarMockupStore | null>(null);

export function RadarMockupProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => new RadarMockupStore());
  return <RadarMockupContext.Provider value={store}>{children}</RadarMockupContext.Provider>;
}

export function useRadarMockup() {
  const store = useContext(RadarMockupContext);
  if (!store) throw new Error("useRadarMockup must be used inside RadarMockupProvider");
  return store;
}
