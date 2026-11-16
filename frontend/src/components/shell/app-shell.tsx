"use client";

import { ChevronRight, Menu, Moon, ShieldCheck, Sun } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUrlState } from "@/hooks/use-url-state";
import { cn } from "@/lib/utils";
import { AlertsBell } from "./alerts-bell";
import { NAV, type NavItem } from "./nav";

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

const OPEN_KEY = "nav-open:";

function readOpen(href: string): boolean | null {
  try {
    const v = localStorage.getItem(OPEN_KEY + href);
    return v === null ? null : v === "1";
  } catch {
    return null;
  }
}

/** A sidebar entry with subsections: expanded while one of them is active, otherwise as the user left it. */
function NavGroup({ item, pathname, carry, onNavigate }: { item: NavItem; pathname: string; carry: (href: string) => string; onNavigate?: () => void }) {
  const { href, label, icon: Icon, children = [] } = item;
  const inside = isActive(pathname, href);
  // null = follow the route; true/false = the user's choice (remembered).
  const [choice, setChoice] = useState<boolean | null>(null);
  // Server render has no storage; read it after mount so hydration matches.
  const [stored, setStored] = useState<boolean | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one read of browser storage after hydration
    setStored(readOpen(href));
  }, [href]);
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    // Entering the group from elsewhere always opens it.
    setLastPath(pathname);
    if (inside && !isActive(lastPath, href)) setChoice(null);
  }
  const open = choice ?? (inside || (stored ?? false));
  const id = `nav-${href.replaceAll("/", "")}`;
  const toggle = () => {
    const next = !open;
    setChoice(next);
    try {
      localStorage.setItem(OPEN_KEY + href, next ? "1" : "0");
    } catch {
      /* storage unavailable: still toggles for this visit */
    }
  };
  const childActive = (c: string) => (c === href ? pathname === href : isActive(pathname, c));
  return (
    <div className="flex flex-col gap-0.5">
      <div className={cn("flex h-8 items-center rounded-lg text-sm text-sidebar-foreground/80", inside && "font-medium text-sidebar-foreground")}>
        <Link
          href={carry(href)}
          onClick={onNavigate}
          className="flex h-full flex-1 items-center gap-2.5 rounded-lg px-2 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
        >
          <Icon className="size-4 shrink-0" />
          <span>{label}</span>
        </Link>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={id}
          aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
          className="flex size-8 items-center justify-center rounded-lg hover:bg-sidebar-accent"
        >
          <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
        </button>
      </div>
      {open && (
        <ul id={id} className="ml-4 flex flex-col gap-0.5 border-l pl-2">
          {children.map((c) => {
            const active = childActive(c.href);
            return (
              <li key={c.href}>
                <Link
                  href={carry(c.href)}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex h-7 items-center rounded-md px-2 text-[13px] text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground",
                    active && "bg-sidebar-accent font-medium text-sidebar-foreground",
                  )}
                >
                  {c.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function NavList({ compact, onNavigate }: { compact?: boolean; onNavigate?: () => void }) {
  const { pathname, carry } = useUrlState();
  return (
    <nav className="flex flex-col gap-5" aria-label="Main">
      {NAV.map((group) => (
        <div key={group.section} className="flex flex-col gap-0.5">
          <p className={cn("px-2 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase", compact && "sr-only")}>
            {group.section}
          </p>
          {group.items.map((item) => {
            const { href, label, icon: Icon } = item;
            const active = isActive(pathname, href);
            if (item.children && !compact)
              return <NavGroup key={href} item={item} pathname={pathname} carry={carry} onNavigate={onNavigate} />;
            const link = (
              <Link
                key={href}
                href={carry(href)}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-8 items-center gap-2.5 rounded-lg px-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground",
                  active && "bg-sidebar-accent font-medium text-sidebar-foreground",
                  compact && "justify-center px-0",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className={cn(compact && "sr-only")}>{label}</span>
              </Link>
            );
            return compact ? (
              <Tooltip key={href}>
                <TooltipTrigger render={<div />}>{link}</TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ) : (
              link
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function Logo({ compact }: { compact?: boolean }) {
  return (
    <Link href="/" className={cn("flex items-center gap-2 px-2 font-semibold tracking-tight", compact && "justify-center px-0")}>
      <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <ShieldCheck className="size-4" />
      </span>
      <span className={cn(compact && "sr-only")}>Claim Integrity</span>
    </Link>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  return (
    <Button variant="ghost" size="icon" aria-label="Switch light or dark mode" onClick={() => setTheme(dark ? "light" : "dark")}>
      <Sun className="hidden size-4 dark:block" />
      <Moon className="size-4 dark:hidden" />
    </Button>
  );
}

export function AppShell({
  children,
  topbar,
}: {
  children: React.ReactNode;
  /** Server-rendered controls for the top bar (brand switcher, date range, search, alerts). */
  topbar: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen bg-background">
      {/* Full sidebar on desktop, icon rail on tablet, sheet on phones. */}
      <aside className="no-print sticky top-0 hidden h-screen w-16 shrink-0 flex-col gap-6 border-r bg-sidebar px-2 py-4 md:flex lg:hidden">
        <Logo compact />
        <NavList compact />
      </aside>
      <aside className="no-print sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 overflow-y-auto border-r bg-sidebar px-3 py-4 lg:flex">
        <Logo />
        <NavList />
      </aside>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 gap-6 bg-sidebar px-3 py-4">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Logo />
          <NavList onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur md:px-6">
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}>
            <Menu className="size-4" />
          </Button>
          <div className="flex min-w-0 flex-1 items-center gap-2">{topbar}</div>
          <AlertsBell />
          <ThemeToggle />
          {/* TODO(auth): show the signed-in user. */}
          <span
            className="hidden size-8 items-center justify-center rounded-full bg-muted text-xs font-semibold sm:flex"
            title="Demo CMO (no sign-in yet)"
          >
            DC
          </span>
        </header>
        <main className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col gap-6 px-4 py-6 md:px-6">{children}</main>
      </div>
    </div>
  );
}
