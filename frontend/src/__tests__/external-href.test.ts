/** Security tests of 22/10/2026: a link built from the data is only ever http(s). */
import { describe, expect, it } from "vitest";
import { externalHref } from "@/lib/url";

describe("externalHref", () => {
  it("keeps http and https links", () => {
    expect(externalHref("https://www.bceao.int/fr/doc.pdf")).toBe("https://www.bceao.int/fr/doc.pdf");
    expect(externalHref("http://example.org")).toBe("http://example.org/");
  });
  it("never links another scheme, a relative path or garbage", () => {
    for (const bad of ["javascript:alert(1)", "JAVASCRIPT:alert(1)", " javascript:alert(1)", "data:text/html,x",
                       "vbscript:x", "/fr/deals", "not a url", "", null, undefined]) {
      expect(externalHref(bad)).toBeUndefined();
    }
  });
});
