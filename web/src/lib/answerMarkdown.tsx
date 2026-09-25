import type { ReactNode } from "react";

/**
 * Renders the assistant's own prose (`Answer.body`) from the light Markdown
 * models write: paragraphs, **bold**, *italic*, `code`, bullet and numbered
 * lists, and `#` headings. Everything else stays literal text.
 *
 * Built from React elements -- never `dangerouslySetInnerHTML` -- so model
 * output can only ever become text, never markup. This is for the model's
 * framing only: quoted manual text lives in the citation cards and is drawn
 * by ManualBlocks, verbatim.
 */
export function AnswerMarkdown({ text }: { text: string }) {
  return <>{blocks(text)}</>;
}

// **bold**, *italic* (the opening star must touch a word, so "4 exits * 2"
// stays literal), `code`.
const INLINE = /\*\*([^*\n]+?)\*\*|\*([^*\s][^*\n]*?)\*|`([^`\n]+)`/g;

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const key = out.length;
    if (m[1] !== undefined) out.push(<strong key={key}>{inline(m[1])}</strong>);
    else if (m[2] !== undefined) out.push(<em key={key}>{inline(m[2])}</em>);
    else out.push(<code key={key}>{m[3]}</code>);
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

function blocks(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushPara = () => {
    if (para.length) {
      const lines = para;
      out.push(
        <p key={out.length}>
          {lines.flatMap((line, i) => (i === 0 ? inline(line) : [<br key={`br${i}`} />, ...inline(line)]))}
        </p>,
      );
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      const items = list.items.map((item, i) => <li key={i}>{inline(item)}</li>);
      out.push(list.ordered ? <ol key={out.length}>{items}</ol> : <ul key={out.length}>{items}</ul>);
      list = null;
    }
  };

  for (const line of text.split("\n")) {
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    const heading = HEADING.exec(line);

    if (!line.trim()) {
      flushPara();
      flushList();
    } else if (heading) {
      flushPara();
      flushList();
      out.push(
        <h4 key={out.length} className="ans-h">
          {inline(heading[1]!)}
        </h4>,
      );
    } else if (bullet || numbered) {
      flushPara();
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flushList();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]!);
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return out;
}
