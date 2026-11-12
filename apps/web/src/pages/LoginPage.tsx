import type { ReactElement } from "react";
import { useSearchParams } from "react-router";

import { Banner } from "@/components/Banner";
import { Layout } from "@/components/Layout";
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

function Notice(): ReactElement | null {
  const [params] = useSearchParams();
  const key = params.get("notice");
  const notice = key !== null && Object.hasOwn(NOTICES, key) ? NOTICES[key] : undefined;
  return notice ? (
    <Banner kind="info" title={notice.title}>
      {notice.text}
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
          <UsernameStep failed={signIn.requestFailed} onSubmit={signIn.requestCode} sending={signIn.sending} />
        ) : (
          <CodeStep
            failure={signIn.failure}
            maskedAddress={maskedAddress}
            onSubmit={signIn.verifyCode}
            onUseAnotherUsername={signIn.useAnotherUsername}
            verifying={signIn.verifying}
          />
        )}
      </div>
    </Layout>
  );
}
