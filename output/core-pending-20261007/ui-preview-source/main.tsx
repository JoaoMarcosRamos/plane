import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, useParams } from "react-router";
import { RadarObjectPage } from "../../../apps/web/components/radar/object-page";
import { RadarObjectsList } from "../../../apps/web/components/radar/objects-list";
import { RadarHome } from "../../../apps/web/components/radar/home";
import { RadarStoreProvider } from "../../../apps/web/store/radar/provider";
import { radarTypeKey } from "../../../apps/web/components/radar/sections";
import "../../../apps/web/styles/globals.css";
function ObjectFixture() { const { objectId } = useParams(); return <RadarObjectPage objectId={objectId!} />; }
function ListFixture() { const { section } = useParams(); return <RadarObjectsList key={section} typeKey={radarTypeKey(section!)} />; }
createRoot(document.getElementById("root")!).render(
  <BrowserRouter><RadarStoreProvider workspaceSlug={window.location.pathname.split("/")[1]}>
    <Routes><Route path="/:slug/radar/:section" element={<ListFixture />} />
      <Route path="/:slug/radar/" element={<RadarHome />} />
      <Route path="/:slug/radar/objects/:objectId" element={<ObjectFixture />} /></Routes>
  </RadarStoreProvider></BrowserRouter>
);
