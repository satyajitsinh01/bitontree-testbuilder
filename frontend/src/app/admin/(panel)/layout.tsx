"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ClipboardList,
  FileQuestion,
  LogOut,
  ScrollText,
  Users,
} from "lucide-react";
import { getToken, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin", label: "Assessments", icon: ClipboardList },
  { href: "/admin/questions", label: "Question Bank", icon: FileQuestion },
  { href: "/admin/users", label: "Admin Users", icon: Users },
  { href: "/admin/audit", label: "Audit Log", icon: ScrollText },
];

export default function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [name, setName] = useState("");

  useEffect(() => {
    if (!getToken("admin")) router.replace("/login");
    setName(window.localStorage.getItem("tb_admin_name") ?? "");
  }, [router]);

  return (
    <div className="min-h-screen flex bg-muted/40">
      <aside className="w-60 shrink-0 border-r bg-sidebar flex flex-col">
        <div className="h-16 flex items-center gap-2.5 px-5 border-b">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <ClipboardList className="h-4 w-4" />
          </span>
          <span className="font-heading text-base font-semibold tracking-tight text-sidebar-foreground">
            TestBuilder
          </span>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <p className="px-3 pb-1 pt-2 text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Workspace
          </p>
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                  active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t space-y-1">
          <div className="flex items-center gap-2.5 px-2 py-1.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
              {(name || "A").slice(0, 1).toUpperCase()}
            </span>
            <p className="text-xs font-medium text-sidebar-foreground truncate">{name}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-sidebar-foreground/70"
            onClick={() => {
              setToken("admin", null);
              router.push("/login");
            }}
          >
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </div>
      </aside>
      <main className="flex-1 p-6 lg:p-8 overflow-x-auto">{children}</main>
    </div>
  );
}
