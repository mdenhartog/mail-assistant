import { useRef, useState } from "react";

import { classifySaveError } from "@/api/categories/categories.api";
import { useSaveCategories } from "@/api/categories/categories.queries";
import type { CategoryInput, CategoryList, CategoryProblem, SaveOutcome } from "@/api/categories/categories.types";
import { validateList } from "@/features/categories/policy";
import { problemText } from "@/features/categories/problemText";
import type { Row, RowField } from "@/features/categories/rows";

/** Message per card key and field; a field that is not there is fine. */
type RowErrors = Record<string, Partial<Record<RowField, string>>>;

/** What the last save left on the page (nothing while a save is in flight). */
export type SaveResult = "saved" | "conflict" | "rate-limited" | "failed" | "refused" | null;

export interface CategoriesSave {
  errors: RowErrors;
  /** Changes on every submit that shows errors, so focus moves once per submit and not while typing. */
  errorStamp: number;
  result: SaveResult;
  /** The summary dialog is open. */
  asking: boolean;
  saving: boolean;
  submit: () => void;
  confirm: () => void;
  cancel: () => void;
  /** Sends the same list again after a failure. */
  retry: () => void;
  /** Hides what the last save said, because the user is editing a card again. */
  clear: (key: string) => void;
}

function bodyOf(rows: readonly Row[]): CategoryInput[] {
  return rows.map((row) =>
    row.id === null
      ? { name: row.name, description: row.description }
      : { id: row.id, name: row.name, description: row.description },
  );
}

/** Maps problems with a card position and a text field to messages; the first problem of a field wins. */
function errorsOf(problems: readonly CategoryProblem[], rows: readonly Row[]): RowErrors {
  const errors: RowErrors = {};
  for (const problem of problems) {
    const row = problem.index === null ? undefined : rows[problem.index];
    if (row !== undefined && (problem.field === "name" || problem.field === "description")) {
      const mine = (errors[row.key] ??= {});
      mine[problem.field] ??= problemText(problem.rule);
    }
  }
  return errors;
}

/** What a save that stored nothing leaves on the page when no field is to blame. */
function resultOf(outcome: SaveOutcome): SaveResult {
  return outcome.kind === "invalid" ? "refused" : outcome.kind;
}

function showFailure(outcome: SaveOutcome, rows: readonly Row[], feedback: Feedback): void {
  const mapped = outcome.kind === "invalid" ? errorsOf(outcome.problems, rows) : {};
  if (Object.keys(mapped).length > 0) {
    feedback.show(mapped);
  } else {
    feedback.setResult(resultOf(outcome));
  }
}

interface Feedback {
  errors: RowErrors;
  errorStamp: number;
  result: SaveResult;
  setResult: (result: SaveResult) => void;
  show: (errors: RowErrors) => void;
  clearAll: () => void;
  clearFor: (key: string) => void;
}

/** The field errors and the result banner; the errors start over when the stored version changes. */
function useFeedback(version: number): Feedback {
  const [errors, setErrors] = useState<RowErrors>({});
  const [errorStamp, setErrorStamp] = useState(0);
  const [result, setResult] = useState<SaveResult>(null);
  const [seen, setSeen] = useState(version);
  if (seen !== version) {
    setSeen(version);
    setErrors({});
  }
  return {
    errors,
    errorStamp,
    result,
    setResult,
    show: (next) => {
      setErrors(next);
      setErrorStamp((stamp) => stamp + 1);
    },
    clearAll: () => {
      setErrors({});
    },
    clearFor: (key) => {
      setErrors((current) => Object.fromEntries(Object.entries(current).filter(([other]) => other !== key)));
      setResult(result === "saved" ? null : result);
    },
  };
}

/**
 * Validates the draft with the shared rules, asks with a summary, then saves it on the version it was
 * based on. The api checks again: its 422 is mapped to the same fields.
 */
export function useCategoriesSave(list: CategoryList, rows: readonly Row[]): CategoriesSave {
  const [asking, setAsking] = useState(false);
  const feedback = useFeedback(list.version);
  const { setResult } = feedback;
  const save = useSaveCategories();
  const inFlight = useRef(false);

  const send = (): void => {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setResult(null);
    feedback.clearAll();
    save.mutate(
      { version: list.version, categories: bodyOf(rows) },
      {
        onSuccess: () => {
          setResult("saved");
        },
        onError: (error) => {
          showFailure(classifySaveError(error), rows, feedback);
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  };

  const submit = (): void => {
    if (save.isPending) {
      return;
    }
    // Every label this page knows is an older category: a card of that name adopts it (AC-53). The api knows the rest.
    const labels = list.olderCategories.map((older) => older.labelName);
    const problems = validateList(rows, labels, labels);
    if (problems.length === 0) {
      setResult(null);
      setAsking(true);
    } else {
      setResult(problems.some((problem) => problem.field === "list") ? "refused" : null);
      feedback.show(errorsOf(problems, rows));
    }
  };

  return {
    errors: feedback.errors,
    errorStamp: feedback.errorStamp,
    result: feedback.result,
    asking,
    saving: save.isPending,
    submit,
    confirm: () => {
      setAsking(false);
      send();
    },
    cancel: () => {
      setAsking(false);
    },
    retry: send,
    clear: feedback.clearFor,
  };
}
