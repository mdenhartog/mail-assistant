import { describe, expect, it } from "vitest";

import { MAX_SENDERS, parseSenders, senderErrors, textOfSenders } from "@/features/categories/senders";

describe("sender lines", () => {
  it("writes one entry per line and marks subdomains with a trailing +subdomains", () => {
    expect(
      textOfSenders([
        { entry: "billing@example.com", subdomains: false },
        { entry: "example.nl", subdomains: true },
      ]),
    ).toBe("billing@example.com\nexample.nl +subdomains");
  });

  it("reads the same text back, skips blank lines and remembers each entry's line", () => {
    const parsed = parseSenders("billing@example.com\n\n  example.nl   +subdomains  \n");
    expect(parsed.entries).toEqual([
      { entry: "billing@example.com", subdomains: false },
      { entry: "example.nl", subdomains: true },
    ]);
    expect(parsed.lines).toEqual([1, 3]);
  });

  it("round-trips what the api returned untouched", () => {
    const senders = [
      { entry: "a@x.nl", subdomains: false },
      { entry: "x.nl", subdomains: true },
    ];
    expect(parseSenders(textOfSenders(senders)).entries).toEqual(senders);
  });

  it("reads the marker in any letter case", () => {
    expect(parseSenders("x.nl +Subdomains").entries).toEqual([{ entry: "x.nl", subdomains: true }]);
  });
});

const row = (key: string, name: string, kind: "topic" | "extra", sendersText: string): Parameters<typeof senderErrors>[1] => ({
  key,
  name,
  kind,
  sendersText,
});

describe("sender errors while typing", () => {
  const energy = row("a", "Huis/Energie", "topic", "x.nl\nenergy@y.nl");

  it("names the other category of the same kind that already has the entry, on the line of the entry", () => {
    const mine = row("b", "Huis/Water", "topic", "water@z.nl\nX.NL");
    const errors = senderErrors([energy, mine], mine);
    expect(errors).toEqual([{ line: 2, text: "X.NL is already in Huis/Energie. Remove it there first." }]);
  });

  it("lets a topic and an extra label share an entry", () => {
    const extra = row("b", "Facturen", "extra", "x.nl");
    expect(senderErrors([energy, extra], extra)).toEqual([]);
  });

  it("flags an entry written twice in the same category", () => {
    const mine = row("b", "Huis/Water", "topic", "a@z.nl\nA@Z.nl");
    expect(senderErrors([mine], mine)).toEqual([{ line: 2, text: "A@Z.nl is listed twice in this category." }]);
  });

  it("flags more than the limit", () => {
    const text = Array.from({ length: MAX_SENDERS + 1 }, (_, index) => `s${String(index)}@x.nl`).join("\n");
    const mine = row("b", "Big", "topic", text);
    expect(senderErrors([mine], mine)).toEqual([{ line: null, text: "A category can list at most 100 senders." }]);
  });
});
