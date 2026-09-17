import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "UMOA Banking Intelligence",
};

// Root layout — minimal shell.
// Actual content is in [locale]/layout.tsx
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
