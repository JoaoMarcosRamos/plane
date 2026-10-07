// Rich text editing belongs to Plane's editor; the fixture keeps the persisted HTML visible.
export function RadarNotesEditor({ initialValue }: { initialValue?: string }) {
  return <div data-testid="notes-stub" dangerouslySetInnerHTML={{ __html: initialValue ?? "" }} />;
}
