export default function Loading() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading" className="flex flex-col gap-2" data-state="loading">
      <div className="h-6 w-48 animate-pulse rounded-sm bg-muted" />
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="h-8 animate-pulse rounded-sm bg-muted/70" />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
