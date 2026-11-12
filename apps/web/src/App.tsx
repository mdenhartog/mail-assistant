import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Navigate, Outlet, RouterProvider, useNavigate } from "react-router";
import type { RouteObject } from "react-router";

import { onApiRefusal, setCsrfToken } from "@/api/client";
import { AccessRefused } from "@/pages/AccessRefused";
import { ClockContext, systemClock } from "@/pages/clock";
import type { Clock } from "@/pages/clock";
import { LoginPage } from "@/pages/LoginPage";
import { NotFound } from "@/pages/NotFound";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { paths } from "@/router/paths";
import { LoginGate, ProtectedShell } from "@/session/SessionRoutes";

/**
 * Root route: reacts to a 401 (back to the login page with the expired notice) and to a 403
 * (full-page refusal) from any request. Both drop everything the session cached.
 */
function Root(): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [refused, setRefused] = useState(false);

  useEffect(
    () =>
      onApiRefusal((status) => {
        setCsrfToken(null);
        queryClient.clear();
        if (status === 401) {
          void navigate(paths.loginExpired);
        } else {
          setRefused(true);
        }
      }),
    [navigate, queryClient],
  );

  if (refused) {
    return (
      <AccessRefused
        onBack={() => {
          setRefused(false);
        }}
      />
    );
  }
  return <Outlet />;
}

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: paths.root, element: <Navigate replace to={paths.settings} /> },
      { path: paths.login, element: <LoginGate />, children: [{ index: true, element: <LoginPage /> }] },
      { path: paths.settings, element: <ProtectedShell />, children: [{ index: true, element: <SettingsPage /> }] },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export interface AppProps {
  router: Parameters<typeof RouterProvider>[0]["router"];
  queryClient?: QueryClient;
  /** Source of time for countdowns; tests pass their own. */
  clock?: Clock;
}

/**
 * Application shell: query client plus router. Nothing is retried; a failed request is shown, not repeated.
 *
 * @example
 * <App router={createBrowserRouter(routes)} />
 */
export function App({ router, queryClient, clock }: AppProps): ReactElement {
  const [fallbackClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={queryClient ?? fallbackClient}>
      <ClockContext value={clock ?? systemClock}>
        <RouterProvider router={router} />
      </ClockContext>
    </QueryClientProvider>
  );
}
