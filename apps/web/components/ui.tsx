"use client";

import clsx from "clsx";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

// ────────── Card, PageHeader, StatCard, Empty ──────────

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("rounded-lg border border-border bg-panel", className)}>{children}</div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold text-text-1">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-text-3">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={clsx("p-5", className)}>{children}</div>;
}

export function PageHeader({
  title, subtitle, actions,
}: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-text-1">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-text-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  icon: Icon, label, value, hint, tone = "default",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "success" | "warn" | "danger";
}) {
  const toneClass = {
    default: "text-text-2",
    success: "text-emerald-400",
    warn: "text-yellow-400",
    danger: "text-red-400",
  }[tone];
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-text-3">{label}</div>
          <div className="mt-2 text-2xl font-semibold tabular-nums text-text-1">{value}</div>
          {hint && <div className={clsx("mt-1 text-xs", toneClass)}>{hint}</div>}
        </div>
        <Icon className={clsx("h-5 w-5 shrink-0", toneClass)} />
      </div>
    </Card>
  );
}

export function EmptyState({
  icon: Icon, title, hint, action,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-panel/50 p-10 text-center">
      <Icon className="mx-auto h-8 w-8 text-text-3" />
      <p className="mt-3 text-sm text-text-1">{title}</p>
      {hint && <p className="mt-1 text-xs text-text-3">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

// ────────── Buttons ──────────

type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
type BtnSize = "sm" | "md";

export function Button({
  variant = "primary", size = "md", className, ...props
}: { variant?: BtnVariant; size?: BtnSize } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
  const sizes = { sm: "px-2.5 py-1 text-xs", md: "px-3.5 py-1.5 text-sm" }[size];
  const variants = {
    primary: "bg-emerald-600 text-white hover:bg-emerald-500",
    secondary: "border border-border bg-panel-2 text-text-1 hover:border-border-strong",
    ghost: "text-text-2 hover:bg-panel-2 hover:text-text-1",
    danger: "border border-red-900 text-red-300 hover:bg-red-950/40",
  }[variant];
  return <button className={clsx(base, sizes, variants, className)} {...props} />;
}

// ────────── Badge ──────────

const SEV_STYLES: Record<string, string> = {
  critical: "border-red-900 bg-red-950/40 text-red-300",
  high: "border-orange-900 bg-orange-950/40 text-orange-300",
  medium: "border-yellow-900 bg-yellow-950/40 text-yellow-300",
  low: "border-blue-900 bg-blue-950/40 text-blue-300",
  info: "border-neutral-800 bg-neutral-900 text-neutral-400",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={clsx(
      "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
      SEV_STYLES[severity] || SEV_STYLES.info
    )}>{severity}</span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const s = status.toLowerCase();
  const cls =
    s === "ok" || s === "succeeded" || s === "pass" ? "bg-emerald-950/40 text-emerald-300 border-emerald-900" :
    s === "failed" || s === "fail" || s === "down" || s === "error" ? "bg-red-950/40 text-red-300 border-red-900" :
    s === "running" || s === "queued" || s === "loading" ? "bg-blue-950/40 text-blue-300 border-blue-900" :
    "bg-neutral-900 text-neutral-400 border-neutral-800";
  return (
    <span className={clsx(
      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
      cls,
    )}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

export function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={clsx(
      "inline-flex items-center rounded-md border border-border bg-panel-2 px-2 py-0.5 text-xs text-text-2",
      className,
    )}>{children}</span>
  );
}

// ────────── Modal ──────────

export function Modal({
  open, onClose, title, children, size = "md",
}: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  const width = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl" }[size];
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 pt-24" onClick={onClose}>
      <div className={clsx("w-full rounded-lg border border-border bg-panel shadow-2xl", width)} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-text-3 hover:bg-panel-2 hover:text-text-1"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

// ────────── Toast ──────────

type Toast = { id: number; kind: "success" | "error" | "info"; msg: string };
const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id}
            className={clsx(
              "pointer-events-auto flex items-start gap-2 rounded-md border p-3 text-sm shadow-lg",
              t.kind === "success" && "border-emerald-900 bg-emerald-950/60 text-emerald-200",
              t.kind === "error" && "border-red-900 bg-red-950/60 text-red-200",
              t.kind === "info" && "border-neutral-800 bg-panel text-text-1",
            )}
          >
            {t.kind === "success" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> :
             t.kind === "error"   ? <AlertCircle  className="h-4 w-4 shrink-0" /> :
                                    <Info         className="h-4 w-4 shrink-0" />}
            <span className="whitespace-pre-wrap">{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ────────── Table wrappers (headless-ish) ──────────

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className={clsx("w-full text-sm", className)}>{children}</table>
    </div>
  );
}
export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="bg-panel-2 text-left text-[11px] uppercase tracking-wider text-text-3">{children}</thead>;
}
export function TH({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={clsx("px-4 py-2.5 font-medium", className)}>{children}</th>;
}
export function TBody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-border">{children}</tbody>;
}
export function TR({ children, className }: { children: React.ReactNode; className?: string }) {
  return <tr className={clsx("bg-panel hover:bg-panel-2/60", className)}>{children}</tr>;
}
export function TD({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={clsx("px-4 py-2.5 text-text-1", className)}>{children}</td>;
}

export function Markdown({ text }: { text: string }) {
  if (!text) return null;
  const blocks = text.split(/\n\n+/);
  return (
    <div className="space-y-3">
      {blocks.map((block, idx) => {
        const trimmed = block.trim();
        if (!trimmed) return null;
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
          const items = trimmed.split(/\n[-*]\s+/).map(item => item.replace(/^[-*]\s+/, ""));
          return (
            <ul key={idx} className="list-disc pl-5 space-y-1.5 text-xs text-text-2 my-2">
              {items.map((item, i) => (
                <li key={i}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={idx} className="text-xs text-text-2 leading-relaxed">
            {renderInline(trimmed)}
          </p>
        );
      })}
    </div>
  );
}

function renderInline(str: string) {
  const parts = str.split(/(\*\*.*?\*\*|`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-text-1">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="bg-panel-2 border border-border px-1.5 py-0.5 rounded text-[11px] font-mono text-emerald-400">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}
