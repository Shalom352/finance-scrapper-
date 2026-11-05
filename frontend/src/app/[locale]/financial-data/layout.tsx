import { sectionMetadata } from "@/lib/pageMetadata";

export const generateMetadata = sectionMetadata("financial_data");

export default function SectionLayout({ children }: { children: React.ReactNode }) {
  return children;
}
