import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../api/auth";
import { AuthPage } from "./AuthPage";

const { state, saveUsername } = vi.hoisted(() => ({
  state: { user: null as AuthUser | null },
  saveUsername: vi.fn(),
}));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ user: state.user, loading: false, logout: vi.fn(), updateUsername: saveUsername }),
}));
vi.mock("../api/auth", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/auth")>(),
  listIdentities: vi.fn().mockResolvedValue([{ id: "email-1", provider: "email" }]),
}));

describe("Account profile", () => {
  beforeEach(() => {
    state.user = { user_id: "user-1", email: "private@example.com", email_verified: true };
    saveUsername.mockReset();
    saveUsername.mockResolvedValue(undefined);
  });

  it("lets an existing account choose a username and preserves sign-out access", async () => {
    render(<AuthPage mode="account" />);
    expect(screen.getByText("Food explorer")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Email address" })).toBeInTheDocument();
    const input = screen.getByRole("textbox", { name: "Username" });
    fireEvent.change(input, { target: { value: "Ramen_Fan" } });
    fireEvent.click(screen.getByRole("button", { name: "Save username" }));
    await waitFor(() => expect(saveUsername).toHaveBeenCalledWith("ramen_fan"));
    expect(await screen.findByRole("status")).toHaveTextContent("Username saved.");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
  });

  it("keeps the entered name and allows retry after a rejected save", async () => {
    state.user!.username = "existing_name";
    saveUsername.mockRejectedValueOnce(new Error("That username is taken. Try another one."));
    render(<AuthPage mode="account" />);
    const input = screen.getByRole("textbox", { name: "Username" });
    expect(input).toHaveValue("existing_name");
    expect(screen.getByRole("button", { name: "Save username" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "taken_name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save username" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That username is taken");
    expect(input).toHaveValue("taken_name");
    expect(input).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(input, { target: { value: "new_name" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save username" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Username saved.");
  });
});
