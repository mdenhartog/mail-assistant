import axe from "axe-core";
import { expect } from "vitest";

/**
 * Fails the test when axe-core finds accessibility violations in the rendered element.
 * Colour contrast is disabled here because jsdom has no layout; Playwright checks it in e2e.
 *
 * @example
 * await expectNoAxeViolations(render(<Card />).container);
 */
export async function expectNoAxeViolations(element: Element): Promise<void> {
  const results = await axe.run(element, { rules: { "color-contrast": { enabled: false } } });
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}
