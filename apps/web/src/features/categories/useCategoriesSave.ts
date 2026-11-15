import { useRef, useState } from "react";

import { classifySaveError } from "@/api/categories/categories.api";
import { useSaveCategories } from "@/api/categories/categories.queries";
import type { CategoryInput, CategoryList, CategoryProblem } from "@/api/categories/categories.types";
import { validateList } from "@/features/categories/policy";
import { problemText } from "@/features/categories/problemText";
import { openOlder } from "@/features/categories/rows";
import type { Row, RowField } from "@/features/categories/rows";

/** Message per card key and field; a field that is not there is fine. */
export type RowErrors = Record<string, Partial<Record<RowField, string>>>;

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
  /** Hides what the last save said, because the user is editing again. */
  clear: (key?: string) => void;
}

function bodyOf(rows: readonly Row[]): CategoryInput[] {
  return rows.map((row) => (row.id === null ? { name: row.name, description: row.description } : { id: row.id, name: row.name, description: row.description }));
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

/**
 * Validates the draft with the shared rules, asks with a summary, then saves it on the version it was
 * based on. The api checks again: its 422 is mapped to the same fields.
 */
export function useCategoriesSave(list: CategoryList, rows: readonly Row[]): CategoriesSave {
  const [errors, setErrors] = useState<RowErrors>({});
  const [errorStamp, setErrorStamp] = useState(0);
  const [result, setResult] = useState<SaveResult>(null);
  const [asking, setAsking] = useState(false);
  const [version, setVersion] = useState(list.version);
  const save = useSaveCategories();
  const inFlight = useRef(false);

  if (version !== list.version) {
    setVersion(list.version);
    setErrors({});
  }

  const show = (next: RowErrors): void => {
    setErrors(next);
    setErrorStamp((stamp) => stamp + 1);
  };

  const send = (): void => {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setResult(null);
    setErrors({});
    save.mutate(
      { version: list.version, categories: bodyOf(rows) },
      {
        onSuccess: () => {
          setResult("saved");
        },
        onError: (error) => {
          const outcome = classifySaveError(error);
          const mapped = outcome.kind === "invalid" ? errorsOf(outcome.problems, rows) : {};
          if (Object.keys(mapped).length > 0) {
            show(mapped);
          } else if (outcome.kind === "invalid") {
            setResult("refused");
          } else if (outcome.kind === "conflict") {
            setResult("conflict");
          } else {
            setResult(outcome.kind);
          }
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  };

  return {
    errors,
    errorStamp,
    result,
    asking,
    saving: save.isPending,
    submit: () => {
      if (save.isPending) {
        return;
      }
      // An older label already added as a card is the user adopting it: the api decides about that name.
      const labels = openOlder(list, rows).map((older) => older.labelName);
      const problems = validateList(rows, labels);
      if (problems.length === 0) {
        setResult(null);
        setAsking(true);
      } else {
        setResult(problems.some((problem) => problem.field === "list") ? "refused" : null);
        show(errorsOf(problems, rows));
      }
    },
    confirm: () => {
      setAsking(false);
      send();
    },
    cancel: () => {
      setAsking(false);
    },
    retry: send,
    clear: (key) => {
      if (key !== undefined) {
        setErrors((current) => Object.fromEntries(Object.entries(current).filter(([other]) => other !== key)));
      }
      setResult((current) => (current === "saved" ? null : current));
    },
  };
}
