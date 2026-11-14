import type { ReactElement } from "react";
import { useSearchParams } from "react-router";

import { Banner } from "@/components/Banner";
import { Layout } from "@/components/Layout";
import { useDraft } from "@/features/settings/useDraft";
import { CodeStep } from "@/pages/CodeStep";
import { UsernameStep } from "@/pages/UsernameStep";
import { useSignIn } from "@/pages/useSignIn";
import type { SignIn } from "@/pages/useSignIn";
import { usePageTitle } from "@/pages/usePageTitle";

/** Fixed texts for the notices a redirect may ask for; anything else in the URL is ignored. */
const NOTICES: Record<string, { title: string; text: string }> = {
  expired: { title: "Your session ended.", text: "Sign in again." },
};

function statusText(signIn: SignIn): string {
  if (signIn.sending) {
    return "Sending your code.";
  }
  if (signIn.verifying) {
    return "Signing you in.";
  }
  return signIn.maskedAddress === null ? "" : `Code sent to ${signIn.maskedAddress}. It is valid for 10 minutes.`;
}

/** What the session notice adds while typed values wait for the return to the settings (AC-12). */
const DRAFT_KEPT = "Sign in again; what you typed is kept.";

function Notice(): ReactElement | null {
  const [params] = useSearchParams();
  const draft = useDraft();
  const key = params.get("notice");
  const notice = key !== null && Object.hasOwn(NOTICES, key) ? NOTICES[key] : undefined;
  return notice ? (
    <Banner kind="info" title={notice.title}>
      {key === "expired" && draft.has() ? DRAFT_KEPT : notice.text}
    </Banner>
  ) : null;
}

/**
 * `/login`: a username, then the code that was mailed. Both steps share the page, its title and
 * one polite status region that is always in the DOM so changes are announced.
 *
 * @example
 * <Route element={<LoginPage />} path="/login" />
 */
export function LoginPage(): ReactElement {
  usePageTitle("Sign in");
  const signIn = useSignIn();
  const { maskedAddress } = signIn;
  return (
    <Layout>
      <div className="mx-auto flex max-w-xl flex-col gap-4 px-6 py-12">
        <h1 className="font-display text-2xl text-text">{maskedAddress === null ? "Sign in" : "Enter your code"}</h1>
        <Notice />
        <div className="sr-only" role="status">
          {statusText(signIn)}
        </div>
        {maskedAddress === null ? (
          <UsernameStep failure={signIn.requestFailure} onSubmit={signIn.requestCode} sending={signIn.sending} />
        ) : (
          <CodeStep
            codeKey={signIn.codeKey}
            failure={signIn.failure}
            maskedAddress={maskedAddress}
            onSubmit={signIn.verifyCode}
            onUseAnotherUsername={signIn.useAnotherUsername}
            resend={signIn.resend}
            verifying={signIn.verifying}
          />
        )}
      </div>
    </Layout>
  );
}
