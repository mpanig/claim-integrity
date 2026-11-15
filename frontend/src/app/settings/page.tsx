import type { Metadata } from "next";
import { ComingSoon } from "@/components/coming-soon";

export const metadata: Metadata = { title: "Settings" };

export default function Page() {
  return <ComingSoon title="Settings" description="Team members, roles and notifications." />;
}
