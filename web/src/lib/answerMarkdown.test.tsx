import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AnswerMarkdown } from "./answerMarkdown";

const html = (text: string) => renderToStaticMarkup(<AnswerMarkdown text={text} />);

describe("AnswerMarkdown", () => {
  it("renders bold and italic instead of showing the asterisks", () => {
    expect(html("**Arming.** Remove the *pin* first")).toBe(
      "<p><strong>Arming.</strong> Remove the <em>pin</em> first</p>",
    );
  });

  it("splits paragraphs on blank lines and keeps single line breaks", () => {
    expect(html("One\nstill one\n\nTwo")).toBe("<p>One<br/>still one</p><p>Two</p>");
  });

  it("renders bullet and numbered lists", () => {
    expect(html("- first\n- **second**")).toBe(
      "<ul><li>first</li><li><strong>second</strong></li></ul>",
    );
    expect(html("1. open\n2. check")).toBe("<ol><li>open</li><li>check</li></ol>");
  });

  it("renders a heading line as a strong heading, and inline code", () => {
    expect(html("## Exits\nUse `L1`")).toBe('<h4 class="ans-h">Exits</h4><p>Use <code>L1</code></p>');
  });

  it("never lets model output become markup", () => {
    const out = html('<img src=x onerror="alert(1)"> **ok**');
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
    expect(out).toContain("<strong>ok</strong>");
  });

  it("leaves unmatched asterisks and plain numbers alone", () => {
    expect(html("A-320 has 4 exits * 2 sides")).toBe("<p>A-320 has 4 exits * 2 sides</p>");
    expect(html("Rows 12/13 (1.1.2–1.1.7)")).toBe("<p>Rows 12/13 (1.1.2–1.1.7)</p>");
  });
});
