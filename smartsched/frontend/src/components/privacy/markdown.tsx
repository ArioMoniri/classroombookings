/**
 * The privacy notice's `body_md` as React elements, without HTML injection: headings (`#`, `##`, `###`), bullet lists
 * (`-`, `*`), numbered lists (`1.`), paragraphs and `**bold**`. Everything else is text. The administrator writes the
 * notice; nothing here adds wording.
 */
import { Fragment, type ReactNode } from "react";

type TextBlock = { kind: "h1" | "h2" | "h3" | "p"; text: string };
type ListBlock = { kind: "ul" | "ol"; items: string[] };
type Block = TextBlock | ListBlock;
const isList = (b: Block): b is ListBlock => b.kind === "ul" || b.kind === "ol";

export function parseMarkdown(md: string): Block[] {
  const out: Block[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) out.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  for (const raw of md.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trim();
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    const ul = /^[-*]\s+(.*)$/.exec(line);
    const ol = /^\d+[.)]\s+(.*)$/.exec(line);
    if (!line) {
      flush();
      continue;
    }
    if (h) {
      flush();
      out.push({ kind: (["h1", "h2", "h3"] as const)[h[1]!.length - 1]!, text: h[2]! });
    } else if (ul || ol) {
      flush();
      const kind = ul ? "ul" : "ol";
      const text = (ul ?? ol)![1]!;
      const last = out[out.length - 1];
      if (last && isList(last) && last.kind === kind) last.items.push(text);
      else out.push({ kind, items: [text] });
    } else para.push(line);
  }
  flush();
  return out;
}

function inline(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => (p.startsWith("**") && p.endsWith("**") && p.length > 4 ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>));
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks = parseMarkdown(source);
  return (
    <div className={className}>
      {blocks.map((b, i) => {
        if (isList(b)) {
          const List = b.kind === "ul" ? "ul" : "ol";
          return (
            <List key={i} className={b.kind === "ul" ? "mt-2 list-disc pl-5" : "mt-2 list-decimal pl-5"}>
              {b.items.map((it, j) => (
                <li key={j}>{inline(it)}</li>
              ))}
            </List>
          );
        }
        if (b.kind === "h1") return <h3 key={i} className="mt-3 type-title-3 text-label-1 first:mt-0">{inline(b.text)}</h3>;
        if (b.kind === "h2") return <h4 key={i} className="mt-3 type-headline text-label-1 first:mt-0">{inline(b.text)}</h4>;
        if (b.kind === "h3") return <h5 key={i} className="mt-2 type-callout font-semibold text-label-1 first:mt-0">{inline(b.text)}</h5>;
        return (
          <p key={i} className="mt-2 first:mt-0">
            {inline(b.text)}
          </p>
        );
      })}
    </div>
  );
}
