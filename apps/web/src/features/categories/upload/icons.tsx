import type { ReactElement } from "react";

export type ChangeKind = "added" | "changed" | "removed";

const PATHS: Record<ChangeKind, string> = {
  added: "M12 5v14M5 12h14",
  changed: "M4 12h16M14 6l6 6-6 6",
  removed: "M5 12h14",
};

/** A mark beside the word of a change; the word carries the meaning, the shape backs it up without colour. */
export function ChangeIcon({ kind }: { kind: ChangeKind }): ReactElement {
  return (
    <svg
      aria-hidden="true"
      className="size-5 flex-none"
      fill="none"
      focusable="false"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2.5"
      viewBox="0 0 24 24"
    >
      <path d={PATHS[kind]} />
    </svg>
  );
}
