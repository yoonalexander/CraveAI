import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountMenu } from "./AccountMenu";

const { logout } = vi.hoisted(() => ({ logout: vi.fn() }));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: {
      user_id: "user-1",
      email: "signed-in@example.com",
      email_verified: true,
    },
    loading: false,
    login: vi.fn(),
    logout,
    refresh: vi.fn(),
  }),
}));

describe("AccountMenu", () => {
  beforeEach(() => {
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
});
