/** Route paths used by the router and by every link or redirect. */
export const paths = {
  root: "/",
  login: "/login",
  loginExpired: "/login?notice=expired",
  settings: "/settings",
  categories: "/categories",
  review: "/review",
} as const;
