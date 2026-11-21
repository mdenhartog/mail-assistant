import { useRef, useState } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { MAX_CATEGORIES } from "@/features/categories/policy";
import { isDirty, nameOfLabel, openOlder, rowsOf } from "@/features/categories/rows";
import type { Row, RowField } from "@/features/categories/rows";

/** Where focus goes after the next render: a field of one card. */
export interface FocusTarget {
  key: string;
  field: RowField;
  /** Changes on every request, so asking twice for the same field still moves focus. */
  stamp: number;
}

export interface Removed {
  row: Row;
  index: number;
}

export interface CategoriesFlow {
  rows: Row[];
  older: CategoryList["olderCategories"];
  dirty: boolean;
  canAdd: boolean;
  /** The card taken away last, until it is put back or the list is saved. */
  removed: Removed | null;
  focusTarget: FocusTarget | null;
  setField: (key: string, field: RowField, value: string) => void;
  remove: (key: string) => void;
  undoRemove: () => void;
  add: () => void;
  adopt: (labelName: string) => void;
}

/**
 * The draft of the list between load and save. It starts from the stored list and starts over whenever
 * the stored version changes (after a save, or after a 409 handed back the current list).
 */
export function useCategoriesFlow(list: CategoryList): CategoriesFlow {
  const [rows, setRows] = useState<Row[]>(() => rowsOf(list));
  const [version, setVersion] = useState(list.version);
  const [removed, setRemoved] = useState<Removed | null>(null);
  const [focusTarget, setFocusTarget] = useState<FocusTarget | null>(null);
  const counter = useRef(0);

  if (version !== list.version) {
    setVersion(list.version);
    setRows(rowsOf(list));
    setRemoved(null);
    setFocusTarget(null);
  }

  const focus = (key: string, field: RowField): void => {
    setFocusTarget((current) => ({ key, field, stamp: (current?.stamp ?? 0) + 1 }));
  };
  const append = (name: string, field: RowField): void => {
    counter.current += 1;
    const key = `new-${String(counter.current)}`;
    setRows((current) => [...current, { key, id: null, name, description: "", mailCount: null, kind: "topic", notify: false, senders: [] }]);
    focus(key, field);
  };

  return {
    rows,
    older: openOlder(list, rows),
    dirty: isDirty(rows, list),
    canAdd: rows.length < MAX_CATEGORIES,
    removed,
    focusTarget,
    setField: (key, field, value) => {
      setRows((current) => current.map((row) => (row.key === key ? { ...row, [field]: value } : row)));
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
      if (removed !== null) {
        const { row, index } = removed;
        setRows((current) => [...current.slice(0, index), row, ...current.slice(index)]);
        setRemoved(null);
        focus(row.key, "name");
      }
    },
    add: () => {
      append("", "name");
    },
    adopt: (labelName) => {
      append(nameOfLabel(labelName), "description");
    },
  };
}
