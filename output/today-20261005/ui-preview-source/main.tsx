import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, useParams } from "react-router";
import { RadarToday } from "../../../apps/web/components/radar/today";
import { RadarRiskReview } from "../../../apps/web/components/radar/risk-review";
import { RadarObjectPage } from "../../../apps/web/components/radar/object-page";
import { RadarStoreProvider } from "../../../apps/web/store/radar/provider";
import "../../../apps/web/styles/globals.css";
function ObjectFixture() { const { objectId } = useParams(); return <RadarObjectPage objectId={objectId!} />; }
createRoot(document.getElementById("root")!).render(<BrowserRouter><RadarStoreProvider workspaceSlug={window.location.pathname.split("/")[1]}><Routes><Route path="/:slug/radar/objects/:objectId" element={<ObjectFixture />} /><Route path="/:slug/radar/risk-review" element={<RadarRiskReview />} /><Route path="*" element={<RadarToday />} /></Routes></RadarStoreProvider></BrowserRouter>);
