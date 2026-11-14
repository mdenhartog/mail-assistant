import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

/** The four widths of AC-22. Below 1280 px the page is used by touch. */
export const VIEWPORTS = [
  { width: 320, height: 640, touch: true },
  { width: 375, height: 667, touch: true },
  { width: 768, height: 1024, touch: true },
  { width: 1280, height: 800, touch: false },
] as const;



export const SCHEMES = ["light", "dark"] as const;

/** Waits for web fonts and for finite animations (a banner rising in) so a check never sees a half-faded box. */
export async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity))
        .map((animation) => animation.finished),
    );
  });
}

/** Text 200 % larger, as the browser's text-size setting does for rem-based layouts. */
export async function useDoubleText(page: Page): Promise<void> {
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const style = document.createElement("style");
      style.textContent = "html { font-size: 200%; }";
      document.head.append(style);
    });
  });
}

/** AC-22: the page is never wider than the window. Returns a problem text, or null. */
export async function overflowProblem(page: Page): Promise<string | null> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    clientWidth: document.documentElement.clientWidth,
  }));
  return scrollWidth > clientWidth ? `scrollWidth ${String(scrollWidth)} > clientWidth ${String(clientWidth)}` : null;
}

/** Every axe rule, colour contrast included; each violation is "id: first selectors". */
export async function axeProblems(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations.map(
    (violation) => `${violation.id}: ${violation.nodes.slice(0, 3).map((node) => node.target.join(" ")).join(" | ")}`,
  );
}

/** Targets of at least 24 px (44 px by touch) and 8 px between neighbours (AC-23). */
export async function targetProblems(page: Page, touch: boolean): Promise<string[]> {
  return page.evaluate((minimum) => {
    const selector =
      'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=combobox], [role=option], [role=button], [tabindex]:not([tabindex="-1"])';
    const label = (element: Element): string => {
      const text = (element.getAttribute("aria-label") ?? (element as HTMLInputElement).labels?.[0]?.textContent ?? element.textContent).trim().slice(0, 30);
      return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""} "${text}"`;
    };
    // With a modal dialog open only the dialog can be reached; the page behind it is inert.
    const modal = document.querySelector("dialog[open]");
    const found = [...document.querySelectorAll(selector)]
      .filter((element) => modal === null || modal.contains(element))
      .map((element) => ({ element, box: element.getBoundingClientRect() }))
      .filter(({ box }) => box.width > 1 && box.height > 1);
    const tooSmall = found
      .filter(({ box }) => box.width < minimum || box.height < minimum)
      .map(({ element, box }) => `${label(element)} is ${box.width.toFixed(1)}x${box.height.toFixed(1)}, below ${String(minimum)}`);
    const isOption = (element: Element): boolean => element.getAttribute("role") === "option";
    const gap = (a: DOMRect, b: DOMRect): number =>
      Math.hypot(Math.max(0, a.left - b.right, b.left - a.right), Math.max(0, a.top - b.bottom, b.top - a.bottom));
    const tooClose: string[] = [];
    for (const [i, a] of found.entries()) {
      for (const b of found.slice(i + 1)) {
        const skip = a.element.contains(b.element) || b.element.contains(a.element) || isOption(a.element) || isOption(b.element);
        if (!skip && gap(a.box, b.box) < 8) {
          tooClose.push(`${label(a.element)} and ${label(b.element)} are ${gap(a.box, b.box).toFixed(1)} px apart`);
        }
      }
    }
    return [...tooSmall, ...tooClose];
  }, touch ? 44 : 24);
}

/** Nothing clipped, nothing outside the window, no two pieces of text or controls on top of each other. */
export async function layoutProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const label = (element: Element): string => `${element.tagName.toLowerCase()} "${element.textContent.trim().slice(0, 30)}"`;
    const clipping = ["hidden", "clip", "auto", "scroll"];
    const modal = document.querySelector("dialog[open]");
    const visible = [...document.body.querySelectorAll("*")].filter((element) => {
      const box = element.getBoundingClientRect();
      return (modal === null || modal.contains(element)) && box.width > 1 && box.height > 1 && getComputedStyle(element).visibility === "visible" && !element.closest("[role=listbox]");
    });
    const outside = (element: Element): string[] => {
      const box = element.getBoundingClientRect();
      const inside = box.left >= -1 && box.right <= document.documentElement.clientWidth + 1;
      return inside ? [] : [`${label(element)} sticks out of the window (${box.left.toFixed(0)}..${box.right.toFixed(0)})`];
    };
    const clipped = (element: Element): string[] => {
      const style = getComputedStyle(element);
      const clips = clipping.includes(style.overflowX) || clipping.includes(style.overflowY);
      // A modal dialog that is taller than a small window scrolls on purpose; its content is reached by scrolling.
      const control = element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLDialogElement;
      const cut = element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1;
      return clips && !control && cut ? [`${label(element)} clips its content`] : [];
    };
    const hasText = (element: Element): boolean =>
      [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && (node.textContent ?? "").trim() !== "");
    const carriers = visible.filter(
      (element) => element.matches("button, a[href], input, select, label, legend, h1, h2, p, time, strong, [role=combobox]") || hasText(element),
    );
    const overlap = (a: Element, b: Element): boolean => {
      const boxA = a.getBoundingClientRect();
      const boxB = b.getBoundingClientRect();
      const x = Math.min(boxA.right, boxB.right) - Math.max(boxA.left, boxB.left);
      const y = Math.min(boxA.bottom, boxB.bottom) - Math.max(boxA.top, boxB.top);
      return x > 1 && y > 1;
    };
    const overlaps: string[] = [];
    for (const [i, a] of carriers.entries()) {
      for (const b of carriers.slice(i + 1)) {
        if (!a.contains(b) && !b.contains(a) && overlap(a, b)) {
          overlaps.push(`${label(a)} overlaps ${label(b)}`);
        }
      }
    }
    return [...visible.flatMap(outside), ...visible.flatMap(clipped), ...overlaps];
  });
}

/** The buttons of the page in DOM order with their boxes, for the stacking check. */
export async function buttonBoxes(page: Page): Promise<{ name: string; top: number; bottom: number }[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll("main button")]
      .map((element) => ({ name: element.textContent.trim(), box: element.getBoundingClientRect() }))
      .filter(({ box }) => box.width > 1)
      .map(({ name, box }) => ({ name, top: box.top, bottom: box.bottom })),
  );
}

export interface FocusReport {
  problems: string[];
  /** Tab stops visited, in order. */
  stops: string[];
}

/** Tabs through the page once; every stop needs the focus outline in the token colour (AC-23) and all controls must be reached. */
export async function focusRingReport(page: Page): Promise<FocusReport> {
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
  });
  const stops: string[] = [];
  const problems: string[] = [];
  const expected = await page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.color = "var(--color-focus)";
    document.body.append(probe);
    const colour = getComputedStyle(probe).color;
    probe.remove();
    return colour;
  });
  for (let press = 0; press < 80; press += 1) {
    await page.keyboard.press("Tab");
    const stop = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) {
        return null;
      }
      const style = getComputedStyle(element);
      return {
        name: `${element.tagName.toLowerCase()} "${(element.getAttribute("aria-label") ?? (element as HTMLInputElement).labels?.[0]?.textContent ?? element.textContent).trim().slice(0, 30)}"`,
        width: parseFloat(style.outlineWidth),
        style: style.outlineStyle,
        colour: style.outlineColor,
      };
    });
    if (stop === null) {
      continue; // focus left the page (document start or browser UI): keep tabbing
    }
    if (stop.name === stops.at(-1)) {
      continue; // a time field has a Tab stop per segment: the same control again
    }
    if (stops.includes(stop.name)) {
      break;
    }
    stops.push(stop.name);
    if (!(stop.width > 0) || stop.style === "none") {
      problems.push(`${stop.name} has no focus outline`);
    } else if (stop.colour !== expected) {
      problems.push(`${stop.name} outline is ${stop.colour}, not the focus token ${expected}`);
    }
  }
  const unreached = await page.evaluate((reached) => {
    const selector =
      'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const modal = document.querySelector("dialog[open]");
    return [...document.querySelectorAll(selector)]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        return (modal === null || modal.contains(element)) && box.width > 1 && box.height > 1;
      })
      .map((element) => `${element.tagName.toLowerCase()} "${(element.getAttribute("aria-label") ?? (element as HTMLInputElement).labels?.[0]?.textContent ?? element.textContent).trim().slice(0, 30)}"`)
      .filter((name) => !reached.includes(name));
  }, stops);
  problems.push(...unreached.map((name) => `${name} was not reached with Tab`));
  return { problems, stops };
}

/** Under `prefers-reduced-motion: reduce` nothing animates or transitions (AC-23). */
export async function motionProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const seconds = (list: string): number[] => list.split(",").map((part) => parseFloat(part));
    const problems: string[] = [];
    for (const element of document.querySelectorAll("*")) {
      const style = getComputedStyle(element);
      const longest = Math.max(...seconds(style.animationDuration), ...seconds(style.transitionDuration));
      if (longest > 0) {
        problems.push(`${element.tagName.toLowerCase()} runs a ${String(longest)}s motion`);
      }
    }
    if (document.getAnimations().length > 0) {
      problems.push(`${String(document.getAnimations().length)} animations are running`);
    }
    return problems;
  });
}
