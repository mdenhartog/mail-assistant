import { useEffect, useRef, useState } from "react";
import type { ClipboardEvent, ReactElement, RefObject, SyntheticEvent } from "react";

import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { DeadCodeBanner, RefusalBanner } from "@/pages/refusals";
import { ResendControl } from "@/pages/ResendControl";
import type { ResendNotice, ResendState } from "@/pages/useCodeSending";

export interface CodeFailure {
  /** A plain wrong code, or one that no longer works: past its ten minutes or out of tries. */
  kind: "wrong" | "expired" | "exhausted";
  /** Tries left from the refusal, or null when it carried none. */
  attemptsLeft: number | null;
  /** Grows with every refusal so a repeated one moves focus again. */
  seq: number;
}

export interface CodeStepProps {
  maskedAddress: string;
  verifying: boolean;
  failure: CodeFailure | null;
  /** Changes when the code field must start empty again. */
  codeKey: number;
  resend: ResendState;
  onSubmit: (code: string) => void;
  onUseAnotherUsername: () => void;
}

const CODE_LENGTH = 6;
const CONTROL =
  "min-h-11 w-full max-w-48 rounded-control border border-border bg-surface-raised px-3 text-text tabular-nums " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80 disabled:cursor-not-allowed disabled:opacity-60";

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
  disabled: boolean;
  onChange: (code: string) => void;
}

/** Digits only: typing drops other characters and a paste such as "123 456" is cleaned, not cut. */
function CodeInput({ inputRef, value, readOnly, disabled, onChange, ...aria }: CodeInputProps): ReactElement {
  const paste = (event: ClipboardEvent<HTMLInputElement>): void => {
    event.preventDefault();
    onChange(digitsOnly(event.clipboardData.getData("text")));
  };
  return (
    <input
      {...aria}
      autoComplete="one-time-code"
      className={CONTROL}
      disabled={disabled}
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

function ResendNoticeBanner({ notice }: { notice: ResendNotice }): ReactElement {
  if (notice.kind === "sent") {
    return <Banner kind="success" title="A new code was sent. The earlier code no longer works." />;
  }
  if (notice.kind === "failed") {
    return (
      <Banner kind="danger" title="Could not send a new code.">
        Try again.
      </Banner>
    );
  }
  return <RefusalBanner refusal={notice} />;
}

function Notices({ failure, notice }: { failure: CodeFailure | null; notice: ResendNotice | null }): ReactElement {
  const dead = failure?.kind === "expired" || failure?.kind === "exhausted" ? failure.kind : null;
  return (
    <>
      {notice ? <ResendNoticeBanner notice={notice} /> : null}
      {dead ? <DeadCodeBanner reason={dead} /> : null}
    </>
  );
}

interface CodeFieldProps {
  maskedAddress: string;
  failure: CodeFailure | null;
  codeKey: number;
  verifying: boolean;
  value: string;
  inputRef: RefObject<HTMLInputElement | null>;
  onChange: (code: string) => void;
}

function CodeField({ maskedAddress, failure, codeKey, verifying, value, inputRef, onChange }: CodeFieldProps): ReactElement {
  return (
    <Field
      hint={`We sent a code to ${maskedAddress}. It is valid for 10 minutes.`}
      label="Code"
      {...(failure?.kind === "wrong" ? { error: wrongCodeText(failure.attemptsLeft) } : {})}
    >
      {(control) => (
        <CodeInput
          {...control}
          disabled={failure?.kind === "exhausted"}
          inputRef={inputRef}
          key={codeKey}
          onChange={onChange}
          readOnly={verifying}
          value={value}
        />
      )}
    </Field>
  );
}

/** Focus: the field when the step appears and after a wrong code; an expired or dead code moves it elsewhere. */
function useFieldFocus(failure: CodeFailure | null, codeKey: number): RefObject<HTMLInputElement | null> {
  const input = useRef<HTMLInputElement>(null);
  const seq = failure?.seq;
  const kind = failure?.kind;
  useEffect(() => {
    if (kind !== "expired" && kind !== "exhausted") {
      input.current?.focus();
      input.current?.select();
    }
  }, [seq, codeKey, kind]);
  return input;
}

/**
 * Step 2 of the login page: the code field, "Sign in", "Send a new code" and "Use another username".
 * The code lives only in this component, so leaving the step clears it. Focus goes to the field when the
 * step appears and after a wrong code (text selected); after an expired code it goes to "Send a new code",
 * and after too many tries to the alert, because the field is disabled until a new code is sent.
 *
 * @example
 * <CodeStep codeKey={0} failure={null} maskedAddress="m***@example.com" onSubmit={verify} onUseAnotherUsername={back} resend={resend} verifying={false} />
 */
export function CodeStep({
  maskedAddress,
  verifying,
  failure,
  codeKey,
  resend,
  onSubmit,
  onUseAnotherUsername,
}: CodeStepProps): ReactElement {
  const [code, setCode] = useState("");
  const [seenKey, setSeenKey] = useState(codeKey);
  const input = useFieldFocus(failure, codeKey);
  if (seenKey !== codeKey) {
    setSeenKey(codeKey);
    setCode("");
  }

  const submit = (event: SyntheticEvent): void => {
    event.preventDefault();
    if (!verifying) {
      onSubmit(code);
    }
  };

  return (
    <form className="flex flex-col gap-4" noValidate onSubmit={submit}>
      <Notices failure={failure} notice={resend.notice} />
      <CodeField
        codeKey={codeKey}
        failure={failure}
        inputRef={input}
        maskedAddress={maskedAddress}
        onChange={setCode}
        value={code}
        verifying={verifying}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={failure?.kind === "exhausted"} loading={verifying} loadingLabel="Signing in..." type="submit" variant="primary">
          Sign in
        </Button>
        <ResendControl
          deadline={resend.deadline}
          focusSignal={failure?.kind === "expired" ? failure.seq : null}
          onResend={resend.onResend}
          sending={resend.sending}
          showSeconds={!resend.hourly}
        />
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
