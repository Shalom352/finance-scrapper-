import { sectionMetadata } from "@/lib/pageMetadata";

export const generateMetadata = sectionMetadata("syndication");

export default function SectionLayout({ children }: { children: React.ReactNode }) {
  return children;
}
