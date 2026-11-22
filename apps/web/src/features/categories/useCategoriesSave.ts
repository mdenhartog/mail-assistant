import { useRef, useState } from "react";

import { classifySaveError } from "@/api/categories/categories.api";
import { useSaveCategories } from "@/api/categories/categories.queries";
import type { CategoryInput, CategoryList } from "@/api/categories/categories.types";
import { MAX_INSTRUCTIONS, validateList } from "@/features/categories/policy";
import { problemText } from "@/features/categories/problemText";
import type { Row } from "@/features/categories/rows";
import { draftErrors, rowErrors } from "@/features/categories/saveErrors";
import type { ErrorsByRow } from "@/features/categories/saveErrors";
import { parseSenders } from "@/features/categories/senders";
import { showFailure, useFeedback } from "@/features/categories/useSaveFeedback";
import type { Feedback, SaveResult } from "@/features/categories/useSaveFeedback";

export interface CategoriesSave {
  errors: ErrorsByRow;
  /** What is wrong with the general instructions of the list. */
  instructionsError: string | undefined;
  /** Changes on every submit that shows errors, so focus moves once per submit and not while typing. */
  errorStamp: number;
  result: SaveResult;
  /** The summary dialog is open. */
  asking: boolean;
  saving: boolean;
  submit: () => void;
  /** Checks one category (the edit view's Save); shows what is wrong and returns whether it is fine. */
  checkRow: (key: string) => boolean;
  confirm: () => void;
  cancel: () => void;
  /** Sends the same list again after a failure. */
  retry: () => void;
  /** Hides what the last save said, because the user is editing a card again. */
  clear: (key: string) => void;
  clearInstructions: () => void;
}

function bodyOf(rows: readonly Row[]): CategoryInput[] {
  return rows.map((row) => {
    const fields = {
      name: row.name,
      description: row.description,
      kind: row.kind,
      notify: row.notify,
      senders: parseSenders(row.sendersText).entries,
    };
    return row.id === null ? fields : { id: row.id, ...fields };
  });
}

interface Sender {
  send: () => void;
  saving: boolean;
}

/** Sends the whole draft on the stored version once at a time; what comes back goes to the feedback. */
function useSender(list: CategoryList, rows: readonly Row[], instructions: string, feedback: Feedback): Sender {
  const save = useSaveCategories();
  const inFlight = useRef(false);
  const send = (): void => {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    feedback.setResult(null);
    feedback.clearAll();
    save.mutate(
      { version: list.version, generalInstructions: instructions, categories: bodyOf(rows) },
      {
        onSuccess: () => {
          feedback.setResult("saved");
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
  return { send, saving: save.isPending };
}

/**
 * Validates the draft with the shared rules, asks with a summary, then saves it on the version it was
 * based on. The api checks again: its 422 is mapped to the same fields.
 */
export function useCategoriesSave(list: CategoryList, rows: readonly Row[], instructions: string): CategoriesSave {
  const [asking, setAsking] = useState(false);
  const feedback = useFeedback(list.version);
  const { send, saving } = useSender(list, rows, instructions, feedback);
  // Every label this page knows is an older category: a card of that name adopts it (AC-53). The api knows the rest.
  const labels = list.olderCategories.map((older) => older.labelName);

  const submit = (): void => {
    if (saving) {
      return;
    }
    const errors = draftErrors(rows, labels);
    const tooLong = Array.from(instructions).length > MAX_INSTRUCTIONS ? problemText("instructions_too_long") : undefined;
    if (Object.keys(errors).length === 0 && tooLong === undefined) {
      feedback.setResult(null);
      setAsking(true);
    } else {
      feedback.setResult(validateList(rows, labels, labels).some((problem) => problem.field === "list") ? "refused" : null);
      feedback.show(errors, tooLong);
    }
  };

  const checkRow = (key: string): boolean => {
    const row = rows.find((other) => other.key === key);
    const errors = row === undefined ? {} : rowErrors(rows, row, labels);
    const fine = Object.keys(errors).length === 0;
    if (!fine) {
      feedback.show(errors);
    }
    return fine;
  };

  return {
    errors: feedback.errors,
    instructionsError: feedback.instructionsError,
    errorStamp: feedback.errorStamp,
    result: feedback.result,
    asking,
    saving,
    submit,
    checkRow,
    confirm: () => {
      setAsking(false);
      send();
    },
    cancel: () => {
      setAsking(false);
    },
    retry: send,
    clear: feedback.clearFor,
    clearInstructions: feedback.clearInstructions,
  };
}
