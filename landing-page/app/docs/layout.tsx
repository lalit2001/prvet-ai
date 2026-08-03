"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  BookOpen, Terminal, Key, Search, Monitor, 
  Menu, X, Server, LayoutTemplate
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const SIDEBAR_GROUPS = [
  {
    title: "Platform",
    items: [
      { href: "/docs", label: "Overview", icon: LayoutTemplate },
      { href: "/docs/architecture", label: "Architecture", icon: Server },
    ]
  },
  {
    title: "Getting Started",
    items: [
      { href: "/docs/quickstart", label: "Quickstart", icon: BookOpen },
      { href: "/docs/install", label: "Installation Guide", icon: Terminal },
    ]
  },
  {
    title: "Pull Request Reviews",
    items: [
      { href: "/docs/configuration", label: "Rules Configuration", icon: Key },
    ]
  }
];

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);

  return (
    <div className="min-h-screen bg-[#090d16] text-zinc-100 flex flex-col font-sans selection:bg-primary/30 selection:text-primary">
      
      {/* Primary Top Navbar */}
      <header className="border-b border-zinc-800/80 bg-[#06090e]/95 backdrop-blur-md sticky top-0 z-50">
        <div className="px-4 md:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/20 ring-1 ring-primary/40">
                <img src="/logo.svg" className="h-4 w-4" alt="PRVet Logo" />
              </div>
              <span className="font-extrabold text-sm tracking-tight text-white">PRVet Docs</span>
            </Link>
            
            {/* Search Mockup */}
            <div className="hidden md:flex items-center w-64 bg-zinc-900 border border-zinc-800 rounded-md px-3 py-1.5 text-zinc-400 group hover:border-zinc-700 transition cursor-pointer">
              <Search className="h-4 w-4 mr-2 text-zinc-500 group-hover:text-zinc-400" />
              <span className="text-xs">Search...</span>
              <div className="ml-auto flex items-center gap-0.5">
                <kbd className="font-sans text-[10px] bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400">⌘</kbd>
                <kbd className="font-sans text-[10px] bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400">K</kbd>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <Link href="http://localhost:3737/login" className="hidden sm:block text-xs font-semibold text-zinc-300 hover:text-white transition">
              Dashboard
            </Link>
            <Link href="http://localhost:3737/register" className="text-xs bg-primary hover:bg-primary/90 text-white font-semibold px-4 py-1.5 rounded-md transition shadow-md shadow-primary/20">
              Sign up <span className="ml-1 opacity-70">›</span>
            </Link>
            
            <button 
              className="md:hidden p-1.5 text-zinc-400 hover:text-white"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </header>

      {/* Secondary Navbar */}
      <div className="hidden md:flex items-center gap-6 px-6 h-12 border-b border-zinc-800/80 bg-[#090d16] text-xs font-medium text-zinc-400 overflow-x-auto">
        <div className="flex items-center gap-2 text-primary border-b-2 border-primary h-full px-1">
          <Server className="h-3.5 w-3.5" />
          <span>PRVet Platform</span>
        </div>
        <div className="flex items-center gap-2 hover:text-zinc-200 transition cursor-pointer px-1">
          <Terminal className="h-3.5 w-3.5" />
          <span>Command-Line Review Tool</span>
        </div>
        <div className="flex items-center gap-2 hover:text-zinc-200 transition cursor-pointer px-1">
          <Monitor className="h-3.5 w-3.5" />
          <span>IDE Extension</span>
        </div>
      </div>

      {/* Workspace */}
      <div className="flex-1 max-w-[1400px] w-full mx-auto px-4 md:px-6 py-8 flex gap-10">
        
        {/* Left Sidebar */}
        <aside className={cn(
          "fixed inset-0 z-40 bg-[#090d16] pt-14 px-6 md:pt-0 md:px-0 md:static md:block md:w-64 shrink-0 border-r border-zinc-800/50 md:min-h-[calc(100vh-8rem)]",
          isMobileMenuOpen ? "block" : "hidden"
        )}>
          <div className="h-full overflow-y-auto pb-20 md:pb-0 md:pr-4 pt-4 md:pt-0">
            {SIDEBAR_GROUPS.map((group, gIdx) => (
              <div key={group.title} className={cn("mb-8", gIdx === 0 && "mt-2")}>
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider mb-3 px-2">
                  {group.title}
                </h3>
                <nav className="space-y-0.5">
                  {group.items.map(link => {
                    // Match logic: Overview is exactly "/docs", others are prefixes like "/docs/quickstart"
                    const active = link.href === "/docs" 
                      ? pathname === "/docs" 
                      : pathname.startsWith(link.href);
                    
                    return (
                      <Link
                        key={link.href}
                        href={link.href}
                        onClick={() => setIsMobileMenuOpen(false)}
                        className={cn(
                          "flex items-center py-2 px-3 rounded-lg text-sm transition-colors duration-200",
                          active
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50"
                        )}
                      >
                        {link.label}
                      </Link>
                    );
                  })}
                </nav>
              </div>
            ))}
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 min-w-0 pb-24 max-w-4xl">
          {children}
        </main>
      </div>
    </div>
  );
}
