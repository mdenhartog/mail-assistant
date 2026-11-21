import { useEffect, useRef } from "react";
import type { ReactElement, RefObject } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { StickyBar } from "@/components/StickyBar";
import { CategoryCard } from "@/features/categories/CategoryCard";
import { Intro, OtherCard } from "@/features/categories/Intro";
import { LeaveGuard } from "@/features/categories/LeaveGuard";
import { OlderCategories } from "@/features/categories/OlderCategories";
import { changesOf } from "@/features/categories/rows";
import { SaveResultBanner } from "@/features/categories/SaveResultBanner";
import { changesText, SaveSummary } from "@/features/categories/SaveSummary";
import { useCategoriesFlow } from "@/features/categories/useCategoriesFlow";
import type { CategoriesFlow, FocusTarget, Removed } from "@/features/categories/useCategoriesFlow";
import { useCategoriesSave } from "@/features/categories/useCategoriesSave";
import type { CategoriesSave } from "@/features/categories/useCategoriesSave";

/** Moves focus to the requested field of a card each time the request changes. */
function useFocusTarget(form: RefObject<HTMLFormElement | null>, target: FocusTarget | null): void {
  useEffect(() => {
    if (target !== null) {
      form.current?.querySelector<HTMLElement>(`[data-row="${target.key}"] [data-field="${target.field}"]`)?.focus();
    }
  }, [form, target]);
}

/** Moves focus to the first invalid control each time `stamp` changes to a non-zero value. */
function useFocusFirstInvalid(form: RefObject<HTMLFormElement | null>, stamp: number): void {
  useEffect(() => {
    if (stamp > 0) {
      form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    }
  }, [form, stamp]);
}

/** Takes the place of the card that was removed, and says what saving does with it. */
function RemovedNotice({ removed, onUndo }: { removed: Removed; onUndo: () => void }): ReactElement {
  return (
    <li data-removed="">
      <Banner action={{ label: "Undo", onClick: onUndo }} kind="info" title={`Removed ${removed.row.name}.`}>
        It is removed when you save. Mail already filed under it stays where it is.
      </Banner>
    </li>
  );
}

function CardGrid({ flow, save }: { flow: CategoriesFlow; save: CategoriesSave }): ReactElement {
  const { removed } = flow;
  const items = flow.rows.map((row, index) => (
    <CategoryCard
      errors={save.errors[row.key] ?? {}}
      key={row.key}
      onChange={(key, field, value) => {
        flow.setField(key, field, value);
        save.clear(key);
      }}
      onRemove={flow.remove}
      position={index + 1}
      readOnly={save.saving}
      row={row}
    />
  ));
  if (removed !== null) {
    items.splice(removed.index, 0, <RemovedNotice key="removed" onUndo={flow.undoRemove} removed={removed} />);
  }
  return <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">{items}</ul>;
}

/** The loaded list as a form of cards. */
export function CategoriesForm({ list }: { list: CategoryList }): ReactElement {
  const flow = useCategoriesFlow(list);
  const save = useCategoriesSave(list, flow.rows);
  const form = useRef<HTMLFormElement>(null);
  useFocusTarget(form, flow.focusTarget);
  useFocusFirstInvalid(form, save.errorStamp);
  const changes = changesOf(flow.rows, list);
  return (
    <form
      className="mt-6 flex flex-col gap-6"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        save.submit();
      }}
      ref={form}
    >
      <Intro />
      <SaveResultBanner onRetry={save.retry} result={save.result} />
      <CardGrid flow={flow} save={save} />
      <div>
        <Button disabled={!flow.canAdd} onClick={flow.add}>
          Add category
        </Button>
        {flow.canAdd ? null : (
          <p className="mt-2 text-sm text-text-muted">You have reached the limit of 100 categories. Remove one to add another.</p>
        )}
      </div>
      <OtherCard mailCount={list.other.mailCount} />
      <OlderCategories older={flow.older} onAdopt={flow.adopt} />
      <StickyBar className="flex flex-wrap items-center gap-3">
        <Button disabled={!flow.dirty} loading={save.saving} type="submit" variant="primary">
          Save changes
        </Button>
        {changes.length > 0 ? <p className="text-sm text-text-muted">{`${changesText(changes.length)} not saved`}</p> : null}
      </StickyBar>
      <SaveSummary
        onCancel={save.cancel}
        onConfirm={save.confirm}
        open={save.asking}
        changes={changes}
      />
      <LeaveGuard dirty={flow.dirty} />
      <p className="sr-only" role="status">
        {save.saving ? "Saving your categories." : ""}
      </p>
    </form>
  );
}
