import { useEffect, useId, useRef } from "react";
import type { ReactElement } from "react";

import type { UploadProblem } from "@/api/categories/upload.types";
import { Button } from "@/components/Button";
import { useCopy } from "@/features/categories/upload/useCopy";

function lineOf(problem: UploadProblem): string {
  return `Line ${String(problem.line)}, ${problem.field}: ${problem.message}`;
}

/** Every problem of a refused file with its line and field, and a button that copies them as plain text. */
export function ProblemsPanel({ problems }: { problems: readonly UploadProblem[] }): ReactElement {
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const { status, copy } = useCopy();
  useEffect(() => {
    heading.current?.focus();
  }, []);
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-card border-l-8 border-danger bg-danger-soft p-5 text-danger">
      <h3 className="font-display text-xl wrap-anywhere" id={id} ref={heading} tabIndex={-1}>
        Your file was not accepted
      </h3>
      <p>Nothing was changed. Fix these and upload the file again.</p>
      <ol className="flex list-decimal flex-col gap-2 pl-6">
        {problems.map((problem) => (
          <li className="wrap-anywhere" key={`${String(problem.line)}-${problem.field}-${problem.rule}`}>
            {lineOf(problem)}
          </li>
        ))}
      </ol>
      <div>
        <Button
          onClick={() => {
            void copy(() => problems.map(lineOf).join("\n"));
          }}
        >
          Copy errors
        </Button>
      </div>
      <p role="status">
        {status === "copied" ? "Copied." : status === "failed" ? "Could not copy. Select the text and copy it yourself." : ""}
      </p>
    </section>
  );
}
