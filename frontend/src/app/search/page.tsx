import { Package, Search as SearchIcon, Store } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";
import { CarryLink, ConflictLink, EmptyState, LoadingBlock } from "@/components/common";
import { PageHeader } from "@/components/page-header";
import { SearchBox } from "@/components/search-box";
import { SeverityBadge, StatusBadge, VerdictBadge } from "@/components/status";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { serverGet } from "@/lib/api";
import { FIELD_LABEL, snippet, SOURCE_TYPE_LABEL } from "@/lib/labels";
import { first, type SP } from "@/lib/params";
import type { Conflict } from "@/lib/types";

export const metadata: Metadata = { title: "Search" };

interface Results {
  products: { id: number; name: string; brand_name: string; gtin: string | null }[];
  pages: { id: number; label: string; url: string; source_type: string; sku_ids: number[] }[];
  conflicts: Conflict[];
}

export default function SearchPage({ searchParams }: PageProps<"/search">) {
  return (
    <>
      <PageHeader title="Search" description="Products, pages and issues across every brand." />
      <Suspense fallback={null}>
        <SearchBox placeholder="Search products, pages, issues" />
      </Suspense>
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <SearchResults searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function SearchResults({ searchParams }: { searchParams: Promise<SP> }) {
  const q = (first((await searchParams).q) ?? "").trim();
  if (q.length < 2)
    return (
      <EmptyState title="Type at least two characters" icon={SearchIcon}>
        Try a product name, a retailer such as “Hannaford”, or a claim such as “paraben”.
      </EmptyState>
    );
  const r = await serverGet<Results>("/search", { q });
  if (!r.products.length && !r.pages.length && !r.conflicts.length)
    return <EmptyState title={`Nothing matches “${q}”`} icon={SearchIcon} />;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Package className="size-4 text-muted-foreground" /> Products ({r.products.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {r.products.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products.</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {r.products.map((p) => (
                <li key={p.id} className="py-2">
                  <CarryLink href={`/products/${p.id}`} className="text-sm font-medium hover:underline">
                    {p.name}
                  </CarryLink>
                  <div className="text-xs text-muted-foreground">
                    {p.brand_name}
                    {p.gtin && ` · GTIN ${p.gtin}`}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Store className="size-4 text-muted-foreground" /> Pages ({r.pages.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {r.pages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pages.</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {r.pages.map((p) => (
                <li key={p.id} className="py-2">
                  {p.sku_ids[0] ? (
                    <CarryLink href={`/products/${p.sku_ids[0]}`} className="text-sm font-medium hover:underline">
                      {p.label}
                    </CarryLink>
                  ) : (
                    <span className="text-sm font-medium">{p.label}</span>
                  )}
                  <div className="truncate text-xs text-muted-foreground">
                    {SOURCE_TYPE_LABEL[p.source_type] ?? p.source_type} · {p.url}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Issues ({r.conflicts.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {r.conflicts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No issues.</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {r.conflicts.map((c) => (
                <li key={c.id}>
                  <ConflictLink id={c.id} className="flex w-full flex-wrap items-center gap-2 py-2 hover:bg-muted/40">
                    <VerdictBadge verdict={c.verdict} />
                    <span className="min-w-0 flex-1 text-sm">
                      <span className="font-medium">
                        {FIELD_LABEL[c.field]} on {c.page_label}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {snippet(c)} · {c.sku_name}
                      </span>
                    </span>
                    <SeverityBadge severity={c.severity} />
                    <StatusBadge status={c.status} />
                  </ConflictLink>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
