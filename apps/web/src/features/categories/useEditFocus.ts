import { useEffect, useRef } from "react";
import type { RefObject } from "react";

/** Where focus goes when the edit view opens: its heading, a field, or the first field with an error. */
export type EditFocus = "heading" | "name" | "description" | "invalid";

function firstInvalid(view: HTMLElement | null): HTMLElement | null | undefined {
  return view?.querySelector<HTMLElement>('[aria-invalid="true"]');
}

function opening(view: HTMLElement | null, focus: EditFocus): HTMLElement | null | undefined {
  const target = focus === "invalid" ? firstInvalid(view) : view?.querySelector<HTMLElement>(`[data-field="${focus}"]`);
  return target ?? view?.querySelector<HTMLElement>('[data-field="heading"]');
}

/** Moves focus when the view opens and again each time `stamp` changes (a Save found an error). */
export function useEditFocus(root: RefObject<HTMLElement | null>, focus: EditFocus, stamp: number): void {
  const opened = useRef(false);
  const seen = useRef(stamp);
  useEffect(() => {
    const view = root.current;
    if (!opened.current) {
      opened.current = true;
      opening(view, focus)?.focus();
    } else if (stamp !== seen.current) {
      firstInvalid(view)?.focus();
    }
    seen.current = stamp;
  }, [root, focus, stamp]);
}
