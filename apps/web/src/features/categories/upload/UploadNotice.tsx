import type { ReactElement } from "react";

import { Banner } from "@/components/Banner";
import type { NoticeKind } from "@/features/categories/upload/useUploadFlow";

const NOTICES: Record<NoticeKind, { title: string; text: string }> = {
  "too-large": { title: "The file is too large.", text: "Nothing was changed. Choose a smaller file." },
  "not-yaml": { title: "That is not a YAML file.", text: "Nothing was changed. Choose a .yaml file, such as the template." },
  "rate-limited": { title: "Too many changes to the list this hour.", text: "Nothing was changed. Wait a while and try again." },
  failed: { title: "Could not check the file. Nothing was changed.", text: "Try again in a moment." },
  changed: { title: "The list changed.", text: "Nothing was replaced. Upload the file again to see what it would change now." },
  "replace-failed": { title: "Could not replace your list. Nothing was changed.", text: "Upload the file again." },
  "restore-failed": { title: "Could not restore the previous version.", text: "Nothing was changed. Try again in a moment." },
};

/** Says why nothing was replaced; it takes focus, so a keyboard user hears it. */
export function UploadNotice({ notice }: { notice: NoticeKind }): ReactElement {
  const { title, text } = NOTICES[notice];
  return (
    <Banner focusOnMount kind={notice === "changed" ? "conflict" : "danger"} title={title}>
      {text}
    </Banner>
  );
}
