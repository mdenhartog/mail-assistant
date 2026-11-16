import { useEffect } from "react";
import type { ReactElement } from "react";
import { useBlocker } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";

/**
 * While `dirty`, leaving the page asks first: a router navigation opens the dialog, closing or reloading
 * the tab shows the browser's own prompt. Nothing is written to browser storage.
 */
export function LeaveGuard({ dirty }: { dirty: boolean }): ReactElement {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (!dirty) {
      return undefined;
    }
    const warn = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty]);
  return (
    <ConfirmDialog
      cancelLabel="Keep editing"
      confirmLabel="Leave"
      onCancel={() => {
        blocker.reset?.();
      }}
      onConfirm={() => {
        blocker.proceed?.();
      }}
      open={blocker.state === "blocked"}
      title="You have changes that are not saved. Leave without saving?"
      tone="danger"
    >
      <p>Your edits to the categories will be lost.</p>
    </ConfirmDialog>
  );
}
