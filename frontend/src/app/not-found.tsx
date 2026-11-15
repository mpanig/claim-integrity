import Link from "next/link";
import { EmptyState } from "@/components/common";

export default function NotFound() {
  return (
    <EmptyState title="Page not found" action={<Link href="/" className="text-sm underline underline-offset-4">Go to the overview</Link>}>
      That product or page doesn&apos;t exist, or it was removed.
    </EmptyState>
  );
}
