import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { Navigate, Outlet, useNavigate } from "react-router";

import { apiFetch, setCsrfToken } from "@/api/client";
import { paths } from "@/router/paths";
import { useSession } from "@/session/useSession";

function Loading(): ReactElement {
  return (
    <p className="px-6 py-12 text-text-muted" role="status">
      Loading
    </p>
  );
}

/** `/login` is for visitors only: a live session goes straight to the settings. */
export function LoginGate(): ReactElement {
  const { data, isPending, isError } = useSession();
  if (isPending) {
    return <Loading />;
  }
  if (!isError && data !== null) {
    return <Navigate replace to={paths.settings} />;
  }
  return <Outlet />;
}

function SignOutButton(): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: () => apiFetch("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      setCsrfToken(null);
      queryClient.clear();
      void navigate(paths.login);
    },
  });
  return (
    <div className="flex items-center gap-3">
      {logout.isError ? <p role="alert">Could not sign out. Try again.</p> : null}
      <button
        className="min-h-11 rounded-full border border-border px-5 text-text"
        onClick={() => {
          logout.mutate();
        }}
        type="button"
      >
        Sign out
      </button>
    </div>
  );
}

/** Pages that need a session: header with the masked address and Sign out, then the page. */
export function ProtectedShell(): ReactElement {
  const { data, isPending, isError } = useSession();
  if (isPending) {
    return <Loading />;
  }
  if (isError) {
    return (
      <p className="px-6 py-12 text-text" role="alert">
        Could not load your session. Reload the page.
      </p>
    );
  }
  if (data === null) {
    return <Navigate replace to={paths.login} />;
  }
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-divider px-6 py-4">
        <span className="font-display text-lg text-text">Mail Assistant</span>
        <p className="text-sm text-text-muted">Signed in as {data.maskedAddress}</p>
        <SignOutButton />
      </header>
      <Outlet />
    </>
  );
}
