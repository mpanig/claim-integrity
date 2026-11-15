import { Hammer } from "lucide-react";
import { EmptyState } from "@/components/common";
import { PageHeader } from "@/components/page-header";

export function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <EmptyState title="Not built yet" icon={Hammer}>
        This screen is planned and will be added in a later step.
      </EmptyState>
    </>
  );
}
