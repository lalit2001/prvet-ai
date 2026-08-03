import React from "react";
import Link from "next/link";
import { Copy, Terminal, ShieldAlert, BookOpen } from "lucide-react";

export default function DocsPage() {
  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
      
      {/* Header */}
      <div className="space-y-4">
        <span className="text-zinc-500 text-sm">Platform</span>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <h1 className="text-4xl font-bold text-white tracking-tight">AI Code Review</h1>
          <button className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition text-xs font-medium">
            <Copy className="h-3.5 w-3.5" />
            Copy page
          </button>
        </div>
        <p className="text-zinc-400 text-lg leading-relaxed max-w-3xl">
          PRVet is an AI-powered platform for code review, blast radius analysis, and security auditing. Review pull requests automatically on GitHub/GitLab, enforce custom YAML rules, and keep your intellectual property 100% on-premise. Ship better software faster with confidence!
        </p>
      </div>

      {/* Bento Grid */}
      <div className="grid md:grid-cols-3 gap-6 pt-6">
        
        <Link href="/docs/architecture" className="group p-6 rounded-2xl bg-[#0d121c] border border-zinc-800 hover:border-zinc-700 transition-colors">
          <div className="text-primary mb-4">
            <ShieldAlert className="h-6 w-6" />
          </div>
          <h3 className="text-lg font-bold text-white mb-2 group-hover:text-primary transition-colors">PRVet Agent</h3>
          <p className="text-sm text-zinc-400 leading-relaxed">
            AI-powered investigation, security auditing, and code changes right from your Git Forge. Shared workspace knowledge, external tools, and governed access.
          </p>
        </Link>

        <Link href="/docs/quickstart" className="group p-6 rounded-2xl bg-[#0d121c] border border-zinc-800 hover:border-zinc-700 transition-colors">
          <div className="text-accent mb-4">
            <BookOpen className="h-6 w-6" />
          </div>
          <h3 className="text-lg font-bold text-white mb-2 group-hover:text-accent transition-colors">Code Review</h3>
          <p className="text-sm text-zinc-400 leading-relaxed">
            Automated, context-aware code reviews. Catches bugs, enforces standards, and learns from your team's feedback. Continuous improvement for your PRs.
          </p>
        </Link>

        <Link href="/docs/configuration" className="group p-6 rounded-2xl bg-[#0d121c] border border-zinc-800 hover:border-zinc-700 transition-colors">
          <div className="text-emerald-500 mb-4">
            <Terminal className="h-6 w-6" />
          </div>
          <h3 className="text-lg font-bold text-white mb-2 group-hover:text-emerald-400 transition-colors">Custom Gating</h3>
          <p className="text-sm text-zinc-400 leading-relaxed">
            Turn ideas, issues, and designs into precise YAML Custom Rules. Get granular AST checking and code-aware logic gating to block problematic merges automatically.
          </p>
        </Link>
        
      </div>

      <div className="pt-6 border-t border-zinc-800/80 mt-12 text-sm text-zinc-400 leading-relaxed">
        Use PRVet wherever you work. Integrate with your Git platform for automated PR reviews, run reviews from the command line, or build your own workflows using our CLI binary.
      </div>
    </div>
  );
}
