import { useState } from "react";

import type { SaveOutcome } from "@/api/categories/categories.types";
import { problemText } from "@/features/categories/problemText";
import type { Row } from "@/features/categories/rows";
import { errorsOf } from "@/features/categories/saveErrors";
import type { ErrorsByRow } from "@/features/categories/saveErrors";

/** What the last save left on the page (nothing while a save is in flight). */
export type SaveResult = "saved" | "conflict" | "rate-limited" | "failed" | "refused" | null;

/** What a save that stored nothing leaves on the page when no field is to blame. */
function resultOf(outcome: SaveOutcome): SaveResult {
  return outcome.kind === "invalid" ? "refused" : outcome.kind;
}

export interface Feedback {
  errors: ErrorsByRow;
  instructionsError: string | undefined;
  /** What the api said about the archive label name. */
  archiveError: string | undefined;
  errorStamp: number;
  result: SaveResult;
  setResult: (result: SaveResult) => void;
  /** Shows the errors of a refused save or check; `instructions` is the text for the list's instructions field. */
  show: (errors: ErrorsByRow, instructions?: string, archive?: string) => void;
  clearAll: () => void;
  clearFor: (key: string) => void;
  clearInstructions: () => void;
  clearArchive: () => void;
}

/** The field errors and the result banner; the errors start over when the stored version changes. */
export function useFeedback(version: number): Feedback {
  const [errors, setErrors] = useState<ErrorsByRow>({});
  const [instructionsError, setInstructionsError] = useState<string | undefined>(undefined);
  const [archiveError, setArchiveError] = useState<string | undefined>(undefined);
  const [errorStamp, setErrorStamp] = useState(0);
  const [result, setResult] = useState<SaveResult>(null);
  const [seen, setSeen] = useState(version);
  if (seen !== version) {
    setSeen(version);
    setErrors({});
    setInstructionsError(undefined);
    setArchiveError(undefined);
  }
  return {
    errors,
    instructionsError,
    archiveError,
    errorStamp,
    result,
    setResult,
    show: (next, instructions, archive) => {
      setErrors(next);
      setInstructionsError(instructions);
      setArchiveError(archive);
      setErrorStamp((stamp) => stamp + 1);
    },
    clearAll: () => {
      setErrors({});
      setInstructionsError(undefined);
      setArchiveError(undefined);
    },
    clearFor: (key) => {
      setErrors((current) => Object.fromEntries(Object.entries(current).filter(([other]) => other !== key)));
      setResult(result === "saved" ? null : result);
    },
    clearInstructions: () => {
      setInstructionsError(undefined);
      setResult(result === "saved" ? null : result);
    },
    clearArchive: () => {
      setArchiveError(undefined);
      setResult(result === "saved" ? null : result);
    },
  };
}

export function showFailure(outcome: SaveOutcome, rows: readonly Row[], feedback: Feedback): void {
  const problems = outcome.kind === "invalid" ? outcome.problems : [];
  const mapped = errorsOf(problems, rows);
  const instructions = problems.some((problem) => problem.field === "instructions") ? problemText("instructions_too_long") : undefined;
  const archive = problems.find((problem) => problem.field === "archive_label");
  const archiveText = archive === undefined ? undefined : problemText(archive.rule);
  if (Object.keys(mapped).length > 0 || instructions !== undefined || archiveText !== undefined) {
    feedback.show(mapped, instructions, archiveText);
  } else {
    feedback.setResult(resultOf(outcome));
  }
}
