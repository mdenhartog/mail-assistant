import { useId, useRef, useState } from "react";
import type { ReactElement, RefObject } from "react";
import { Link } from "react-router";

import { classifyResortError } from "@/api/categories/resort.api";
import { useLatestThreshold, useRequestResort } from "@/api/categories/resort.queries";
import type { ResortFailure } from "@/api/categories/resort.types";
import { usePlan } from "@/api/plan/plan.queries";
import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { SORT_AGAIN } from "@/features/categories/copy";
import { parseThreshold, THRESHOLD_REASON } from "@/features/categories/sort-again/threshold";

/** The plan states in which the agent still has work to do for the user; any of them blocks a new request. */
const OPEN_STATES = new Set(["building", "ready", "scheduled", "applying"]);

function failureText(failure: ResortFailure): string {
  switch (failure) {
    case "open":
      return SORT_AGAIN.open;
    case "rate-limited":
      return SORT_AGAIN.tooMany;
    default:
      return SORT_AGAIN.failed;
  }
}

function Loading(): ReactElement {
  return (
    <div aria-busy="true">
      <p className="text-text-muted" role="status">
        Loading the threshold
      </p>
      <div aria-hidden="true" className="mt-3 h-11 w-32 rounded-control bg-divider motion-safe:animate-pulse" data-skeleton="" />
    </div>
  );
}

interface Message {
  role: "alert" | "status";
  content: ReactElement | string;
}

function MessageLine({ id, message }: { id: string; message: Message }): ReactElement {
  return (
    <p className={message.role === "alert" ? "text-danger" : "text-text-muted"} id={id} role={message.role}>
      {message.content}
    </p>
  );
}

const PLAN_OPEN: Message = {
  role: "status",
  content: (
    <>
      A plan is open. Wait until it has been applied or cancelled.{" "}
      <Link className="inline-flex min-h-11 items-center underline" to="/review">
        Follow it in Review moves
      </Link>
    </>
  ),
};

interface SortAgain {
  text: string;
  /** The last valid value, shown in the text of the spec. */
  shown: number;
  fieldError: string | undefined;
  failure: ResortFailure | null;
  sent: boolean;
  planOpen: boolean;
  pending: boolean;
  input: RefObject<HTMLInputElement | null>;
  change: (next: string) => void;
  submit: () => void;
}

/** The typed threshold, its check before any request, and what the request and the open plan say. */
function useSortAgain(initial: number): SortAgain {
  const [text, setText] = useState(String(initial));
  const [shown, setShown] = useState(initial);
  const [fieldError, setFieldError] = useState<string | undefined>(undefined);
  const [failure, setFailure] = useState<ResortFailure | null>(null);
  const [sent, setSent] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const request = useRequestResort();
  const state = usePlan().data?.state;
  const planOpen = state !== undefined && state !== null && OPEN_STATES.has(state);

  const refuseField = (): void => {
    setFieldError(THRESHOLD_REASON);
    input.current?.focus();
  };
  const submit = (): void => {
    if (request.isPending || sent || planOpen) {
      return;
    }
    const threshold = parseThreshold(text);
    if (threshold === null) {
      refuseField();
      return;
    }
    setFailure(null);
    request.mutate(threshold, {
      onSuccess: () => {
        setSent(true);
      },
      onError: (error) => {
        const kind = classifyResortError(error);
        if (kind === "invalid") {
          refuseField();
        } else {
          setFailure(kind);
        }
      },
    });
  };
  const change = (next: string): void => {
    setText(next);
    setFieldError(undefined);
    const valid = parseThreshold(next);
    if (valid !== null) {
      setShown(valid);
    }
  };
  return { text, shown, fieldError, failure, sent, planOpen, pending: request.isPending, input, change, submit };
}

function messageOf(sort: SortAgain): Message | null {
  if (sort.planOpen) {
    return PLAN_OPEN;
  }
  if (sort.sent) {
    return { role: "status", content: SORT_AGAIN.sent };
  }
  return sort.failure === null ? null : { role: "alert", content: failureText(sort.failure) };
}

function ThresholdForm({ initial }: { initial: number }): ReactElement {
  const sort = useSortAgain(initial);
  const noteId = useId();
  const messageId = useId();
  const message = messageOf(sort);
  return (
    <form
      className="flex flex-col gap-3"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        sort.submit();
      }}
    >
      <Field error={sort.fieldError} hint={SORT_AGAIN.explain(sort.shown)} label={SORT_AGAIN.field}>
        {(control) => (
          <input
            {...control}
            autoComplete="off"
            className="min-h-11 w-32 min-w-0 rounded-control border border-border bg-surface-raised px-3 py-2 text-text aria-invalid:border-2 aria-invalid:border-danger"
            inputMode="numeric"
            onChange={(event) => {
              sort.change(event.target.value);
            }}
            ref={sort.input}
            type="text"
            value={sort.text}
          />
        )}
      </Field>
      <p className="text-sm text-text-muted">{SORT_AGAIN.calibration}</p>
      <div className="flex flex-col items-start gap-2">
        <Button
          aria-describedby={message === null ? noteId : `${noteId} ${messageId}`}
          disabled={sort.planOpen || sort.sent}
          loading={sort.pending}
          loadingLabel="Sending..."
          type="submit"
          variant="primary"
        >
          {SORT_AGAIN.title}
        </Button>
        <p className="text-sm text-text-muted" id={noteId}>
          {SORT_AGAIN.underButton}
        </p>
        {message === null ? null : <MessageLine id={messageId} message={message} />}
      </div>
    </form>
  );
}

/** The threshold field, the Sort everything again button and the texts around them. */
export function SortAgainSection(): ReactElement {
  const latest = useLatestThreshold();
  let content: ReactElement;
  if (latest.isPending) {
    content = <Loading />;
  } else if (latest.isError) {
    content = (
      <Banner
        action={{
          label: "Try again",
          onClick: () => {
            void latest.refetch();
          },
        }}
        kind="danger"
        title="Could not load the threshold."
      >
        Check your connection and try again.
      </Banner>
    );
  } else {
    content = <ThresholdForm initial={latest.data.threshold} />;
  }
  return (
    <section aria-labelledby="sort-again" className="mt-10 flex flex-col gap-4 border-t border-divider pt-8">
      <h2 className="font-display text-xl text-text wrap-anywhere" id="sort-again">
        {SORT_AGAIN.title}
      </h2>
      {content}
    </section>
  );
}
