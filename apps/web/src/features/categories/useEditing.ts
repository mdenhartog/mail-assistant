import { useState } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { rowsOf } from "@/features/categories/rows";
import type { Row } from "@/features/categories/rows";
import type { EditFocus } from "@/features/categories/useEditFocus";
import type { CategoriesFlow } from "@/features/categories/useCategoriesFlow";
import type { CategoriesSave } from "@/features/categories/useCategoriesSave";
import type { ListView } from "@/features/categories/useListView";

/** The category whose edit view is open, as it was when the view opened (null for a new one), and where focus starts. */
interface Editing {
  key: string;
  snapshot: Row | null;
  focus: EditFocus;
}

/** Asks the list to put focus on the row of a category (after the edit view closed). `stamp` makes each ask new. */
interface FocusRow {
  key: string;
  stamp: number;
}

export interface EditingFlow {
  editing: Editing | null;
  focusRow: FocusRow | null;
  open: (key: string) => void;
  add: () => void;
  undo: () => void;
  save: () => void;
  cancel: () => void;
  remove: () => void;
}

interface Parts {
  list: CategoryList;
  flow: CategoriesFlow;
  save: CategoriesSave;
  view: ListView;
}

/** The first category with an error that is not the one being edited, as the view to open for it. */
function viewForErrors({ list, flow, save }: Parts, current: Editing | null): Editing | null {
  const bad = flow.rows.find((row) => save.errors[row.key] !== undefined);
  if (bad === undefined || current?.key === bad.key) {
    return null;
  }
  const stored = rowsOf(list).find((row) => row.id !== null && row.id === bad.id) ?? null;
  return { key: bad.key, snapshot: stored, focus: "invalid" };
}

interface EditState {
  editing: Editing | null;
  setEditing: (editing: Editing | null) => void;
  focusRow: FocusRow | null;
  askFocus: (key: string) => void;
}

/** What is open, where focus goes back to, and the opening of the view of a category the save refused. */
function useEditState(parts: Parts): EditState {
  const [editing, setEditing] = useState<Editing | null>(null);
  const [focusRow, setFocusRow] = useState<FocusRow | null>(null);
  const [seen, setSeen] = useState(parts.save.errorStamp);
  if (seen !== parts.save.errorStamp) {
    setSeen(parts.save.errorStamp);
    const next = viewForErrors(parts, editing);
    if (next !== null) {
      setEditing(next);
    }
  }
  return {
    editing,
    setEditing,
    focusRow,
    askFocus: (key) => {
      setFocusRow((last) => ({ key, stamp: (last?.stamp ?? 0) + 1 }));
    },
  };
}

/**
 * Which category is open in the edit view, and what Save, Cancel and Delete do to the draft. A refused save
 * (the page's or the api's) opens the view of the first category with an error.
 */
export function useEditing(parts: Parts): EditingFlow {
  const { flow, save, view } = parts;
  const { editing, setEditing, focusRow, askFocus } = useEditState(parts);
  const back = (row: Row): void => {
    view.reveal(row.name);
    setEditing(null);
    askFocus(row.key);
  };
  const open = (key: string, focus: EditFocus, snapshot: Row | null): void => {
    setEditing({ key, snapshot, focus });
  };
  return {
    editing,
    focusRow,
    open: (key) => {
      open(key, "heading", flow.rows.find((row) => row.key === key) ?? null);
    },
    add: () => {
      open(flow.add(), "name", null);
    },
    undo: () => {
      const row = flow.undoRemove();
      if (row !== null) {
        view.reveal(row.name);
        askFocus(row.key);
      }
    },
    save: () => {
      const row = flow.rows.find((other) => other.key === editing?.key);
      if (row !== undefined && save.checkRow(row.key)) {
        back(row);
      }
    },
    cancel: () => {
      if (editing === null) {
        return;
      }
      save.clear(editing.key);
      if (editing.snapshot === null) {
        flow.drop(editing.key);
        setEditing(null);
      } else {
        flow.restore(editing.snapshot);
        back(editing.snapshot);
      }
    },
    remove: () => {
      if (editing !== null) {
        (editing.snapshot === null ? flow.drop : flow.remove)(editing.key);
        setEditing(null);
      }
    },
  };
}
