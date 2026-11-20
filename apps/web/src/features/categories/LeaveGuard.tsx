import { useEffect } from "react";
import type { ReactElement } from "react";
import { useBlocker } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { paths } from "@/router/paths";

/**
 * While `dirty`, leaving the page asks first: a router navigation opens the dialog, closing or reloading
 * the tab shows the browser's own prompt. Nothing is written to browser storage.
 */
export function LeaveGuard({ dirty }: { dirty: boolean }): ReactElement {
  // The sign-in page is where an ended session or the web lock sends the user (AC-32); that must never wait for a question.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && currentLocation.pathname !== nextLocation.pathname && nextLocation.pathname !== paths.login,
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
