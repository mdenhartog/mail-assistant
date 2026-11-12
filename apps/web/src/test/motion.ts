import { expect } from "vitest";

/**
 * A component sets no motion of its own under `prefers-reduced-motion` when every transition,
 * duration or animation utility on it is behind the `motion-safe:` variant. jsdom has no media
 * queries for Tailwind, so the class list is the contract.
 *
 * @example
 * expectMotionOnlyWhenSafe(screen.getByRole("button"));
 */
export function expectMotionOnlyWhenSafe(element: Element): void {
  const classes = element.className.split(/\s+/);
  expect(classes.filter((c) => /^(transition|duration|ease|animate)/.test(c))).toEqual([]);
}
