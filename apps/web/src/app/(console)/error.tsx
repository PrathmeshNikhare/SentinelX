"use client";

import { Button } from "@/components/ui/button";

export default function ConsoleError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-4 text-red-900" data-state="error">
      <p className="font-medium">This view failed to load.</p>
      <p className="mt-1">
        An unexpected error occurred.
        {error.digest ? (
          <>
            {" "}
            Reference: <code>{error.digest}</code>
          </>
        ) : null}
      </p>
      <Button className="mt-3" variant="outline" size="sm" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
