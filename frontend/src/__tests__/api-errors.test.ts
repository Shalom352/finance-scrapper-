/**
 * Phase 13 — API client error handling: the backend envelope { error: { code, message } }
 * is read; a network failure (status 0) is distinguished from an invalid answer; GET requests
 * send no Content-Type (no needless CORS preflight).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, errorFromResponse, getDeal, getDeals } from "@/lib/api";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("ApiError", () => {
  it("reads the backend error envelope", async () => {
    const err = await errorFromResponse(json({ error: { code: "CONFLICT", message: "stale", details: {} } }, 409));
    expect([err.status, err.code, err.message]).toEqual([409, "CONFLICT", "stale"]);
  });

  it("falls back on the status for a non-JSON answer", async () => {
    const err = await errorFromResponse(new Response("<html>502</html>", { status: 502 }));
    expect([err.status, err.code, err.message]).toEqual([502, "HTTP_502", "HTTP 502"]);
  });

  it.each([404, 413, 422, 500])("keeps the HTTP status %i", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: { code: "X", message: "m" } }, status)));
    await expect(getDeal("d")).rejects.toMatchObject({ status, code: "X" });
  });

  it("a network failure is status 0, an invalid JSON body is not", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(getDeal("d")).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json", { status: 200 })));
    await expect(getDeal("d")).rejects.toMatchObject({ status: 200, code: "INVALID_RESPONSE" });
    expect(new ApiError(0, "x")).toBeInstanceOf(Error);
  });

  it("GET requests send no Content-Type header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ items: [], total: 0, page: 1, page_size: 20, has_next: false, has_prev: false }));
    vi.stubGlobal("fetch", fetchMock);
    await getDeals({ country: "SN" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/deals\?country=SN$/);
    expect(Object.keys(init.headers)).not.toContain("Content-Type");
  });

  it("missing numeric fields stay null, never 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({
      items: [{ id: "d", title: "t", amount: null, borrowers: null, arrangers: undefined }],
      total: 1, page: 1, page_size: 20, has_next: false, has_prev: false,
    })));
    const res = await getDeals({});
    expect(res.items[0].amount).toBeNull();
    expect(res.items[0].borrowers).toEqual([]);
  });
});
