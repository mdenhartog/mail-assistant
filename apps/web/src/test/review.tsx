import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { ReviewPage } from "@/features/review/ReviewPage";

/** Renders the Review moves page inside the providers it needs and waits for its heading. */
export async function renderReview(): Promise<HTMLElement> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const { container } = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { level: 1, name: "Review moves" });
  return container;
}
