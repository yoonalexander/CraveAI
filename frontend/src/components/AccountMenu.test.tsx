import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountMenu } from "./AccountMenu";

const { authState, logout } = vi.hoisted(() => ({
  authState: {
    user: {
      user_id: "user-1",
      email: "signed-in@example.com",
      email_verified: true,
    } as null | { user_id: string; email: string; email_verified: boolean },
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
