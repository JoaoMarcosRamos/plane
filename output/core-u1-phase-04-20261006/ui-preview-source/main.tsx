import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { observer } from "mobx-react";
import { BrowserRouter, Routes, Route, useParams } from "react-router";
import { RadarObjectPage } from "../../../apps/web/components/radar/object-page";
import { RadarCreateObjectDialog } from "../../../apps/web/components/radar/create-object-dialog";
import { RadarStoreProvider, useRadarStore } from "../../../apps/web/store/radar/provider";
import "../../../apps/web/styles/globals.css";

function ObjectFixture() {
  const { objectId } = useParams();
  return <RadarObjectPage objectId={objectId!} />;
}

// The production list layout needs Plane workspace stores; the dialog itself is the production component.
const CreateFixture = observer(function CreateFixture() {
  const store = useRadarStore();
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void Promise.all([store.loadTypes(), store.loadList()]).then(() => setReady(true));
  }, [store]);
  return (
    <div className="p-6">
      <button className="underline" disabled={!ready} onClick={() => setOpen(true)}>
        Create object
      </button>
      {open && <RadarCreateObjectDialog onClose={() => setOpen(false)} />}
    </div>
  );
});

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <RadarStoreProvider workspaceSlug={window.location.pathname.split("/")[1]}>
      <Routes>
        <Route path="/:slug/radar/create" element={<CreateFixture />} />
        <Route path="/:slug/radar/objects/:objectId" element={<ObjectFixture />} />
      </Routes>
    </RadarStoreProvider>
  </BrowserRouter>
);
