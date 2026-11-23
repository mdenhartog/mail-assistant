import type { ReactElement } from "react";

import type { CategoryList } from "@/api/categories/categories.types";
import { CategoriesListScreen } from "@/features/categories/CategoriesListScreen";
import { CategoryEditView } from "@/features/categories/CategoryEditView";
import { LeaveGuard } from "@/features/categories/LeaveGuard";
import { changesOf } from "@/features/categories/rows";
import { SaveSummary } from "@/features/categories/SaveSummary";
import { SortAgainSection } from "@/features/categories/sort-again/SortAgainSection";
import { UploadSection } from "@/features/categories/upload/UploadSection";
import { useCategoriesFlow } from "@/features/categories/useCategoriesFlow";
import { useCategoriesSave } from "@/features/categories/useCategoriesSave";
import { useEditing } from "@/features/categories/useEditing";
import { useListView } from "@/features/categories/useListView";

/** The loaded list: the collapsed list, or the full-screen edit view of one category, and the save and leave questions. */
export function CategoriesForm({ list }: { list: CategoryList }): ReactElement {
  const flow = useCategoriesFlow(list);
  const save = useCategoriesSave(list, flow.rows, flow.settings);
  const view = useListView();
  const edit = useEditing({ list, flow, save, view });
  const changes = changesOf(flow.rows, list, flow.settings);
  const open = edit.editing === null ? undefined : flow.rows.find((row) => row.key === edit.editing?.key);
  return (
    <div className="mt-6">
      {edit.editing !== null && open !== undefined ? (
        <CategoryEditView
          errorStamp={save.errorStamp}
          errors={save.errors[open.key] ?? {}}
          focus={edit.editing.focus}
          isNew={edit.editing.snapshot === null}
          key={open.key}
          onCancel={edit.cancel}
          onChange={(patch) => {
            flow.setRow(open.key, patch);
            save.clear(open.key);
          }}
          onDelete={edit.remove}
          onSave={edit.save}
          row={open}
          rows={flow.rows}
        />
      ) : (
        <CategoriesListScreen changes={changes} edit={edit} flow={flow} list={list} save={save} view={view} />
      )}
      {edit.editing === null ? <SortAgainSection /> : null}
      {edit.editing === null ? <UploadSection list={list} /> : null}
      <SaveSummary changes={changes} onCancel={save.cancel} onConfirm={save.confirm} open={save.asking} />
      <LeaveGuard dirty={flow.dirty} />
      <p className="sr-only" role="status">
        {save.saving ? "Saving your categories." : ""}
      </p>
    </div>
  );
}
