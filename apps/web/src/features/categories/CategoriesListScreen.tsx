import { useEffect, useRef } from "react";
import type { ReactElement, RefObject } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { Button } from "@/components/Button";
import { StickyBar } from "@/components/StickyBar";
import { CategoryListBody } from "@/features/categories/CategoryListBody";
import { InstructionsField } from "@/features/categories/InstructionsField";
import { Intro, OtherCard } from "@/features/categories/Intro";
import { OlderCategories } from "@/features/categories/OlderCategories";
import type { Change } from "@/features/categories/rows";
import { SaveResultBanner } from "@/features/categories/SaveResultBanner";
import { changesText } from "@/features/categories/SaveSummary";
import type { CategoriesFlow } from "@/features/categories/useCategoriesFlow";
import type { CategoriesSave } from "@/features/categories/useCategoriesSave";
import type { EditingFlow } from "@/features/categories/useEditing";
import type { ListView } from "@/features/categories/useListView";

export interface CategoriesListScreenProps {
  list: CategoryList;
  flow: CategoriesFlow;
  save: CategoriesSave;
  view: ListView;
  edit: EditingFlow;
  changes: readonly Change[];
}

/** Moves focus to the instructions field when a save finds it wrong (not when the list merely comes back into view). */
function useFocusInstructionsError(form: RefObject<HTMLFormElement | null>, stamp: number): void {
  const seen = useRef(stamp);
  useEffect(() => {
    if (stamp !== seen.current) {
      seen.current = stamp;
      form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    }
  }, [form, stamp]);
}

/** Puts focus on the row of the category the edit view was just closed for. */
function useFocusRow(form: RefObject<HTMLFormElement | null>, edit: EditingFlow): void {
  const request = edit.focusRow;
  useEffect(() => {
    if (request !== null) {
      form.current?.querySelector<HTMLElement>(`[data-row-key="${request.key}"] [data-edit]`)?.focus();
    }
  }, [form, request]);
}

/** The list page: the fixed block, the general instructions, the collapsed list and the Save changes bar. */
export function CategoriesListScreen({ list, flow, save, view, edit, changes }: CategoriesListScreenProps): ReactElement {
  const form = useRef<HTMLFormElement>(null);
  useFocusInstructionsError(form, save.errorStamp);
  useFocusRow(form, edit);
  return (
    <form
      className="flex flex-col gap-6"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        save.submit();
      }}
      ref={form}
    >
      <Intro />
      <SaveResultBanner onRetry={save.retry} result={save.result} />
      <InstructionsField
        error={save.instructionsError}
        onChange={(value) => {
          flow.setInstructions(value);
          save.clearInstructions();
        }}
        readOnly={save.saving}
        value={flow.instructions}
      />
      <CategoryListBody
        flow={flow}
        locked={save.saving}
        onAdd={edit.add}
        onEdit={edit.open}
        onNotify={(key, notify) => {
          flow.setRow(key, { notify });
          save.clear(key);
        }}
        onUndo={edit.undo}
        view={view}
      />
      <OtherCard mailCount={list.other.mailCount} />
      <OlderCategories older={flow.older} onAdopt={edit.adopt} />
      <StickyBar className="flex flex-wrap items-center gap-3">
        <Button disabled={!flow.dirty} loading={save.saving} type="submit" variant="primary">
          Save changes
        </Button>
        {changes.length > 0 ? <p className="text-sm text-text-muted">{`${changesText(changes.length)} not saved`}</p> : null}
      </StickyBar>
    </form>
  );
}
