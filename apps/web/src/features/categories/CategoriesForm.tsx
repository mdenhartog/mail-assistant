import { useEffect, useRef } from "react";
import type { ReactElement, RefObject } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { CategoryCard } from "@/features/categories/CategoryCard";
import { countText } from "@/features/categories/copy";
import { OlderCategories } from "@/features/categories/OlderCategories";
import { useCategoriesFlow } from "@/features/categories/useCategoriesFlow";
import type { FocusTarget } from "@/features/categories/useCategoriesFlow";

/** Moves focus to the requested field of a card each time the request changes. */
function useFocusTarget(form: RefObject<HTMLFormElement | null>, target: FocusTarget | null): void {
  useEffect(() => {
    if (target !== null) {
      form.current?.querySelector<HTMLElement>(`[data-row="${target.key}"] [data-field="${target.field}"]`)?.focus();
    }
  }, [form, target]);
}

/** The loaded list as a form of cards. */
export function CategoriesForm({ list }: { list: CategoryList }): ReactElement {
  const flow = useCategoriesFlow(list);
  const form = useRef<HTMLFormElement>(null);
  useFocusTarget(form, flow.focusTarget);
  return (
    <form
      className="mt-6 flex flex-col gap-6"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
      }}
      ref={form}
    >
      <div className="flex flex-col gap-2">
        <p className="text-text">Changes apply to new mail from now on. Old mail stays where it is for now.</p>
        <p className="text-sm text-text-muted">Renaming only changes the label name.</p>
      </div>
      <Banner kind="info" title="Archive is left alone.">
        Mail you put in the Gmail label Archive is never re-sorted.
      </Banner>
      {flow.removed ? (
        <Banner action={{ label: "Undo", onClick: flow.undoRemove }} kind="info" title={`Removed ${flow.removed.row.name}.`}>
          It is gone when you save.
        </Banner>
      ) : null}
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {flow.rows.map((row, index) => (
          <CategoryCard
            errors={{}}
            key={row.key}
            onChange={flow.setField}
            onRemove={flow.remove}
            position={index + 1}
            readOnly={false}
            row={row}
          />
        ))}
      </ul>
      <div>
        <Button disabled={!flow.canAdd} onClick={flow.add}>
          Add category
        </Button>
        {flow.canAdd ? null : (
          <p className="mt-2 text-sm text-text-muted">You have 50 categories, the most you can have.</p>
        )}
      </div>
      <Card>
        <div aria-label="Other" className="flex flex-col gap-1" role="group">
          <h2 className="font-display text-xl text-text">Other</h2>
          <p className="text-text-muted">Mail that fits no category</p>
          <p className="text-sm text-text-muted">{countText(list.other.mailCount)}</p>
        </div>
      </Card>
      <OlderCategories older={flow.older} onAdopt={flow.adopt} />
    </form>
  );
}
