"use client";

import clsx from "clsx";
import {
  Activity, AlertOctagon, Bot, Cable, FileCheck, FolderGit2, GitPullRequest, HelpCircle,
  LayoutDashboard, Play, Settings, Code2, Loader2, LogOut, User, Users
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { StatusPill } from "@/components/ui";

const NAV = [
  { section: "Overview", items: [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/repos", label: "Repositories", icon: FolderGit2 },
    { href: "/prs", label: "Pull Requests", icon: GitPullRequest },
    { href: "/findings", label: "Findings", icon: AlertOctagon },
    { href: "/runs", label: "Runs", icon: Play },
  ]},
  { section: "Configure", items: [
    { href: "/admin/users", label: "Users & Access", icon: Users },
    { href: "/admin/forges", label: "GitHub / Forges", icon: Cable },
    { href: "/admin/providers", label: "AI Providers", icon: Bot },
    { href: "/admin/rules", label: "Rules", icon: FileCheck },
    { href: "/admin/ast", label: "AST Viewer", icon: Code2 },
    { href: "/admin/audit", label: "Audit log", icon: Activity },
    { href: "/admin", label: "Settings", icon: Settings },
  ]},
  { section: "Learn", items: [
    { href: "/help", label: "Documentation", icon: HelpCircle },
  ]},
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [authed, setAuthed] = useState(false);

  const isLoginPage = pathname ? pathname.replace(/\/$/, "") === "/login" : false;

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("crv_token");
      if (!token && !isLoginPage) {
        window.location.href = "/login";
      } else {
        setAuthed(true);
      }
    }
  }, [pathname, isLoginPage]);

  if (isLoginPage) {
    return <div className="min-h-screen bg-bg">{children}</div>;
  }

  if (!authed) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <Sidebar />
      <div className="pl-60">
        <TopBar />
        <main className="mx-auto max-w-7xl px-8 py-8">{children}</main>
      </div>
    </div>
  );
}

function Sidebar() {
  const path = usePathname() || "/";
  const [userRole, setUserRole] = useState("member");
  const [userName, setUserName] = useState("Standard User");
  const [userEmail, setUserEmail] = useState("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      setUserRole(localStorage.getItem("crv_role") || "member");
      setUserName(localStorage.getItem("crv_name") || "Standard User");
      setUserEmail(localStorage.getItem("crv_email") || "");
    }
  }, []);

  function handleLogout() {
    localStorage.removeItem("crv_token");
    localStorage.removeItem("crv_role");
    localStorage.removeItem("crv_email");
    localStorage.removeItem("crv_name");
    window.location.href = "/login";
  }

  // Hide Configure section for standard users
  const filteredNav = NAV.filter(s => s.section !== "Configure" || userRole === "admin");

  return (
    <aside className="fixed left-0 top-0 z-30 flex h-screen w-60 flex-col border-r border-border bg-panel/60 backdrop-blur">
      <div className="flex items-center gap-2 px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-600/20 ring-1 ring-emerald-600/40">
          <span className="text-sm font-bold text-emerald-400">c</span>
        </div>
        <div>
          <div className="text-sm font-semibold tracking-tight">Sentry Review</div>
          <div className="text-[10px] uppercase tracking-wider text-text-3">crv · dev</div>
        </div>
      </div>
      
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {filteredNav.map((s) => (
          <div key={s.section} className="mb-4">
            <div className="mb-1.5 px-2 text-[10px] font-medium uppercase tracking-wider text-text-3">{s.section}</div>
            <ul className="space-y-0.5">
              {s.items.map((it) => {
                const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
                const Icon = it.icon;
                return (
                  <li key={it.href}>
                    <Link
                      href={it.href}
                      className={clsx(
                        "group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-emerald-600/10 text-emerald-400"
                          : "text-text-2 hover:bg-panel-2 hover:text-text-1",
                      )}
                    >
                      <Icon className={clsx("h-4 w-4", active ? "text-emerald-400" : "text-text-3 group-hover:text-text-1")} />
                      {it.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* User profile footer */}
      <div className="border-t border-border p-4 bg-panel/30">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-neutral-900 border border-neutral-800 text-neutral-400">
            <User className="h-4 w-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-text-1 truncate">{userName}</div>
            <div className="text-[10px] text-text-3 capitalize truncate">{userRole === "admin" ? "Administrator" : "Member"}</div>
          </div>
          <button
            onClick={handleLogout}
            title="Log Out"
            className="p-1.5 text-text-3 hover:text-red-400 hover:bg-panel-2 rounded-lg transition-colors focus:outline-none"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}

function TopBar() {
  const [api_status, setStatus] = useState<"loading" | "ok" | "down">("loading");
  useEffect(() => {
    api.health().then(() => setStatus("ok")).catch(() => setStatus("down"));
    const t = setInterval(() => {
      api.health().then(() => setStatus("ok")).catch(() => setStatus("down"));
    }, 15000);
    return () => clearInterval(t);
  }, []);
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-bg/80 px-8 py-3 backdrop-blur">
      <div className="text-xs text-text-3">Self-hosted AI code review</div>
      <div className="flex items-center gap-3">
        <StatusPill status={api_status} />
      </div>
    </header>
  );
}
