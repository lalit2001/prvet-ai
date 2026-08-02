"use client";

import { Copy } from "lucide-react";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui";
import { useState } from "react";

function Cmd({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-md border border-border bg-black/40 p-3 text-xs mono">
        <code>{text}</code>
      </pre>
      <button
        onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
        className="absolute right-2 top-2 rounded border border-border bg-panel px-1.5 py-1 text-[10px] text-text-3 opacity-0 group-hover:opacity-100"
      >
        {copied ? "copied" : <Copy className="h-3 w-3" />}
      </button>
    </div>
  );
}

export default function HelpPage() {
  return (
    <>
      <PageHeader title="Test on GitHub" subtitle="Five steps from a fresh clone to a real PR review posted on GitHub." />

      <div className="space-y-6">
        <Step n={1} title="Add at least one AI provider">
          <p>Open <b>AI Providers</b> in the sidebar. Add an OpenAI/Anthropic key, or wire Bedrock / Azure OpenAI / Ollama / vLLM — anything OpenAI-compatible works. Each provider needs a <code className="mono">fast</code> and <code className="mono">deep</code> role model set. Hit <b>Test</b> on the provider card to verify.</p>
        </Step>

        <Step n={2} title="Expose your local API to the internet">
          <p>GitHub needs a public URL to POST webhooks to. Easiest: <a href="https://ngrok.com/download" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">ngrok</a> (free tier is fine).</p>
          <Cmd text="ngrok http 8080" />
          <p className="text-xs text-text-3">Copy the <code className="mono">https://….ngrok-free.app</code> URL — that's your public API base. You'll paste it into step 4.</p>
        </Step>

        <Step n={3} title="Get a GitHub personal access token">
          <p>Create a fine-grained PAT at <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">github.com/settings/personal-access-tokens/new</a>. Give it access to the repos you want reviewed, with these permissions:</p>
          <ul className="list-inside list-disc text-sm text-text-2 pl-2">
            <li><b>Contents</b>: Read</li>
            <li><b>Pull requests</b>: Read &amp; write (to post the review comment)</li>
            <li><b>Webhooks</b>: Read &amp; write (to create the webhook)</li>
            <li><b>Metadata</b>: Read (mandatory)</li>
          </ul>
          <p className="text-xs text-text-3">Classic PATs work too — <code className="mono">repo</code> + <code className="mono">admin:repo_hook</code> scopes.</p>
        </Step>

        <Step n={4} title="Connect the GitHub account">
          <p>Open <b>AI Providers</b> sidebar &gt; <b>Add forge → GitHub</b> (or go to <a className="text-emerald-400 hover:underline" href="/admin/forges">/admin/forges</a>). Paste the PAT. We'll verify it and remember the account.</p>
          <p>Then <b>pick a repo</b> from the list. When you click <b>Enable</b>, we register a webhook on that repo pointing at:</p>
          <Cmd text="https://<your-ngrok-subdomain>.ngrok-free.app/api/v1/webhooks/<connection_id>" />
          <p className="text-xs text-text-3">The <code className="mono">connection_id</code> is filled in for you automatically.</p>
        </Step>

        <Step n={5} title="Open a PR — that's the test">
          <p>On the enabled repo, open (or push to) any pull request. Within a few seconds you'll see:</p>
          <ul className="list-inside list-disc text-sm text-text-2 pl-2">
            <li>A comment on the PR summarising files reviewed and findings by severity</li>
            <li>The run in <b>Runs</b> in the sidebar</li>
            <li>Findings in <b>Findings</b>, filterable by severity/category/repo</li>
          </ul>
          <p className="text-xs text-text-3">If nothing happens: check <b>Runs</b> for a failed row, or the API terminal for a webhook error. Common causes: PAT missing webhook permission (step 3), ngrok URL not up (step 2), no provider configured (step 1).</p>
        </Step>

        <Card>
          <CardHeader title="What works today" subtitle="Honest state of the tool" />
          <CardBody>
            <ul className="list-inside list-disc space-y-1 text-sm text-text-2">
              <li>✅ GitHub PAT connection + repo enablement + webhook creation</li>
              <li>✅ Real PR review on pull_request opened/synchronize/reopened</li>
              <li>✅ Diff-scoped LLM review with structured findings + summary comment</li>
              <li>✅ Multi-provider routing (OpenAI / Anthropic / Azure / Bedrock / Vertex / Ollama / vLLM / LiteLLM / any OpenAI-compatible)</li>
              <li>⚠️ Blast-radius (cross-file callers) — <i>diff-only for now, symbol_references join lands next</i></li>
              <li>⚠️ Merge gate (blocking merge) — <i>posts a comment, does not yet call GitHub Checks API</i></li>
              <li>⚠️ Real Semgrep/gitleaks/OSV — <i>LLM only for now</i></li>
              <li>❌ GitLab / Azure DevOps — <i>M4</i></li>
              <li>❌ OIDC/SSO — <i>M6</i></li>
            </ul>
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <div className="flex gap-4 p-5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-emerald-600/40 bg-emerald-600/10 text-sm font-semibold text-emerald-400">
          {n}
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <h3 className="text-sm font-semibold text-text-1">{title}</h3>
          <div className="space-y-3 text-sm text-text-2">{children}</div>
        </div>
      </div>
    </Card>
  );
}
