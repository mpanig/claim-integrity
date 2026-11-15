import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";

export const metadata: Metadata = { title: "Recommendations" };

export default function Page() {
  return <ComingSoon title="Recommendations" description="Ranked actions that improve consistency the most." />;
}
