import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { Navigate, Outlet, useNavigate } from "react-router";

import { Banner } from "@/components/Banner";
import { Layout } from "@/components/Layout";
import { apiFetch, setCsrfToken } from "@/api/client";
import { paths } from "@/router/paths";
import { useSession } from "@/session/useSession";

function Loading(): ReactElement {
  return (
    <Layout>
      <p className="px-6 py-12 text-text-muted" role="status">
        Loading
      </p>
    </Layout>
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

/** Pages that need a session: the layout with the masked address and Sign out, then the page. */
export function ProtectedShell(): ReactElement {
  const { data, isPending, isError } = useSession();
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
  if (isPending) {
    return <Loading />;
  }
  if (isError) {
    return (
      <Layout>
        <div className="px-6 py-12">
          <Banner focusOnMount kind="danger" title="Could not load your session.">
            Reload the page.
          </Banner>
        </div>
      </Layout>
    );
  }
  if (data === null) {
    return <Navigate replace to={paths.login} />;
  }
  return (
    <Layout
      account={{
        maskedAddress: data.maskedAddress,
        onSignOut: () => {
          logout.mutate();
        },
        signingOut: logout.isPending,
        signOutFailed: logout.isError,
      }}
    >
      <Outlet />
    </Layout>
  );
}
