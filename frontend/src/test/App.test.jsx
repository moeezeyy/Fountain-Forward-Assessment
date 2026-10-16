import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

// Covers the required frontend scenario: login, inventory display, and an
// allowed update, by stubbing the backend over fetch so the test runs
// standalone without a live API.
function jsonResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

describe("dealership inventory app", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("logs in, shows the dealership-scoped inventory, and saves an admin update", async () => {
    const vehicle = {
      id: "veh-north-1",
      dealership_id: "dealership-north",
      make: "Toyota",
      model: "Camry",
      year: 2022,
      status: "available",
      version: 1,
      updated_at: "2026-01-01T00:00:00Z",
    };

    const fetchMock = vi.fn((url, options = {}) => {
      const method = options.method || "GET";

      if (url.endsWith("/api/auth/me") && method === "GET") {
        return jsonResponse({ detail: "not authenticated" }, 401);
      }
      if (url.endsWith("/api/auth/login") && method === "POST") {
        return jsonResponse({
          id: "user-north-admin1",
          email: "admin1@northgate.test",
          role: "admin",
          dealership_id: "dealership-north",
        });
      }
      if (url.endsWith("/api/vehicles") && method === "GET") {
        return jsonResponse([vehicle]);
      }
      if (url.includes("/api/vehicles/veh-north-1") && method === "PATCH") {
        return jsonResponse({ ...vehicle, status: "sold", version: 2 });
      }
      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });
    global.fetch = fetchMock;

    const user = userEvent.setup();
    render(<App />);

    // Login screen appears once the initial session check (401) resolves.
    await screen.findByText("Dealership Inventory");
    await user.type(screen.getByLabelText("Email"), "admin1@northgate.test");
    await user.type(screen.getByLabelText("Password"), "Passw0rd!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Inventory list renders with the dealership-scoped vehicle.
    await screen.findByText("Toyota");
    expect(screen.getByText("available")).toBeInTheDocument();

    // Admin performs an allowed update.
    await user.click(screen.getByRole("button", { name: /edit/i }));
    const statusSelect = screen.getByRole("combobox");
    await userEvent.selectOptions(statusSelect, "sold");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText("sold")).toBeInTheDocument());

    const patchCall = fetchMock.mock.calls.find(
      ([url, opts]) => url.includes("/api/vehicles/veh-north-1") && opts?.method === "PATCH"
    );
    expect(JSON.parse(patchCall[1].body)).toMatchObject({ status: "sold", version: 1 });
  });
});
