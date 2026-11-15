"use client";

import { PlugZap } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const offline = /fetch failed|ECONNREFUSED|Failed to fetch/i.test(error.message);
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center">
      <PlugZap className="size-6 text-muted-foreground" />
      <h1 className="font-medium">{offline ? "Can't reach the Claim Integrity service" : "Something went wrong"}</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        {offline
          ? "The backend API isn't responding. Start it with `uv run uvicorn app.main:app` in the backend folder, then try again."
          : error.message}
      </p>
      <Button variant="outline" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
