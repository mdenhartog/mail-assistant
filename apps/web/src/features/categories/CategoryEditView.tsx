import { useId, useRef } from "react";
import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { StickyBar } from "@/components/StickyBar";
import { CategoryFields } from "@/features/categories/CategoryFields";
import type { CategoryFieldsProps } from "@/features/categories/CategoryFields";
import { useEditFocus } from "@/features/categories/useEditFocus";
import type { EditFocus } from "@/features/categories/useEditFocus";

export interface CategoryEditViewProps extends CategoryFieldsProps {
  isNew: boolean;
  focus: EditFocus;
  /** Changes whenever Save found something wrong, so focus moves to it once. */
  errorStamp: number;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
}

/**
 * The full-screen edit view of one category with Save and Cancel. It edits the draft of the page; nothing is
 * stored until the page's Save changes.
 */
export function CategoryEditView({ isNew, focus, errorStamp, onSave, onCancel, onDelete, ...fields }: CategoryEditViewProps): ReactElement {
  const root = useRef<HTMLElement>(null);
  const headingId = useId();
  useEditFocus(root, focus, errorStamp);
  const name = fields.row.name.trim() === "" ? "this category" : fields.row.name;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-6" ref={root}>
      <h2 className="font-display text-xl text-text outline-none" data-field="heading" id={headingId} tabIndex={-1}>
        {isNew ? "New category" : "Edit category"}
      </h2>
      <form
        className="flex flex-col gap-6"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <CategoryFields {...fields} />
        <StickyBar className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary">
            Save
          </Button>
          <Button onClick={onCancel}>Cancel</Button>
          <Button aria-label={`Delete ${name}`} onClick={onDelete} variant="ghost">
            Delete
          </Button>
        </StickyBar>
      </form>
    </section>
  );
}
