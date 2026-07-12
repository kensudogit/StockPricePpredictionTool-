import { describe, expect, it, vi, beforeEach } from "vitest";

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls /api/v1 health with relative URL when NEXT_PUBLIC_API_URL is empty", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        status: "ok",
        environment: "test",
        trading_mode: "paper",
        providers: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    // dynamic import after stub — module reads API_URL at load time
    vi.resetModules();
    const { api } = await import("@/lib/api");
    const data = await api.health();
    expect(data.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalled();
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("/api/v1/health");
  });

  it("builds ingest POST body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ bars: 1, source: "yahoo" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const { api } = await import("@/lib/api");
    await api.ingest("7203.T");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.ticker).toBe("7203.T");
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        statusText: "Bad Request",
        text: async () => "fail",
      }),
    );
    vi.resetModules();
    const { api } = await import("@/lib/api");
    await expect(api.health()).rejects.toThrow("fail");
  });
});
