import { useState } from "react";

export type CopyStatus = "idle" | "copied" | "failed";

/** Puts text on the clipboard; the text may still have to be fetched. Says in words whether it worked. */
export function useCopy(): { status: CopyStatus; copy: (text: () => Promise<string> | string) => Promise<void> } {
  const [status, setStatus] = useState<CopyStatus>("idle");
  return {
    status,
    copy: async (text) => {
      setStatus("idle");
      try {
        await navigator.clipboard.writeText(await text());
        setStatus("copied");
      } catch {
        setStatus("failed");
      }
    },
  };
}
