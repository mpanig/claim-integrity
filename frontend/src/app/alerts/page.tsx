import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";

export const metadata: Metadata = { title: "Alerts" };

export default function Page() {
  return <ComingSoon title="Alerts" description="New high-risk issues and score drops." />;
}
