"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/admin", label: "Admin" },
  { href: "/admin/rules", label: "Rules" },
  { href: "/admin/audit", label: "Audit" },
];

export default function Nav() {
  const path = usePathname() || "/";
  return (
    <nav className="border-b border-neutral-900 bg-neutral-950/50">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
        <Link href="/" className="text-sm font-semibold tracking-tight">Sentry Review</Link>
        <div className="flex gap-4 text-sm">
          {links.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link
                key={l.href} href={l.href}
                className={active ? "text-emerald-400" : "text-neutral-400 hover:text-neutral-200"}
              >
                {l.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
