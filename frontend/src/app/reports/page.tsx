import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";

export const metadata: Metadata = { title: "Reports" };

export default function Page() {
  return <ComingSoon title="Reports" description="Weekly summaries to share." />;
}
