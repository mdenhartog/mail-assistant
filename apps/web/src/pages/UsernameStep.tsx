import { useRef, useState } from "react";
import type { ReactElement, SyntheticEvent } from "react";

import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { RefusalBanner } from "@/pages/refusals";
import type { RequestFailure } from "@/pages/refusals";

export interface UsernameStepProps {
  sending: boolean;
  /** Why the last request gave no code; null when it did not fail. */
  failure: RequestFailure | null;
  onSubmit: (username: string) => void;
}

/** Fixed text: it says what the field wants and never whether a name exists (ADR-0038). */
const USERNAME_HINT = "Your username, not your e-mail address.";

const CONTROL =
  "min-h-11 w-full rounded-control border border-border bg-surface-raised px-3 text-text " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

/**
 * Step 1 of the login page: the username and the button that asks for a code.
 *
 * @example
 * <UsernameStep failure={null} onSubmit={ask} sending={false} />
 */
export function UsernameStep({ sending, failure, onSubmit }: UsernameStepProps): ReactElement {
  const [username, setUsername] = useState("");
  const [missing, setMissing] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const submit = (event: SyntheticEvent): void => {
    event.preventDefault();
    if (sending) {
      return;
    }
    const trimmed = username.trim();
    setMissing(trimmed === "");
    if (trimmed === "") {
      input.current?.focus();
      return;
    }
    onSubmit(trimmed);
  };

  return (
    <form className="flex flex-col gap-4" noValidate onSubmit={submit}>
      {failure?.kind === "failed" ? (
        <Banner kind="danger" title="Could not ask for a code.">
          Check the username and try again.
        </Banner>
      ) : null}
      {failure && failure.kind !== "failed" ? <RefusalBanner refusal={failure} /> : null}
      <Field hint={USERNAME_HINT} label="Username" {...(missing ? { error: "Enter your username." } : {})}>
        {(control) => (
          <input
            {...control}
            autoCapitalize="none"
            autoComplete="username"
            className={CONTROL}
            onChange={(event) => {
              setUsername(event.target.value);
            }}
            readOnly={sending}
            ref={input}
            spellCheck={false}
            type="text"
            value={username}
          />
        )}
      </Field>
      <div>
        <Button loading={sending} loadingLabel="Sending..." type="submit" variant="primary">
          Send me a code
        </Button>
      </div>
      <p className="text-sm text-text-muted">
        We send a one-time code to the e-mail address on file for this username. This page never asks for access to
        your mail or calendar.
      </p>
    </form>
  );
}
