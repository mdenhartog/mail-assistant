import { useState } from "react";

import type { CategoryProblem, SaveOutcome } from "@/api/categories/categories.types";
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

/** What the api said about the two label names. */
interface NameErrors {
  archive?: string | undefined;
  other?: string | undefined;
}

export interface Feedback {
  errors: ErrorsByRow;
  instructionsError: string | undefined;
  /** What the api said about the archive label name. */
  archiveError: string | undefined;
  /** What the api said about the name of the "Other" label. */
  otherError: string | undefined;
  errorStamp: number;
  result: SaveResult;
  setResult: (result: SaveResult) => void;
  /** Shows the errors of a refused save or check; `instructions` is the text for the list's instructions field. */
  show: (errors: ErrorsByRow, instructions?: string, names?: NameErrors) => void;
  clearAll: () => void;
  clearFor: (key: string) => void;
  clearInstructions: () => void;
  clearArchive: () => void;
  clearOther: () => void;
}

/** The field errors and the result banner; the errors start over when the stored version changes. */
export function useFeedback(version: number): Feedback {
  const [errors, setErrors] = useState<ErrorsByRow>({});
  const [instructionsError, setInstructionsError] = useState<string | undefined>(undefined);
  const [archiveError, setArchiveError] = useState<string | undefined>(undefined);
  const [otherError, setOtherError] = useState<string | undefined>(undefined);
  const [errorStamp, setErrorStamp] = useState(0);
  const [result, setResult] = useState<SaveResult>(null);
  const [seen, setSeen] = useState(version);
  if (seen !== version) {
    setSeen(version);
    setErrors({});
    setInstructionsError(undefined);
    setArchiveError(undefined);
    setOtherError(undefined);
  }
  return {
    errors,
    instructionsError,
    archiveError,
    otherError,
    errorStamp,
    result,
    setResult,
    show: (next, instructions, names) => {
      setErrors(next);
      setInstructionsError(instructions);
      setArchiveError(names?.archive);
      setOtherError(names?.other);
      setErrorStamp((stamp) => stamp + 1);
    },
    clearAll: () => {
      setErrors({});
      setInstructionsError(undefined);
      setArchiveError(undefined);
      setOtherError(undefined);
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
    clearOther: () => {
      setOtherError(undefined);
      setResult(result === "saved" ? null : result);
    },
  };
}

/** The reason the api gave for each of the two label names, in plain words. */
function nameErrorsOf(problems: readonly CategoryProblem[]): NameErrors {
  const archive = problems.find((problem) => problem.field === "archive_label");
  const other = problems.find((problem) => problem.field === "other_label");
  return { archive: archive && problemText(archive.rule), other: other && problemText(other.rule) };
}

export function showFailure(outcome: SaveOutcome, rows: readonly Row[], feedback: Feedback): void {
  const problems = outcome.kind === "invalid" ? outcome.problems : [];
  const mapped = errorsOf(problems, rows);
  const instructions = problems.some((problem) => problem.field === "instructions") ? problemText("instructions_too_long") : undefined;
  const names = nameErrorsOf(problems);
  if (Object.keys(mapped).length > 0 || instructions !== undefined || names.archive !== undefined || names.other !== undefined) {
    feedback.show(mapped, instructions, names);
  } else {
    feedback.setResult(resultOf(outcome));
  }
}
