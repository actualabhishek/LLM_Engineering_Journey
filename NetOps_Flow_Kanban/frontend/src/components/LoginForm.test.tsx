import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "./LoginForm";
import { ApiError, login } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  login: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public status: number) {
      super(`Request failed: ${status}`);
    }
  },
}));

describe("LoginForm", () => {
  it("calls onSuccess with the token on valid credentials", async () => {
    vi.mocked(login).mockResolvedValue("token-123");
    const onSuccess = vi.fn();
    render(<LoginForm onSuccess={onSuccess} />);

    await userEvent.type(screen.getByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).toHaveBeenCalledWith("user", "password");
    expect(onSuccess).toHaveBeenCalledWith("token-123");
  });

  it("shows an error message when login fails", async () => {
    vi.mocked(login).mockRejectedValue(new ApiError(401));
    const onSuccess = vi.fn();
    render(<LoginForm onSuccess={onSuccess} />);

    await userEvent.type(screen.getByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid username or password")).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("says the server is unreachable when the request never lands", async () => {
    vi.mocked(login).mockRejectedValue(new TypeError("Failed to fetch"));
    render(<LoginForm onSuccess={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByText(/Cannot reach the server/)
    ).toBeInTheDocument();
  });

  it("reports a server error separately from bad credentials", async () => {
    vi.mocked(login).mockRejectedValue(new ApiError(500));
    render(<LoginForm onSuccess={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/server error 500/)).toBeInTheDocument();
  });
});
