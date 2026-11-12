// ESLint flat config enforcing guardrail-typescript, guardrail-react, guardrail-tanstack-query
// and guardrail-a11y. Complexity limits back the cleanup-gate.
import pluginQuery from "@tanstack/eslint-plugin-query";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["src/api/schema.d.ts", "dist", "coverage", "playwright-report", "test-results"] },
  ...tseslint.configs.strictTypeChecked,
  ...pluginQuery.configs["flat/recommended"],
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  jsxA11y.flatConfigs.recommended,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    settings: { react: { version: "detect" } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "react/no-danger": "error",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-non-null-assertion": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/explicit-module-boundary-types": "error",
      complexity: ["error", 8],
      "max-depth": ["error", 3],
      "max-lines-per-function": ["error", { max: 60, skipBlankLines: true, skipComments: true }],
      "no-console": ["error", { allow: ["warn", "error"] }],
      "no-restricted-globals": ["error", { name: "fetch", message: "Use the API layer in src/api (guardrail-tanstack-query)." }],
    },
  },
  {
    // The API layer is the one place that may call fetch.
    files: ["src/api/**/*.ts"],
    rules: { "no-restricted-globals": "off" },
  },
  {
    files: ["**/*.test.{ts,tsx}", "e2e/**/*.ts"],
    rules: { "max-lines-per-function": "off", "no-restricted-globals": "off" },
  },
  {
    // Playwright fixtures call `use()`, which is not a React hook.
    files: ["e2e/**/*.ts"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
  {
    files: ["*.config.{ts,mjs}", "eslint.config.mjs"],
    ...tseslint.configs.disableTypeChecked,
  },
);
