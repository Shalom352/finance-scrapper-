import { sectionMetadata } from "@/lib/pageMetadata";

export const generateMetadata = sectionMetadata("data_quality");

export default function SectionLayout({ children }: { children: React.ReactNode }) {
  return children;
}
