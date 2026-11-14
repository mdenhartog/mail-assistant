import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

import {
  axeProblems,
  buttonBoxes,
  focusRingReport,
  layoutProblems,
  motionProblems,
  overflowProblem,
  SCHEMES,
  settle,
  targetProblems,
  useDoubleText,
  VIEWPORTS,
} from "./support/checks";
import { allStates } from "./support/states";
import { held, reply, sequence, STORED, stubApi } from "./support/stubs";

// The `ui-states` project: every state of the login and settings pages against a stubbed API (route.fulfill,
// no backend). This is the one place for pixel, contrast, overflow and target checks (AC-22, AC-23).

const STATES = allStates();

for (const viewport of VIEWPORTS) {
  for (const scheme of SCHEMES) {
    test.describe(`${String(viewport.width)} px, ${scheme}`, () => {
      for (const state of STATES) {
        test(`${state.name}: no overflow, no axe violation, targets big enough`, async ({ page }) => {
          await page.setViewportSize(viewport);
          await page.emulateMedia({ colorScheme: scheme });
          const release = await state.open(page);
          await settle(page);

          expect.soft(await overflowProblem(page), "AC-22 horizontal scroll").toBeNull();
          expect.soft(await axeProblems(page), "AC-22 axe with colour contrast").toEqual([]);
          if (scheme === "light") {
            expect.soft(await targetProblems(page, viewport.touch), "AC-23 target size and spacing").toEqual([]);
          }
          release();
        });
      }
    });
  }

  test.describe(`${String(viewport.width)} px at 200 % text`, () => {
    for (const state of STATES) {
      test(`${state.name}: nothing is clipped or overlaps`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await useDoubleText(page);
        const release = await state.open(page);
        await settle(page);

        expect.soft(await overflowProblem(page), "AC-22 horizontal scroll").toBeNull();
        expect.soft(await layoutProblems(page), "AC-22 clipping and overlap").toEqual([]);
        expect.soft(await axeProblems(page), "AC-22 axe").toEqual([]);
        release();
      });
    }
  });
}

test.describe("200 % text at 320 px: the buttons stack with the primary one first", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await useDoubleText(page);
  });

  const EXPECTED_ORDER: Record<string, string[]> = {
    "login: step 2": ["Sign in"],
    "settings: dirty": ["Save changes", "Reset to defaults"],
    "settings: loaded": ["Save changes", "Reset to defaults"],
  };
  for (const [name, order] of Object.entries(EXPECTED_ORDER)) {
    test(name, async ({ page }) => {
      const state = STATES.find((candidate) => candidate.name === name);
      await state?.open(page);
      await settle(page);

      const boxes = await buttonBoxes(page);
      const own = boxes.filter((box) => box.name !== "Sign out");
      expect(own.slice(0, order.length).map((box) => box.name)).toEqual(order);
      for (const [index, box] of own.entries()) {
        const previous = own[index - 1];
        if (previous) {
          expect(box.top, `${box.name} sits below ${previous.name}`).toBeGreaterThanOrEqual(previous.bottom - 1);
        }
      }
    });
  }
});

async function tabTo(page: Page, target: Locator): Promise<void> {
  for (let press = 0; press < 40; press += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) {
      return;
    }
    await page.keyboard.press("Tab");
  }
  throw new Error("The control was not reached with Tab");
}

test("the stubbed sign-in to saved flow works with the keyboard only, and focus lands on the first invalid field", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await stubApi(page, {
    putSettings: sequence(
      reply(422, {
        problems: [
          { field: "overviewAt", rule: "overview_in_quiet_hours", value: "23:30", example: "For example 18:00" },
          { field: "remindAt", rule: "remind_in_quiet_hours", value: "06:00", example: "For example 09:00" },
        ],
      }),
      reply(200, { ...STORED, version: 4, updatedAt: "2026-11-12T20:42:00Z", updatedVia: "web" }),
    ),
  });
  await page.goto("/login");

  await tabTo(page, page.getByLabel("Username"));
  await page.keyboard.type("marco");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Code")).toBeFocused();
  await page.keyboard.type("123456");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();

  await tabTo(page, page.getByLabel("Remind-me-later default"));
  await page.keyboard.press("ArrowUp");
  await tabTo(page, page.getByRole("button", { name: "Save changes" }));
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Daily overview")).toBeFocused();
  await expect(page.getByLabel("Daily overview")).toHaveAttribute("aria-invalid", "true");

  await page.keyboard.press("ArrowUp");
  await tabTo(page, page.getByRole("button", { name: "Save changes" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText(/^Saved at/)).toBeVisible();
});

test.describe("the reset confirmation", () => {
  test("two buttons in greyscale differ by label, border and weight, not by colour alone", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await STATES.find((state) => state.name === "settings: reset confirmation")?.open(page);
    await page.addStyleTag({ content: "html { filter: grayscale(1); }" });

    const look = async (name: string): Promise<{ label: string; border: string; weight: string }> =>
      page.getByRole("button", { name }).evaluate((element) => {
        const style = getComputedStyle(element);
        return { label: element.textContent, border: style.borderTopWidth, weight: style.fontWeight };
      });
    const safe = await look("Keep my settings");
    const destructive = await look("Replace my settings with defaults");

    expect(destructive.label).not.toBe(safe.label);
    expect(destructive.border).not.toBe(safe.border);
    expect(destructive.weight).not.toBe(safe.weight);
  });

  test("Tab stays inside the dialog and Escape returns focus to Reset to defaults", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await STATES.find((state) => state.name === "settings: reset confirmation")?.open(page);

    for (let press = 0; press < 6; press += 1) {
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => document.activeElement?.closest("dialog") !== null)).toBe(true);
    }
    for (let press = 0; press < 3; press += 1) {
      await page.keyboard.press("Shift+Tab");
      expect(await page.evaluate(() => document.activeElement?.closest("dialog") !== null)).toBe(true);
    }
    await page.keyboard.press("Escape");

    await expect(page.getByRole("alertdialog")).toBeHidden();
    await expect(page.getByRole("button", { name: "Reset to defaults" })).toBeFocused();
  });

  test("the page behind the dialog cannot be reached by click or focus", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    const stub = await stubApi(page, { signedIn: true });
    await page.goto("/settings");
    await page.getByRole("button", { name: "Reset to defaults" }).click();

    await page.getByLabel("Daily overview").focus();
    await expect(page.getByLabel("Daily overview")).not.toBeFocused();
    await expect(page.getByRole("button", { name: "Keep my settings" })).toBeFocused();
    expect(stub.calls.resetSettings).toBe(0);
  });
});

const FOCUS_PAGES = ["login: step 1", "login: step 2", "settings: loaded", "settings: reset confirmation", "settings: conflict", "refused (403)", "not found"];

for (const viewport of [VIEWPORTS[1], VIEWPORTS[3]]) {
  for (const scheme of SCHEMES) {
    test.describe(`focus rings at ${String(viewport.width)} px, ${scheme}`, () => {
      for (const name of FOCUS_PAGES) {
        test(name, async ({ page }) => {
          await page.setViewportSize(viewport);
          await page.emulateMedia({ colorScheme: scheme });
          await STATES.find((state) => state.name === name)?.open(page);
          await settle(page);

          const report = await focusRingReport(page);
          expect(report.problems, `tab stops: ${report.stops.join(", ")}`).toEqual([]);
        });
      }
    });
  }
}

test("a slow save disables Save and a second activation sends no second request", async ({ page }) => {
  const gate = held(reply(200, { ...STORED, version: 4 }));
  const stub = await stubApi(page, { signedIn: true, putSettings: gate.handler });
  await page.goto("/settings");
  await page.getByLabel("Remind-me-later default").fill("10:30");
  const save = page.getByRole("button", { name: "Save changes" });
  await save.focus();
  await page.keyboard.press("Enter");

  const saving = page.getByRole("button", { name: "Saving..." });
  await expect(saving).toHaveAttribute("aria-disabled", "true");
  await expect(saving).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Space");
  await settle(page);
  expect(stub.calls.putSettings).toBe(1);

  gate.release();
  await expect(page.getByText(/^Saved at/)).toBeVisible();
  expect(stub.calls.putSettings).toBe(1);
});

test.describe("reduced motion", () => {
  for (const state of STATES) {
    test(`${state.name}: no animation or transition runs`, async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const release = await state.open(page);

      expect(await motionProblems(page)).toEqual([]);
      release();
    });
  }
});
