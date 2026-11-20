import { useEffect, useId, useRef } from "react";
import type { KeyboardEvent, ReactElement, ReactNode, RefObject } from "react";

import { Button } from "@/components/Button";

export type ConfirmTone = "safe" | "danger";

export interface ConfirmDialogProps {
  /** While false nothing is rendered. */
  open: boolean;
  title: string;
  /** `danger` for a choice that replaces or discards (red button); `safe` for one that only renames or moves labels. */
  tone: ConfirmTone;
  /** The confirming choice; it says what will happen, not "OK". */
  confirmLabel: string;
  /** The safe choice; it has the initial focus. */
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** What the choice does, read out with the title. */
  children: ReactNode;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/** Tab and Shift+Tab turn round over every focusable element inside the dialog; the page behind it is inert. */
function keepFocusInside(event: KeyboardEvent<HTMLDialogElement>): void {
  const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE));
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const target = event.shiftKey ? last : first;
  const edge = event.shiftKey ? first : last;
  if (target && document.activeElement === edge) {
    event.preventDefault();
    target.focus();
  }
}

/**
 * Opens as a native modal while mounted: focus starts on the cancel button (the first button), and when it
 * goes away focus returns to whatever opened it.
 */
function useModal(): RefObject<HTMLDialogElement | null> {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const opener = document.activeElement;
    const element = dialog.current;
    element?.showModal();
    element?.querySelector<HTMLElement>("[data-initial-focus]")?.focus();
    return () => {
      if (element?.open) {
        element.close();
      }
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus();
      }
    };
  }, []);
  return dialog;
}

function OpenDialog({ title, tone, confirmLabel, cancelLabel, onConfirm, onCancel, children }: Omit<ConfirmDialogProps, "open">): ReactElement {
  const titleId = useId();
  const descriptionId = useId();
  const dialog = useModal();
  const handleKeyDown = (event: KeyboardEvent<HTMLDialogElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    } else if (event.key === "Tab") {
      keepFocusInside(event);
    }
  };
  return (
    <dialog
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      className="m-auto max-h-11/12 w-11/12 max-w-md overflow-y-auto rounded-card bg-surface-raised p-6 text-text shadow-soft backdrop:bg-text/50"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      onKeyDown={handleKeyDown}
      ref={dialog}
      role="alertdialog"
    >
      <h2 className="font-display text-xl text-text" id={titleId}>
        {title}
      </h2>
      <div className="mt-3 text-text" id={descriptionId}>
        {children}
      </div>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button className="py-2" data-initial-focus onClick={onCancel} variant="secondary">
          {cancelLabel}
        </Button>
        <Button className="py-2" onClick={onConfirm} variant={tone === "danger" ? "danger" : "primary"}>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}

/**
 * Asks before something that replaces what the user has. A native `<dialog>` opened with `showModal`:
 * the page behind it is inert, Escape and the safe button cancel, no click outside is needed.
 *
 * @example
 * <ConfirmDialog cancelLabel="Keep" confirmLabel="Replace" onCancel={close} onConfirm={go} open={asking} title="Replace?" tone="danger">
 *   <p>This replaces what you have.</p>
 * </ConfirmDialog>
 */
export function ConfirmDialog({ open, ...rest }: ConfirmDialogProps): ReactElement | null {
  return open ? <OpenDialog {...rest} /> : null;
}
