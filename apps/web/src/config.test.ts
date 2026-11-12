import { readFileSync } from "node:fs";
import { join } from "node:path";

function read(relative: string): string {
  return readFileSync(join(import.meta.dirname, relative), "utf8");
}

describe("build configuration", () => {
  it("given the Vitest config, when read, then every coverage threshold is 90", () => {
    const source = read("../vite.config.ts");

    for (const metric of ["lines", "branches", "functions", "statements"]) {
      expect(source).toContain(`${metric}: 90`);
    }
  });

  it("given index.html and the CSS, when read, then lang is en and no URL leaves the origin", () => {
    const html = read("../index.html");
    const css = `${read("./index.css")}\n${read("../../../packages/tokens/tokens.css")}`;

    expect(html).toMatch(/<html lang="en"/);
    expect(html).not.toMatch(/(?:src|href)="(?:https?:)?\/\//);
    expect(css).not.toMatch(/url\(\s*["']?(?:https?:)?\/\//);
    expect(css).not.toMatch(/@import\s+(?:url\()?["']?https?:/);
  });
});
