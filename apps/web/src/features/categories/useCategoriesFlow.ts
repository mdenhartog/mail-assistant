import { useRef, useState } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { MAX_CATEGORIES } from "@/features/categories/policy";
import { blankRow, isDirty, nameOfLabel, openOlder, rowsOf } from "@/features/categories/rows";
import type { Row, RowPatch } from "@/features/categories/rows";

interface Removed {
  row: Row;
  index: number;
}

export interface CategoriesFlow {
  rows: Row[];
  /** The general instructions of the whole list. */
  instructions: string;
  older: CategoryList["olderCategories"];
  dirty: boolean;
  canAdd: boolean;
  /** The category taken away last, until it is put back or the list is saved. */
  removed: Removed | null;
  setRow: (key: string, patch: RowPatch) => void;
  setInstructions: (value: string) => void;
  /** Puts a row back as it was (Cancel in the edit view). */
  restore: (row: Row) => void;
  /** Takes a row away without a notice (a new category that was cancelled). */
  drop: (key: string) => void;
  remove: (key: string) => void;
  undoRemove: () => Row | null;
  /** Appends a new category and returns its key. */
  add: () => string;
  /** Appends a new category named after an older label and returns its key. */
  adopt: (labelName: string) => string;
}

/**
 * The draft of the list between load and save. It starts from the stored list and starts over whenever
 * the stored version changes (after a save, or after a 409 handed back the current list).
 */
export function useCategoriesFlow(list: CategoryList): CategoriesFlow {
  const [rows, setRows] = useState<Row[]>(() => rowsOf(list));
  const [instructions, setInstructions] = useState(list.generalInstructions);
  const [version, setVersion] = useState(list.version);
  const [removed, setRemoved] = useState<Removed | null>(null);
  const counter = useRef(0);

  if (version !== list.version) {
    setVersion(list.version);
    setRows(rowsOf(list));
    setInstructions(list.generalInstructions);
    setRemoved(null);
  }

  const append = (name: string): string => {
    counter.current += 1;
    const key = `new-${String(counter.current)}`;
    setRows((current) => [...current, blankRow(key, name)]);
    return key;
  };

  return {
    rows,
    instructions,
    older: openOlder(list, rows),
    dirty: isDirty(rows, list, instructions),
    canAdd: rows.length < MAX_CATEGORIES,
    removed,
    setRow: (key, patch) => {
      setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
    },
    setInstructions,
    restore: (row) => {
      setRows((current) => current.map((other) => (other.key === row.key ? row : other)));
    },
    drop: (key) => {
      setRows((current) => current.filter((row) => row.key !== key));
    },
    remove: (key) => {
      const index = rows.findIndex((row) => row.key === key);
      const row = rows[index];
      if (row !== undefined) {
        setRemoved({ row, index });
        setRows((current) => current.filter((other) => other.key !== key));
      }
    },
    undoRemove: () => {
      if (removed === null) {
        return null;
      }
      const { row, index } = removed;
      setRows((current) => [...current.slice(0, index), row, ...current.slice(index)]);
      setRemoved(null);
      return row;
    },
    add: () => append(""),
    adopt: (labelName) => append(nameOfLabel(labelName)),
  };
}
