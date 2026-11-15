import { CircleCheck } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { BarListChart } from "@/components/charts/bar-list-chart";
import { EmptyState, LoadingBlock } from "@/components/common";
import { OwnerTypeFilter } from "@/components/owner-type-filter";
import { PageHeader } from "@/components/page-header";
import { RecommendationCard } from "@/components/recommendation-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { brandParam, first, type SP } from "@/lib/params";
import type { Recommendations } from "@/lib/recommendations";

export const metadata: Metadata = { title: "Recommendations" };

export default function RecommendationsPage({ searchParams }: PageProps<"/recommendations">) {
  return (
    <>
      <PageHeader
        title="Recommendations"
        description="The actions that improve consistency the most, ranked by risk × page importance × ease. Create a task to put one on the fix board."
      />
      <Suspense fallback={<LoadingBlock rows={4} />}>
        <RecommendationList searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function RecommendationList({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const data = await serverGet<Recommendations>("/recommendations", { brand_id: brandParam(sp) });
  const ownerType = first(sp.owner_type);
  const todo = data.items.filter((r) => r.state === "todo");
  const shown = data.items.filter((r) => !ownerType || r.owner_type === ownerType);
  const counts = Object.entries(data.owner_types).map(([value, label]) => ({
    value,
    label,
    count: todo.filter((r) => r.owner_type === value).length,
  }));
  const best = Math.max(0, ...todo.map((r) => r.impact_points));
  const products = new Set(todo.map((r) => r.sku_id)).size;

  if (data.items.length === 0) {
    return (
      <EmptyState title="Nothing to recommend" icon={CircleCheck}>
        Every page matches its approved claims and every truth sheet is complete.
      </EmptyState>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="flex flex-col gap-4 lg:col-span-2">
        <OwnerTypeFilter options={counts} />
        {shown.length === 0 ? (
          <EmptyState title="No actions for this team">Choose another team, or Everyone.</EmptyState>
        ) : (
          shown.map((r, i) => <RecommendationCard key={r.key} r={r} rank={i + 1} />)
        )}
      </div>
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardDescription>Open actions</CardDescription>
            <CardTitle className="text-3xl">{todo.length}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Across {products} product{products === 1 ? "" : "s"}; the biggest single action adds{" "}
            <span className="font-medium text-foreground">+{best} points</span> to its product&apos;s score.{" "}
            {data.items.length - todo.length} already {data.items.length - todo.length === 1 ? "has a task" : "have tasks"}.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Who needs to act</CardTitle>
            <CardDescription>Open actions by team.</CardDescription>
          </CardHeader>
          <CardContent>
            <BarListChart
              data={counts.filter((c) => c.count > 0).map((c) => ({ label: c.label, value: c.count }))}
              valueName="Open actions"
              labelWidth={150}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>How ranking works</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
            <p>Priority = risk of each issue × how much the page matters × how easy the fix is.</p>
            <p>“+pts” is how much the product&apos;s consistency score rises once the action is done.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
