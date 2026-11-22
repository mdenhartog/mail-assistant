import { useState } from "react";

import { classifyFileError } from "@/api/categories/upload.api";
import type { FileFailure, UploadPreview, UploadProblem } from "@/api/categories/upload.types";
import { useConfirmUpload, useRestorePrevious, useUploadFile } from "@/api/categories/upload.queries";

/** What the page says when nothing was replaced; every one names the reason and that nothing changed. */
export type NoticeKind = "too-large" | "not-yaml" | "rate-limited" | "failed" | "changed" | "replace-failed" | "restore-failed";

type Phase =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "preview"; preview: UploadPreview }
  | { kind: "refused"; problems: UploadProblem[] }
  | { kind: "notice"; notice: NoticeKind }
  | { kind: "replaced" }
  | { kind: "restoring" }
  | { kind: "restored" };

export interface UploadFlow {
  phase: Phase;
  /** True while a confirm is on its way. */
  replacing: boolean;
  choose: (file: File) => void;
  cancel: () => void;
  replace: () => void;
  restore: () => void;
}

function noticeOf(failure: FileFailure, otherwise: NoticeKind): NoticeKind {
  switch (failure.kind) {
    case "conflict":
      return "changed";
    case "too-large":
    case "not-yaml":
    case "rate-limited":
      return failure.kind;
    default:
      return otherwise;
  }
}

/** The steps of an upload: choose a file, see the preview, replace the list, restore the previous version. */
export function useUploadFlow(version: number): UploadFlow {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const upload = useUploadFile();
  const confirm = useConfirmUpload();
  const restoring = useRestorePrevious();

  return {
    phase,
    replacing: confirm.isPending,
    choose: (file) => {
      setPhase({ kind: "checking" });
      upload.mutate(file, {
        onSuccess: (preview) => {
          setPhase({ kind: "preview", preview });
        },
        onError: (error) => {
          const failure = classifyFileError(error);
          setPhase(
            failure.kind === "invalid" ? { kind: "refused", problems: failure.problems } : { kind: "notice", notice: noticeOf(failure, "failed") },
          );
        },
      });
    },
    cancel: () => {
      setPhase({ kind: "idle" });
    },
    replace: () => {
      if (phase.kind !== "preview") {
        return;
      }
      confirm.mutate(
        { previewId: phase.preview.previewId, fileHash: phase.preview.fileHash },
        {
          onSuccess: () => {
            setPhase({ kind: "replaced" });
          },
          onError: (error) => {
            setPhase({ kind: "notice", notice: noticeOf(classifyFileError(error), "replace-failed") });
          },
        },
      );
    },
    restore: () => {
      setPhase({ kind: "restoring" });
      restoring.mutate(version, {
        onSuccess: () => {
          setPhase({ kind: "restored" });
        },
        onError: (error) => {
          setPhase({ kind: "notice", notice: noticeOf(classifyFileError(error), "restore-failed") });
        },
      });
    },
  };
}
