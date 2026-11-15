import { Suspense } from "react";
import { serverGet } from "@/lib/api";
import type { Brand } from "@/lib/types";
import { BrandSwitcher, RangePicker } from "./filters";
import { GlobalSearch } from "./global-search";

async function BrandSwitcherLoader() {
  let brands: Brand[] = [];
  try {
    brands = await serverGet<Brand[]>("/brands");
  } catch {
    // The page body shows the connection error; keep the switcher usable.
  }
  return <BrandSwitcher brands={brands} />;
}

export function Topbar() {
  return (
    <>
      <Suspense fallback={<div className="h-8 w-40 rounded-lg border" />}>
        <BrandSwitcherLoader />
      </Suspense>
      <Suspense fallback={<div className="hidden h-8 w-44 rounded-lg border sm:block" />}>
        <RangePicker />
      </Suspense>
      <Suspense fallback={null}>
        <GlobalSearch />
      </Suspense>
    </>
  );
}
