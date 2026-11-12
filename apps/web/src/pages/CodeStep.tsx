import { useEffect, useRef, useState } from "react";
import type { ClipboardEvent, ReactElement, RefObject, SyntheticEvent } from "react";

import { Button } from "@/components/Button";
import { Field } from "@/components/Field";

export interface CodeFailure {
  /** Tries left from the refusal, or null when it carried none. */
  attemptsLeft: number | null;
  /** Grows with every refusal so a repeated one moves focus again. */
  seq: number;
}

export interface CodeStepProps {
  maskedAddress: string;
  verifying: boolean;
  failure: CodeFailure | null;
  onSubmit: (code: string) => void;
  onUseAnotherUsername: () => void;
}

const CODE_LENGTH = 6;
const CONTROL =
  "min-h-11 w-full max-w-48 rounded-control border border-border bg-surface-raised px-3 text-text tabular-nums " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

function digitsOnly(text: string): string {
  return text.replace(/\D/g, "").slice(0, CODE_LENGTH);
}

/** The text under a wrong code; the same one whatever the reason (AC-3). */
function wrongCodeText(attemptsLeft: number | null): string {
  if (attemptsLeft === null) {
    return "That code is not right.";
  }
  return `That code is not right. You have ${String(attemptsLeft)} ${attemptsLeft === 1 ? "try" : "tries"} left.`;
}

interface CodeInputProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
  inputRef: RefObject<HTMLInputElement | null>;
  value: string;
  readOnly: boolean;
  onChange: (code: string) => void;
}

/** Digits only: typing drops other characters and a paste such as "123 456" is cleaned, not cut. */
function CodeInput({ inputRef, value, readOnly, onChange, ...aria }: CodeInputProps): ReactElement {
  const paste = (event: ClipboardEvent<HTMLInputElement>): void => {
    event.preventDefault();
    onChange(digitsOnly(event.clipboardData.getData("text")));
  };
  return (
    <input
      {...aria}
      autoComplete="one-time-code"
      className={CONTROL}
      inputMode="numeric"
      maxLength={CODE_LENGTH}
      onChange={(event) => {
        onChange(digitsOnly(event.target.value));
      }}
      onPaste={paste}
      pattern="[0-9]*"
      readOnly={readOnly}
      ref={inputRef}
      type="text"
      value={value}
    />
  );
}

/**
 * Step 2 of the login page: the code field, "Sign in" and "Use another username". The code lives
 * only in this component, so leaving the step clears it. Focus goes to the field when the step
 * appears and again, with the text selected, after every refusal.
 *
 * @example
 * <CodeStep failure={null} maskedAddress="m***@example.com" onSubmit={verify} onUseAnotherUsername={back} verifying={false} />
 */
export function CodeStep({
  maskedAddress,
  verifying,
  failure,
  onSubmit,
  onUseAnotherUsername,
}: CodeStepProps): ReactElement {
  const [code, setCode] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const failureSeq = failure?.seq;

  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, [failureSeq]);

  const submit = (event: SyntheticEvent): void => {
    event.preventDefault();
    if (!verifying) {
      onSubmit(code);
    }
  };

  return (
    <form className="flex flex-col gap-4" noValidate onSubmit={submit}>
      <Field
        hint={`We sent a code to ${maskedAddress}. It is valid for 10 minutes.`}
        label="Code"
        {...(failure ? { error: wrongCodeText(failure.attemptsLeft) } : {})}
      >
        {(control) => <CodeInput {...control} inputRef={input} onChange={setCode} readOnly={verifying} value={code} />}
      </Field>
      <div className="flex flex-wrap gap-3">
        <Button loading={verifying} loadingLabel="Signing in..." type="submit" variant="primary">
          Sign in
        </Button>
        <Button onClick={onUseAnotherUsername} variant="ghost">
          Use another username
        </Button>
      </div>
      <p className="text-sm text-text-muted">
        No code after a few minutes? Ask for a new one after the countdown, or check the mail setup.
      </p>
    </form>
  );
}
