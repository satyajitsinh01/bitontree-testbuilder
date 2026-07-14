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
    if (!getToken("admin")) router.replace("/admin/login");
    setName(window.localStorage.getItem("tb_admin_name") ?? "");
  }, [router]);

  return (
    <div className="min-h-screen flex bg-muted/30">
      <aside className="w-60 shrink-0 border-r bg-background flex flex-col">
        <div className="h-14 flex items-center px-5 border-b font-semibold tracking-tight">
          TestBuilder
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t space-y-2">
          <p className="px-3 text-xs text-muted-foreground truncate">{name}</p>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2"
            onClick={() => {
              setToken("admin", null);
              router.push("/admin/login");
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
