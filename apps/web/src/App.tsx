import type { QueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { createMemoryRouter, RouteObject } from "react-router";

export const routes: RouteObject[] = [];

export interface AppProps {
  router: ReturnType<typeof createMemoryRouter>;
  queryClient?: QueryClient;
}

export function App({ router }: AppProps): ReactElement {
  return <main data-routes={router.routes.length} />;
}
