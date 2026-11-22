// Helpers for the `label-structure` project (U-label-structure-17): the anonymised golden file of 43 nested categories
// and what the page must show for it. The expected values are read from the golden file's own expectation
// (packages/category-policy/tests/fixtures/golden_example_43.expected.json), so the page is checked against the
// same oracle as the parser.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

const FIXTURES = fileURLToPath(new URL("../../../../packages/category-policy/tests/fixtures/", import.meta.url));

export interface GoldenCategory {
  name: string;
  kind: "topic" | "extra";
  notify: boolean;
  /** The number of sender entries. */
  senders: number;
}

interface GoldenExpectation {
  categories: GoldenCategory[];
}

const KIND_WORD = { topic: "Topic", extra: "Extra label" } as const;

/** The 43 categories the golden file must produce, in file order. */
export const GOLDEN: readonly GoldenCategory[] = (
  JSON.parse(readFileSync(`${FIXTURES}golden_example_43.expected.json`, "utf8")) as GoldenExpectation
).categories;

export interface UploadFile {
  name: string;
  mimeType: string;
  buffer: Buffer;
}

function fixture(relative: string): UploadFile {
  return { name: relative.split("/").at(-1) ?? relative, mimeType: "application/yaml", buffer: readFileSync(`${FIXTURES}${relative}`) };
}

export const goldenFile = (): UploadFile => fixture("golden_example_43.yaml");

/** A file the api refuses with a list of problems (an unknown field). */
export const refusedFile = (): UploadFile => fixture("hostile/unknown_field.yaml");

/** The words under a category's name in the list: its kind and its number of senders. */
export function rowText(category: GoldenCategory): RegExp {
  const senders = category.senders === 0 ? "No senders" : `${String(category.senders)} ${category.senders === 1 ? "sender" : "senders"}`;
  return new RegExp(`^${KIND_WORD[category.kind]}\\s*${senders}$`);
}

/** Opens every group of the list, children included, until no "Expand" button is left. */
export async function expandAll(page: Page): Promise<void> {
  // After a reload the heading is there before the list is: wait for a row, or the loop sees no group and stops.
  await expect(page.locator("button[data-edit]").first()).toBeVisible();
  const expanders = page.getByRole("button", { name: /^Expand / });
  for (let guard = 0; guard < 60 && (await expanders.count()) > 0; guard += 1) {
    await expanders.first().click();
  }
  await expect(expanders).toHaveCount(0);
}

/** Chooses the file in the upload box and waits for the preview, which takes focus. */
export async function uploadToPreview(page: Page, file: UploadFile): Promise<void> {
  await page.getByLabel("Choose a YAML file").setInputFiles(file);
  await expect(page.getByRole("heading", { name: "Preview of your file" })).toBeFocused();
}

/** Confirms the preview and waits until the page shows the new list. */
export async function confirmPreview(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^Replace my whole list/ }).click();
  await expect(page.getByText("Your list was replaced.")).toBeVisible();
}
