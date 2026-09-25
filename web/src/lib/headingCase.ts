/**
 * Display-time title case for the manual's all-capitals headings and
 * contents entries ("3.16 SECTION 8 SERIES O PART II (SEAT/BERTH/SEATBELT)").
 *
 * Like `displayManualText`, this changes only what is painted: `Block.text`
 * stays as the manual printed it, and citations quote the manual verbatim.
 *
 * The hard part is not lowercasing what should stay upper. A word is kept as
 * printed when it is:
 *  - an abbreviation the manual uses (below: measured from its headings and
 *    contents entries, keeping those that are not dictionary words),
 *  - alone in brackets, spelling out what came before it ("(ENDS)"),
 *  - a Roman numeral ("PART II"),
 *  - part of a code with digits ("A320", "6E", "24B"),
 *  - already mixed case ("IndiGo").
 */
const ABBREVIATIONS = new Set([
  "ABP", "ADT", "AED", "AIC", "AOC", "APU", "ASC", "ATC", "BA", "CAR", "CIDS", "COVID",
  "CPR", "CRM", "CSC", "DG", "DGCA", "DPNA", "ECAM", "EFB", "EGCA", "ELT", "ETOPS", "EVAC",
  "FAP", "FDTL", "FSB", "FWD", "IATA", "ICAO", "IFE", "LAME", "LED", "LRBL", "MEL", "MRT",
  "NEO", "OC", "PA", "PAX", "PBE", "PFMC", "PIC", "POC", "PRM", "PSU", "QDM", "RVSM", "SAFA",
  "SED", "SEP", "SG", "SIC", "SMS", "SOP", "TCAS", "UMNR", "UV", "VIP", "WCHC", "WCHR", "WCHS", "XLR",
]);

const SMALL_WORDS = new Set([
  "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "of", "on", "or",
  "per", "the", "to", "via", "vs", "with",
]);

const ROMAN = /^[IVXL]+$/;

/** Whether `text` is set in capitals -- only then is it recased. Counted by
 *  word, so one mixed-case name ("AIM OF SMS AT IndiGo") doesn't hide it. */
function shouting(text: string): boolean {
  const words = text.match(/[A-Za-z]{2,}/g) ?? [];
  if (words.length === 0) return false;
  return words.filter((w) => w === w.toUpperCase()).length / words.length >= 0.7;
}

export function titleCase(text: string): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!shouting(clean)) return clean;
  let first = true;
  return clean.replace(/[A-Za-z]+/g, (word, at: number) => {
    const before = clean[at - 1] ?? "";
    const after = clean[at + word.length] ?? "";
    // The first word of the title, or one opening a bracket or a new clause,
    // always takes a capital -- even a small word.
    const opens = first || before === "(" || /[:–—-]\s?$/.test(clean.slice(Math.max(0, at - 2), at));
    first = false;
    if (/[a-z]/.test(word)) return word;
    if (/\d/.test(before) || /\d/.test(after)) return word;
    // A lone letter after a number is part of a code ("RULE 24 A"), not "a".
    if (word.length === 1 && /\d$/.test(clean.slice(0, at).trimEnd())) return word;
    if (ABBREVIATIONS.has(word)) return word;
    // A word alone in brackets is the abbreviation it spells out: "(ENDS)".
    if (before === "(" && after === ")") return word;
    if (word.endsWith("S") && ABBREVIATIONS.has(word.slice(0, -1))) return `${word.slice(0, -1)}s`;
    if (ROMAN.test(word) && (word.length > 1 || /\bPART\s$/i.test(clean.slice(0, at)))) return word;
    const lower = word.toLowerCase();
    if (!opens && SMALL_WORDS.has(lower)) return lower;
    return lower[0]!.toUpperCase() + lower.slice(1);
  });
}

/** A heading's own number, hung in its own column, and its title. */
export function splitHeading(text: string): { number: string | null; title: string } {
  const m = /^(\d+(?:\.\d+)*)\.?\s+(\S[\s\S]*)$/.exec(text.trim());
  return m ? { number: m[1]!, title: titleCase(m[2]!) } : { number: null, title: titleCase(text) };
}
