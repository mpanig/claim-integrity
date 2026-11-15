import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";

export const metadata: Metadata = { title: "Competitors" };

export default function Page() {
  return <ComingSoon title="Competitors" description="Compare how consistently each brand is described." />;
}
