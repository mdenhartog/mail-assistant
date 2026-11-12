import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import config from "../vite.config";

function read(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");
}

describe("build configuration", () => {
  it("given the Vitest config, when read, then every coverage threshold is 90", () => {
    expect(config.test?.coverage?.thresholds).toEqual({ lines: 90, branches: 90, functions: 90, statements: 90 });
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
