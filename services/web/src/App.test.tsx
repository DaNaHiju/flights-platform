import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { PROVIDER_DOWN_MESSAGE } from "./api";
import { SearchForm } from "./SearchForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SearchForm", () => {
  it("renders origin, destination and date fields and a submit button", () => {
    render(<SearchForm onSearch={() => {}} disabled={false} />);

    expect(screen.getByLabelText("Origen")).toBeTruthy();
    expect(screen.getByLabelText("Destino")).toBeTruthy();
    expect(screen.getByLabelText("Fecha")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Buscar" })).toBeTruthy();
  });
});

describe("App", () => {
  it("shows the provider-down message when the API answers 502", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve(
          url.startsWith("/api/deals")
            ? new Response(JSON.stringify({ deals: [] }), { status: 200 })
            : new Response(JSON.stringify({ error: "provider_unavailable" }), {
                status: 502,
              }),
        ),
      ),
    );

    render(<App />);
    fireEvent.change(screen.getByLabelText("Origen"), { target: { value: "eze" } });
    fireEvent.change(screen.getByLabelText("Destino"), { target: { value: "mad" } });
    fireEvent.change(screen.getByLabelText("Fecha"), {
      target: { value: "2099-01-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(PROVIDER_DOWN_MESSAGE),
    );
  });
});
