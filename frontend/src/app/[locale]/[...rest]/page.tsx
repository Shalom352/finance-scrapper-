import { notFound } from "next/navigation";

/** Any unknown path under a locale renders the app's not-found page (inside the shell, translated). */
export default function UnknownPage() {
  notFound();
}
