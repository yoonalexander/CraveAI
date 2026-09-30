import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../api/auth";

import { AccountMenu } from "./AccountMenu";

const { authState, logout } = vi.hoisted(() => ({
  authState: {
    user: {
      user_id: "user-1",
      email: "signed-in@example.com",
      email_verified: true,
    } as AuthUser | null,
    loading: false,
    status: "authenticated",
  },
  logout: vi.fn(),
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: authState.user,
    loading: authState.loading,
    status: authState.status,
    login: vi.fn(),
    logout,
    refresh: vi.fn(),
  }),
}));

describe("AccountMenu", () => {
  beforeEach(() => {
    authState.user = {
      user_id: "user-1",
      email: "signed-in@example.com",
      email_verified: true,
    };
    authState.loading = false;
    authState.status = "authenticated";
    logout.mockReset();
    logout.mockResolvedValue(undefined);
  });

  it("keeps the sign-out label on one line", () => {
    render(<AccountMenu />);

    expect(screen.getByRole("button", { name: "Sign out" })).toHaveClass(
      "whitespace-nowrap",
      "shrink-0",
    );
  });

  it("shows an accessible profile icon without exposing the email", () => {
    authState.user = { ...authState.user!, username: "ramen_fan" };
    render(<AccountMenu />);
    const profile = screen.getByRole("link", { name: "Account: ramen_fan" });
    expect(profile).toHaveAttribute("href", "/account");
    expect(profile.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(profile).toHaveTextContent("");
    expect(screen.queryByText("signed-in@example.com")).not.toBeInTheDocument();
  });

  it("keeps legacy accounts accessible with an email-independent fallback", () => {
    render(<AccountMenu />);
    expect(screen.getByRole("link", { name: "Account: Food explorer" })).toHaveAttribute("href", "/account");
    expect(screen.queryByText("signed-in@example.com")).not.toBeInTheDocument();
  });

  it("asks for confirmation before signing out", async () => {
    render(<AccountMenu />);

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(logout).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog", { name: "Sign out of CraveAI?" });
    expect(dialog).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();

    fireEvent.click(within(dialog).getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
  });

  it("cancels without signing out", () => {
    render(<AccountMenu />);

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(logout).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toHaveFocus();
  });

  it("keeps keyboard focus in the confirmation and returns it on Escape", () => {
    render(<AccountMenu />);
    const trigger = screen.getByRole("button", { name: "Sign out" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("alertdialog");
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    const confirm = within(dialog).getByRole("button", { name: "Sign out" });
    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(cancel).toHaveFocus();
    fireEvent.keyDown(cancel, { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("does not show login until account checking finishes", () => {
    authState.user = null;
    authState.loading = true;
    authState.status = "checking";

    render(<AccountMenu />);

    expect(screen.getByText("Checking account…")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
  });

  it("distinguishes an unavailable account check from a confirmed guest", () => {
    authState.user = null;
    authState.status = "offline";

    const { rerender } = render(<AccountMenu />);
    expect(screen.getByText("Account unavailable — retrying…")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();

    authState.status = "guest";
    rerender(<AccountMenu />);
    expect(screen.getByRole("link", { name: "Log in" })).toBeInTheDocument();
  });
});
