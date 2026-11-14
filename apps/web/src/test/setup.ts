import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { installDialogPolyfill } from "@/test/dialog";

installDialogPolyfill();

afterEach(() => {
  cleanup();
  // The settings page keeps a draft of typed values in the tab's storage; no test leaves one for the next.
  window.sessionStorage.clear();
});
