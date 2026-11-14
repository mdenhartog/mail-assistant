/**
 * jsdom has no modal `<dialog>` behaviour. This gives it the part the app relies on: `showModal` opens the
 * dialog and `close` closes it and fires `close`. Focus trapping and the inert page behind it are the
 * browser's job; the Playwright `ui-states` project checks them for real.
 */
export function installDialogPolyfill(): void {
  const proto = HTMLDialogElement.prototype;
  if (typeof proto.showModal !== "function") {
    proto.showModal = function showModal(this: HTMLDialogElement): void {
      this.setAttribute("open", "");
    };
  }
  if (typeof proto.close !== "function") {
    proto.close = function close(this: HTMLDialogElement): void {
      if (this.hasAttribute("open")) {
        this.removeAttribute("open");
        this.dispatchEvent(new Event("close"));
      }
    };
  }
}
