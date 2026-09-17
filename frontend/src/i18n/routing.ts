import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["fr", "en"],
  defaultLocale: "fr",
  // URL prefix strategy: always show locale prefix
  localePrefix: "always",
});
