import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Field } from "@/components/Field";
import { countText } from "@/features/categories/copy";
import type { Row, RowField } from "@/features/categories/rows";

export const DESCRIPTION_HINT =
  "The model reads the description. Say what belongs here, for example: Invoices, receipts and payment confirmations.";

const CONTROL =
  "min-h-11 w-full min-w-0 max-w-full rounded-control border border-border bg-surface-raised px-3 py-2 text-text " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

export interface CategoryCardProps {
  row: Row;
  position: number;
  errors: Partial<Record<RowField, string>>;
  readOnly: boolean;
  onChange: (key: string, field: RowField, value: string) => void;
  onRemove: (key: string) => void;
}

/**
 * One category: name, description, the number of mails filed under it and Delete. Every text is rendered
 * as text (React escapes it), so a name with markup stays inert (AC-21).
 */
export function CategoryCard({ row, position, errors, readOnly, onChange, onRemove }: CategoryCardProps): ReactElement {
  const label = row.name.trim() === "" ? `category ${String(position)}` : row.name;
  return (
    <li data-row={row.key}>
      <Card>
        <div aria-label={`Category ${String(position)}`} className="flex flex-col gap-4" role="group">
          <Field error={errors.name} label="Name">
            {(control) => (
              <input
                {...control}
                className={CONTROL}
                data-field="name"
                onChange={(event) => {
                  onChange(row.key, "name", event.target.value);
                }}
                readOnly={readOnly}
                type="text"
                value={row.name}
              />
            )}
          </Field>
          <Field error={errors.description} hint={DESCRIPTION_HINT} label="Description">
            {(control) => (
              <textarea
                {...control}
                className={CONTROL}
                data-field="description"
                onChange={(event) => {
                  onChange(row.key, "description", event.target.value);
                }}
                readOnly={readOnly}
                rows={3}
                value={row.description}
              />
            )}
          </Field>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-text-muted">{row.mailCount === null ? "Not counted yet" : countText(row.mailCount)}</p>
            <Button
              aria-label={`Delete ${label}`}
              onClick={() => {
                onRemove(row.key);
              }}
              variant="ghost"
            >
              Delete
            </Button>
          </div>
        </div>
      </Card>
    </li>
  );
}
