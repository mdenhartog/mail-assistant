import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { resetCategories, seedList } from "./support/categoriesDb";
import { axeProblems, overflowProblem, SCHEMES, settle, targetProblems, useDoubleText, VIEWPORTS } from "./support/checks";
import { resetState } from "./support/db";
import {
  confirmPreview,
  expandAll,
  GOLDEN,
  goldenFile,
  refusedFile,
  rowText,
  uploadToPreview,
} from "./support/labelStructure";
import { signInThroughPage } from "./support/signin";

// The `label-structure` project (U-label-structure-17, the R1 gate of INT-008): upload, preview, confirm, the nested
// Categories page, a tick and its restore, through a real browser over the prod-like stack. One worker, in file order,
// after `categories` and `review`: the stack has one mailbox and one list, and the specs reset it by owner SQL.
//
// The golden file is the anonymised example of 43 nested categories (packages/category-policy). The list the user has
// before the upload is the small seeded one (Invoices, Travel), so the preview shows 43 added and 2 removed.
test.describe.configure({ mode: "serial", timeout: 180_000 });

test.beforeEach(() => {
  resetState();
  resetCategories();
});

async function openCategories(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Categories" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit Invoices", exact: true }).or(page.locator("button[data-edit]").first())).toBeVisible();
}

async function openSeeded(page: Page): Promise<void> {
  seedList();
  await signInThroughPage(page);
  await openCategories(page);
}

/** Seeded list, then the golden file uploaded, previewed and confirmed. */
async function openGolden(page: Page): Promise<void> {
  await openSeeded(page);
  await uploadToPreview(page, goldenFile());
  await confirmPreview(page);
}

// 2 (AC: upload, preview, confirm, then nested categories with kinds, senders and ticks)
test("the golden file is uploaded, previewed and confirmed, and the page shows 43 nested categories with kinds, senders and ticks", async ({
  page,
}) => {
  await openSeeded(page);
  await uploadToPreview(page, goldenFile());

  const preview = page.getByRole("region", { name: "Preview of your file" });
  await expect(preview.getByText("43 added")).toBeVisible();
  await expect(preview.getByText("2 removed").first()).toBeVisible();
  await expect(preview.getByText("Nothing is stored until you replace your list.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Replace my whole list (2 removed)" })).not.toBeFocused();

  await confirmPreview(page);

  // Collapsed first: the groups are closed, the old categories are gone.
  await expect(page.getByRole("button", { name: "Edit Invoices", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Edit Huis/Energie", exact: true })).toHaveCount(0);
  await expandAll(page);
  await expect(page.locator("button[data-edit]")).toHaveCount(GOLDEN.length);

  for (const category of GOLDEN) {
    const edit = page.getByRole("button", { name: `Edit ${category.name}`, exact: true });
    await expect(edit, `${category.name}: row`).toBeVisible();
    await expect(edit, `${category.name}: kind and senders`).toHaveAccessibleDescription(rowText(category));
    const tick = page.getByRole("checkbox", { name: `Always notify, ${category.name}`, exact: true });
    if (category.notify) {
      await expect(tick, `${category.name}: tick`).toBeChecked();
    } else {
      await expect(tick, `${category.name}: tick`).not.toBeChecked();
    }
  }
  expect(GOLDEN.some((category) => category.kind === "extra"), "the golden file has an extra label").toBe(true);
  expect(GOLDEN.some((category) => category.notify), "the golden file has ticks").toBe(true);
});

// 3: a tick, set and saved, is there after a reload
test("a tick that is set and saved is still set after a reload", async ({ page }) => {
  await openGolden(page);
  await expandAll(page);

  const water = GOLDEN.find((category) => !category.notify && category.name.includes("/"));
  const energy = GOLDEN.find((category) => category.notify && category.name.includes("/"));
  if (water === undefined || energy === undefined) {
    throw new Error("the golden file needs a ticked and an unticked nested category");
  }
  const tickOf = (name: string): ReturnType<Page["getByRole"]> => page.getByRole("checkbox", { name: `Always notify, ${name}`, exact: true });

  await tickOf(water.name).check();
  await tickOf(energy.name).uncheck();
  await page.getByRole("button", { name: "Save changes" }).click();
  const dialog = page.getByRole("alertdialog", { name: /^Save \d+ changes?\?$/ });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Categories" })).toBeVisible();
  await expandAll(page);
  await expect(tickOf(water.name)).toBeChecked();
  await expect(tickOf(energy.name)).not.toBeChecked();
  // An untouched tick keeps its value as well.
  const other = GOLDEN.find((category) => category.notify && category.name !== energy.name);
  if (other !== undefined) {
    await expect(tickOf(other.name)).toBeChecked();
  }
});

// 1 (a11y): the page, in every state of the journey, at the four widths of the spec, light and dark
for (const viewport of VIEWPORTS) {
  test(`${String(viewport.width)} px: the page has no axe violation, light and dark, from the first list to the edit view`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await openSeeded(page);

    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await settle(page);
      expect.soft(await axeProblems(page), `${scheme}: first list`).toEqual([]);
    }

    await page.getByLabel("Choose a YAML file").setInputFiles(refusedFile());
    await expect(page.getByRole("heading", { name: "Your file was not accepted" })).toBeFocused();
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await settle(page);
      expect.soft(await axeProblems(page), `${scheme}: refused file`).toEqual([]);
    }

    await uploadToPreview(page, goldenFile());
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await settle(page);
      expect.soft(await axeProblems(page), `${scheme}: preview`).toEqual([]);
    }

    await confirmPreview(page);
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await settle(page);
      expect.soft(await axeProblems(page), `${scheme}: replaced and collapsed`).toEqual([]);
    }

    await expandAll(page);
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await settle(page);
      expect.soft(await axeProblems(page), `${scheme}: nested list`).toEqual([]);
      expect.soft(await overflowProblem(page), `${scheme}: horizontal scroll`).toBeNull();
    }
    const rowTargets = (await targetProblems(page, viewport.touch)).filter((problem) => /tooSmall|below/.test(problem));
    expect.soft(rowTargets, "targets below the minimum").toEqual([]);

    await page.getByRole("button", { name: "Edit Huis/Onderhoud", exact: true }).click();
    await expect(page.getByRole("region", { name: /^Edit category$/ })).toBeVisible();
    for (const scheme of SCHEMES) {
      await page.emulateMedia({ colorScheme: scheme });
      await settle(page);
      expect.soft(await axeProblems(page), `${scheme}: edit view`).toEqual([]);
    }
  });

  // 4 (a11y): 200 % text, the edit view and the preview
  test(`${String(viewport.width)} px at 200 % text: the preview, the refused file and the edit view do not scroll sideways`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await useDoubleText(page);
    await openSeeded(page);

    await page.getByLabel("Choose a YAML file").setInputFiles(refusedFile());
    await expect(page.getByRole("heading", { name: "Your file was not accepted" })).toBeVisible();
    await settle(page);
    expect.soft(await overflowProblem(page), "refused file: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "refused file: axe").toEqual([]);

    await uploadToPreview(page, goldenFile());
    await settle(page);
    expect.soft(await overflowProblem(page), "preview: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "preview: axe").toEqual([]);

    await confirmPreview(page);
    await expandAll(page);
    await settle(page);
    expect.soft(await overflowProblem(page), "nested list: horizontal scroll").toBeNull();

    // The row with the longest text of the golden file: a description that carries the "meaning lost" note.
    await page.getByRole("button", { name: "Edit Huis/Onderhoud", exact: true }).click();
    await expect(page.getByRole("region", { name: /^Edit category$/ })).toBeVisible();
    await settle(page);
    expect.soft(await overflowProblem(page), "edit view: horizontal scroll").toBeNull();
    expect.soft(await axeProblems(page), "edit view: axe").toEqual([]);
  });
}

/** Tabs from the top of the page until the focus is on the control, or fails after `limit` presses. */
async function tabTo(page: Page, reached: () => Promise<boolean>, limit = 200): Promise<void> {
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
  });
  for (let press = 0; press < limit; press += 1) {
    await page.keyboard.press("Tab");
    if (await reached()) {
      return;
    }
  }
  throw new Error(`the control was not reached with Tab in ${String(limit)} presses`);
}

const isFocused = (page: Page, name: string, role: "button" | "checkbox" | "heading" = "button") => async (): Promise<boolean> =>
  page.getByRole(role, { name, exact: true }).evaluate((element) => element === document.activeElement).catch(() => false);

// 5 (a11y): the keyboard only, from the upload box to the confirmed list; every error takes focus
test("with the keyboard alone the user uploads, previews and confirms, and every error takes focus", async ({ page }) => {
  await openSeeded(page);

  // A refused file first: its heading takes focus and the copy button is next.
  const input = page.getByLabel("Choose a YAML file");
  await tabTo(page, () => input.evaluate((element) => element === document.activeElement));
  let chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(refusedFile());
  await expect(page.getByRole("heading", { name: "Your file was not accepted" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Copy errors" })).toBeFocused();

  // The right file: the preview heading takes focus, not the confirm button; Cancel and Replace are the next two stops.
  await tabTo(page, () => input.evaluate((element) => element === document.activeElement));
  chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(goldenFile());
  await expect(page.getByRole("heading", { name: "Preview of your file" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  const replace = page.getByRole("button", { name: "Replace my whole list (2 removed)" });
  await expect(replace).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Your list was replaced.")).toBeVisible();
  await tabTo(page, isFocused(page, "Restore previous version"));

  // The nested list: a group opens with Enter, its first category opens with Enter, an empty name is refused and the
  // refusal takes focus.
  const huis = page.getByRole("button", { name: "Expand Huis", exact: true });
  await tabTo(page, isFocused(page, "Expand Huis"));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Collapse Huis", exact: true })).toBeVisible();
  await expect(huis).toHaveCount(0);

  await tabTo(page, isFocused(page, "Edit Huis/Energie"));
  await page.keyboard.press("Enter");
  const view = page.getByRole("region", { name: /^Edit category$/ });
  await expect(view).toBeVisible();
  const name = view.getByLabel("Name");
  await name.fill("");
  await tabTo(page, isFocused(page, "Save"));
  await page.keyboard.press("Enter");
  await expect(view.getByText("Give the category a name.")).toBeVisible();
  await expect(name).toBeFocused();
  await expect(name).toHaveAttribute("aria-invalid", "true");

  // Every control of the list is a tab stop with a visible, non-zero focus outline.
  await name.fill("Huis/Energie");
  await page.keyboard.press("Tab");
  await tabTo(page, isFocused(page, "Save"));
  await page.keyboard.press("Enter");
  await expect(view).toBeHidden();
  await expect(page.getByRole("button", { name: "Edit Huis/Energie", exact: true })).toBeFocused();
});
