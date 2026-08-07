import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AuthPage } from "./AuthPage";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("./ThemeToggle", () => ({
  ThemeToggle: () => <button type="button">Theme</button>,
}));

describe("AuthPage", () => {
  it("starts Google OAuth as a full-page, same-tab navigation", () => {
    render(<AuthPage mode="login" />);

    const googleLink = screen.getByRole("link", {
      name: "Continue with Google",
    });

    expect(googleLink).toHaveAttribute("href", "/api/auth/google/start");
    expect(googleLink).not.toHaveAttribute("target");
  });
});
