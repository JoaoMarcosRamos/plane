import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useParams } from "react-router";
import { TranslationProvider } from "@plane/i18n";
import { PlaneToastProvider } from "@plane/blocks/toast";
import { RadarMockupShell } from "../../../apps/web/components/radar/mockups/shell";
import { RadarMockupScreen } from "../../../apps/web/components/radar/mockups/screens";
// oxlint-disable-next-line import/no-unassigned-import -- global styles are a side-effect import
import "../../../apps/web/styles/globals.css";

function Screen() {
  const { screen, projectId } = useParams();
  return <RadarMockupScreen screen={screen} projectId={projectId} />;
}

function Frame() {
  return (
    <div className="h-screen w-screen bg-surface-2 p-2">
      <RadarMockupShell>
        <Outlet />
      </RadarMockupShell>
    </div>
  );
}

// Plane's own components translate through @plane/i18n; in the app this follows the profile language.
localStorage.setItem("userLanguage", "pt-BR");

createRoot(document.getElementById("root")!).render(
  <TranslationProvider>
    <PlaneToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/radar-piloto/radar/mockups/hoje/" replace />} />
          <Route path="/:workspaceSlug/radar/mockups" element={<Frame />}>
            <Route index element={<Screen />} />
            <Route path="projetos/:projectId" element={<Screen />} />
            <Route path=":screen" element={<Screen />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </PlaneToastProvider>
  </TranslationProvider>
);
