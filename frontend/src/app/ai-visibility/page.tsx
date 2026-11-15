import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";

export const metadata: Metadata = { title: "AI visibility" };

export default function Page() {
  return <ComingSoon title="AI visibility" description="What AI assistants say about your products." />;
}
