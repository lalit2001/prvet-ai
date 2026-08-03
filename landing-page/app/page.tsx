"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { 
  GitPullRequest, BrainCircuit, Code, ShieldAlert,
  Server, Lock, FileCode, Search, Terminal, ArrowRight,
  CheckCircle2, Network, Cpu, Database
} from "lucide-react";

const fadeIn = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6 } }
};

export default function Home() {
  return (
    <div className="min-h-screen bg-brand-light text-foreground selection:bg-brand-primary/30 selection:text-brand-primary font-sans overflow-x-hidden">
      
      {/* Navbar */}
      <header className="sticky top-0 z-50 bg-brand-light/95 backdrop-blur-md border-b border-black/5">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-1.5">
              <span className="font-serif text-2xl tracking-tight font-bold text-brand-dark">PRVet</span>
              <div className="w-1.5 h-1.5 rounded-full bg-brand-primary mt-1.5" />
            </Link>
            
            <nav className="hidden md:flex items-center gap-6">
              <Link href="#scip" className="text-sm font-medium text-brand-dark/70 hover:text-brand-dark transition-colors">
                SCIP Indexing
              </Link>
              <Link href="#rules" className="text-sm font-medium text-brand-dark/70 hover:text-brand-dark transition-colors">
                Rules Engine
              </Link>
              <Link href="#security" className="text-sm font-medium text-brand-dark/70 hover:text-brand-dark transition-colors">
                Security
              </Link>
              <Link href="/docs" className="text-sm font-medium text-brand-dark/70 hover:text-brand-dark transition-colors">
                Docs
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <Link 
              href="http://localhost:3737/login" 
              className="text-sm bg-brand-dark hover:bg-black text-white font-medium px-6 py-2 rounded-full transition-all shadow-md"
            >
              Book a demo
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* Custom Hero Section */}
        <section className="relative pt-24 pb-32 bg-brand-dark overflow-hidden">
          {/* Gradients */}
          <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-brand-primary/20 rounded-full blur-[120px] mix-blend-screen pointer-events-none translate-x-1/3 -translate-y-1/3" />
          <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-indigo-500/10 rounded-full blur-[100px] mix-blend-screen pointer-events-none -translate-x-1/3 translate-y-1/3" />
          
          <div className="max-w-7xl mx-auto px-6 relative z-10 grid lg:grid-cols-2 gap-16 items-center">
            
            <motion.div 
              initial="hidden" animate="visible" variants={fadeIn}
              className="space-y-8"
            >
              <div className="inline-flex items-center gap-2 text-brand-primary text-[10px] uppercase tracking-widest font-bold">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-primary" />
                ENTERPRISE CODE REVIEW · V1.0
              </div>
              
              <h1 className="text-5xl md:text-7xl font-serif text-white tracking-tight leading-[1.1]">
                Review code with <br />
                <span className="italic text-brand-primary/90 font-normal">context.</span>
              </h1>
              
              <p className="text-brand-light/70 text-lg leading-relaxed font-light max-w-lg">
                PRVet doesn't just read diffs. It parses your Abstract Syntax Tree, indexes your entire repository, and flags blast-radius logic bugs—all while remaining 100% airgapped inside your VPC.
              </p>
              
              <div className="flex flex-col sm:flex-row gap-4 pt-4">
                <Link 
                  href="/docs" 
                  className="inline-flex items-center justify-center gap-2 bg-brand-primary hover:bg-brand-primary/90 text-white font-medium px-8 py-3.5 rounded-full transition-all text-sm shadow-[0_0_40px_-10px_rgba(124,58,237,0.4)]"
                >
                  Start Vetting Code <ArrowRight className="w-4 h-4" />
                </Link>
                <Link 
                  href="https://github.com/prvet" 
                  className="inline-flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium px-8 py-3.5 rounded-full transition-all text-sm"
                >
                  <Terminal className="w-4 h-4 text-white/50" />
                  View CLI Source
                </Link>
              </div>
            </motion.div>

            {/* Custom Code Visual */}
            <motion.div 
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3, duration: 0.8 }}
              className="relative"
            >
              <div className="bg-[#0B1120] border border-white/10 rounded-2xl p-6 shadow-2xl relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-brand-primary to-indigo-500" />
                
                <div className="flex items-center justify-between mb-6 border-b border-white/5 pb-4">
                  <div className="flex items-center gap-2">
                    <GitPullRequest className="w-4 h-4 text-zinc-500" />
                    <span className="text-xs font-mono text-zinc-400">feat: update signature</span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-brand-accent/20 text-brand-accent text-[10px] font-bold uppercase tracking-wider">Merge Blocked</span>
                </div>

                <div className="space-y-4 font-mono text-sm">
                  <div className="text-zinc-500">{"// db.py (modified)"}</div>
                  <div className="bg-black/50 p-4 rounded-xl border border-white/5">
                    <div className="text-rose-400">{"- def execute(query: str, params=None):"}</div>
                    <div className="text-emerald-400">{"+ def execute(query: str, *, params=None):"}</div>
                  </div>
                  
                  <div className="pt-4 flex items-start gap-3">
                    <div className="w-6 h-6 rounded bg-brand-primary flex items-center justify-center shrink-0 mt-1">
                      <BrainCircuit className="w-3.5 h-3.5 text-white" />
                    </div>
                    <div className="bg-brand-primary/10 border border-brand-primary/20 rounded-xl p-4 text-brand-primary/90 text-xs leading-relaxed">
                      <strong>Blast Radius Warning:</strong> Converting <code className="text-white">params</code> to a keyword-only argument breaks 47 downstream callers across 12 files. 
                      <br/><br/>
                      <em>Detected via SCIP Graph Indexing.</em>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>

          </div>
        </section>

        {/* Ecosystem Banner */}
        <section className="border-b border-brand-dark/5 bg-white py-8">
          <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-center gap-8 md:gap-16 opacity-60 grayscale hover:grayscale-0 transition-all duration-500">
            <span className="text-xs font-bold uppercase tracking-widest text-brand-dark/40">Integrates with</span>
            <div className="flex items-center gap-12">
              <span className="font-serif font-bold text-xl text-brand-dark">GitHub Enterprise</span>
              <span className="font-serif font-bold text-xl text-brand-dark">GitLab Self-Managed</span>
              <span className="font-serif font-bold text-xl text-brand-dark">Bitbucket Server</span>
            </div>
          </div>
        </section>

        {/* Deep Dive 1: SCIP Indexing */}
        <section id="scip" className="py-32 px-6">
          <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-16 items-center">
            <div>
              <div className="text-[10px] font-bold text-brand-primary uppercase tracking-widest mb-4">
                Beyond the Diff
              </div>
              <h2 className="text-4xl md:text-5xl font-serif text-brand-dark leading-[1.1] mb-6">
                Understand the <br/>blast radius.
              </h2>
              <p className="text-brand-dark/70 text-base leading-relaxed mb-8">
                Most AI tools read a Git diff in isolation. PRVet checks out your entire codebase and builds a SCIP (Shared Code Intelligence Portal) index. It maps every function call, interface implementation, and variable reference.
              </p>
              <ul className="space-y-4">
                <li className="flex items-start gap-3 text-sm text-brand-dark/80">
                  <Network className="w-5 h-5 text-brand-primary shrink-0" />
                  <span><strong>Call Graph Resolution:</strong> Knows exactly which files will break if you modify a shared utility.</span>
                </li>
                <li className="flex items-start gap-3 text-sm text-brand-dark/80">
                  <Database className="w-5 h-5 text-brand-primary shrink-0" />
                  <span><strong>Type-Aware:</strong> Doesn't just grep strings. Understands type boundaries across your TypeScript, Python, or Go mono-repos.</span>
                </li>
              </ul>
            </div>
            
            <div className="bg-brand-dark rounded-3xl p-8 relative overflow-hidden shadow-xl border border-brand-dark/10">
              <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-20" />
              <div className="relative z-10 flex flex-col gap-4">
                <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex items-center justify-between text-white">
                  <div className="flex flex-col">
                    <span className="text-xs font-mono opacity-50 mb-1">utils/auth.py</span>
                    <span className="font-mono text-sm line-through decoration-brand-accent">verify_session()</span>
                  </div>
                  <ArrowRight className="w-4 h-4 text-zinc-600" />
                </div>
                
                <div className="flex gap-4">
                  <div className="w-px bg-gradient-to-b from-brand-primary/50 to-transparent ml-8" />
                  <div className="space-y-4 py-2 w-full">
                    <div className="bg-brand-accent/20 border border-brand-accent/30 text-brand-accent rounded-xl p-3 text-xs font-mono">
                      FAIL: routers/users.py:L14 calling verify_session()
                    </div>
                    <div className="bg-brand-accent/20 border border-brand-accent/30 text-brand-accent rounded-xl p-3 text-xs font-mono">
                      FAIL: jobs/sync.py:L92 calling verify_session()
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Deep Dive 2: Custom Rules */}
        <section id="rules" className="py-32 px-6 bg-white border-y border-brand-dark/5">
          <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-16 items-center">
            
            <div className="order-2 md:order-1 bg-brand-dark rounded-3xl p-8 relative shadow-xl border border-brand-dark/10">
              <div className="flex items-center gap-2 mb-4 pb-4 border-b border-white/10">
                <FileCode className="w-4 h-4 text-brand-primary" />
                <span className="text-xs font-mono text-white/50">.crv.yml</span>
              </div>
              <pre className="font-mono text-xs text-zinc-300 leading-relaxed overflow-x-auto">
<span className="text-brand-primary">rules:</span>
  - <span className="text-indigo-400">id:</span> <span className="text-emerald-300">block-unsafe-eval</span>
    <span className="text-indigo-400">pattern:</span> <span className="text-emerald-300">"eval(...)"</span>
    <span className="text-indigo-400">message:</span> <span className="text-emerald-300">"Never use eval in production."</span>
    <span className="text-indigo-400">severity:</span> <span className="text-emerald-300">error</span>

  - <span className="text-indigo-400">id:</span> <span className="text-emerald-300">require-logger</span>
    <span className="text-indigo-400">pattern:</span> <span className="text-emerald-300">"console.log(...)"</span>
    <span className="text-indigo-400">message:</span> <span className="text-emerald-300">"Use the internal winston logger."</span>
    <span className="text-indigo-400">severity:</span> <span className="text-emerald-300">warning</span>
              </pre>
            </div>

            <div className="order-1 md:order-2">
              <div className="text-[10px] font-bold text-brand-primary uppercase tracking-widest mb-4">
                Governance as Code
              </div>
              <h2 className="text-4xl md:text-5xl font-serif text-brand-dark leading-[1.1] mb-6">
                Enforce your standards. <br/>Automatically.
              </h2>
              <p className="text-brand-dark/70 text-base leading-relaxed mb-8">
                Tired of repeating the same review comments? Define organizational policies in a simple `.crv.yml` file at the root of your repository. PRVet acts as an intelligent, AST-aware linter that enforces your specific architecture.
              </p>
              <Link 
                href="/docs/configuration" 
                className="inline-flex items-center gap-2 text-brand-primary font-bold text-sm hover:gap-3 transition-all"
              >
                Read the Rule Schema Spec <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            
          </div>
        </section>

        {/* Deep Dive 3: Security */}
        <section id="security" className="py-32 px-6">
          <div className="max-w-7xl mx-auto text-center max-w-3xl">
            <ShieldAlert className="w-12 h-12 text-brand-dark mx-auto mb-6" />
            <h2 className="text-4xl md:text-5xl font-serif text-brand-dark leading-[1.1] mb-6">
              Your IP never leaves your VPC.
            </h2>
            <p className="text-brand-dark/70 text-lg leading-relaxed mb-12 max-w-2xl mx-auto">
              Cloud-based AI assistants require you to send proprietary source code to third-party APIs. PRVet is designed for high-compliance environments. It deploys entirely on-premise via Docker Compose.
            </p>
          </div>

          <div className="max-w-5xl mx-auto grid md:grid-cols-3 gap-6">
            <div className="bg-white p-8 rounded-2xl border border-brand-dark/5 shadow-sm text-center">
              <Server className="w-6 h-6 text-brand-primary mx-auto mb-4" />
              <h3 className="font-bold text-brand-dark mb-2">Stateless Workers</h3>
              <p className="text-sm text-brand-dark/60 leading-relaxed">
                Review jobs run in isolated Celery workers. Code is checked out to memory and instantly wiped after the review completes.
              </p>
            </div>
            <div className="bg-white p-8 rounded-2xl border border-brand-dark/5 shadow-sm text-center">
              <Cpu className="w-6 h-6 text-brand-primary mx-auto mb-4" />
              <h3 className="font-bold text-brand-dark mb-2">BYO Inference</h3>
              <p className="text-sm text-brand-dark/60 leading-relaxed">
                Connect PRVet to your locally hosted Ollama instances, Azure Foundry, or private endpoints. Total control over inference.
              </p>
            </div>
            <div className="bg-white p-8 rounded-2xl border border-brand-dark/5 shadow-sm text-center">
              <Lock className="w-6 h-6 text-brand-primary mx-auto mb-4" />
              <h3 className="font-bold text-brand-dark mb-2">Airgapped Database</h3>
              <p className="text-sm text-brand-dark/60 leading-relaxed">
                All tokens, webhooks, and review metadata are stored in a local PostgreSQL instance that you manage.
              </p>
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="py-32 px-6 bg-brand-dark text-center relative overflow-hidden">
          <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-10" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl h-64 bg-brand-primary/20 blur-[100px] rounded-full" />
          
          <div className="relative z-10 max-w-3xl mx-auto">
            <h2 className="text-5xl md:text-7xl font-serif text-white tracking-tight mb-8">
              Ready to ship <br/><span className="italic text-brand-primary">flawless</span> code?
            </h2>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link 
                href="/docs/install" 
                className="bg-brand-primary hover:bg-brand-primary/90 text-white font-medium px-10 py-4 rounded-full transition-all text-sm shadow-[0_0_40px_-10px_rgba(124,58,237,0.4)]"
              >
                Install the CLI
              </Link>
              <Link 
                href="http://localhost:3737/login" 
                className="bg-white/10 hover:bg-white/20 text-white font-medium px-10 py-4 rounded-full transition-all text-sm backdrop-blur-sm"
              >
                Book a Demo
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-brand-dark/10 py-16">
        <div className="max-w-7xl mx-auto px-6 grid md:grid-cols-4 gap-12 md:gap-6">
          <div className="col-span-1 md:col-span-2 space-y-4">
            <Link href="/" className="flex items-center gap-1.5 opacity-80 mb-4">
              <span className="font-serif text-xl tracking-tight font-bold text-brand-dark">PRVet</span>
              <div className="w-1.5 h-1.5 rounded-full bg-brand-primary mt-1.5" />
            </Link>
            <p className="text-brand-dark/50 text-xs max-w-xs leading-relaxed">
              Self-hosted AI code review that ships with your codebase, keeping your intellectual property securely within your virtual boundary.
            </p>
          </div>
          
          <div className="space-y-4">
            <h4 className="text-brand-dark font-bold text-xs uppercase tracking-widest">Platform</h4>
            <ul className="space-y-3 text-sm text-brand-dark/60">
              <li><Link href="#scip" className="hover:text-brand-primary transition-colors">SCIP Indexing</Link></li>
              <li><Link href="#rules" className="hover:text-brand-primary transition-colors">Custom Rules</Link></li>
              <li><Link href="#security" className="hover:text-brand-primary transition-colors">Security Profile</Link></li>
            </ul>
          </div>

          <div className="space-y-4">
            <h4 className="text-brand-dark font-bold text-xs uppercase tracking-widest">Developers</h4>
            <ul className="space-y-3 text-sm text-brand-dark/60">
              <li><Link href="/docs" className="hover:text-brand-primary transition-colors">Documentation</Link></li>
              <li><Link href="https://github.com/prvet" className="hover:text-brand-primary transition-colors">GitHub Repository</Link></li>
            </ul>
          </div>
        </div>
        
        <div className="max-w-7xl mx-auto px-6 pt-12 mt-12 border-t border-brand-dark/5 flex flex-col md:flex-row items-center justify-between text-xs text-brand-dark/40 font-mono">
          <span>&copy; {new Date().getFullYear()} PRVET INC. OPEN SOURCE APACHE 2.0.</span>
          <div className="flex gap-6 mt-4 md:mt-0">
            <Link href="#" className="hover:text-brand-dark">PRIVACY</Link>
            <Link href="#" className="hover:text-brand-dark">TERMS</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
