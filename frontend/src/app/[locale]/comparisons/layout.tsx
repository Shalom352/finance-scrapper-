import { sectionMetadata } from "@/lib/pageMetadata";

export const generateMetadata = sectionMetadata("comparisons");

export default function SectionLayout({ children }: { children: React.ReactNode }) {
  return children;
}
