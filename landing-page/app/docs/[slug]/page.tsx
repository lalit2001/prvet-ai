import fs from "fs";
import path from "path";
import { notFound } from "next/navigation";
import { MDXRemote } from "next-mdx-remote/rsc";

export async function generateStaticParams() {
  return [
    { slug: "quickstart" },
    { slug: "install" },
    { slug: "configuration" },
    { slug: "architecture" },
  ];
}

interface PageProps {
  params: Promise<{ slug: string }>;
}

export default async function DocPage({ params }: PageProps) {
  const { slug } = await params;
  
  const contentDir = path.join(process.cwd(), "content");
  const filePath = path.join(contentDir, `${slug}.mdx`);
  
  if (!fs.existsSync(filePath)) {
    notFound();
  }
  
  const rawContent = fs.readFileSync(filePath, "utf-8");
  
  return (
    <article className="prose prose-invert prose-zinc max-w-none prose-headings:tracking-tight prose-a:text-primary hover:prose-a:text-primary/80 prose-code:text-zinc-200 prose-code:bg-zinc-900 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-pre:bg-[#0a0f18] prose-pre:border prose-pre:border-zinc-800/80">
      <MDXRemote source={rawContent} />
    </article>
  );
}
