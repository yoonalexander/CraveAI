import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

describe("Sidebar", () => {
  it("renders the complete navigation and marks the current page", () => {
    render(
      <Sidebar
        collapsed={false}
        currentPath="/likes"
        mobileOpen={false}
        onCloseMobile={vi.fn()}
        onNavigate={vi.fn()}
        onToggle={vi.fn()}
        weather={{ temperature: 18.4, condition: "Clear", isDay: true }}
        weatherLoading={false}
      />,
    );

    expect(screen.getByRole("link", { name: "Likes" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("18°C")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See plans and pricing" })).toBeInTheDocument();
  });

  it("routes New chat with reset semantics and closes the mobile drawer", () => {
    const navigate = vi.fn();
    const close = vi.fn();
    render(
      <Sidebar
        collapsed={false}
        currentPath="/history"
        mobileOpen
        onCloseMobile={close}
        onNavigate={navigate}
        onToggle={vi.fn()}
        weather={null}
        weatherLoading={false}
      />,
    );
    expect(document.body).toHaveClass("crave-overlay-open");
    fireEvent.click(screen.getByRole("link", { name: "New chat" }));
    expect(navigate).toHaveBeenCalledWith("/", true);
    expect(close).toHaveBeenCalled();
  });

  it("exposes collapsed labels as tooltips", () => {
    render(
      <Sidebar
        collapsed
        currentPath="/"
        mobileOpen={false}
        onCloseMobile={vi.fn()}
        onNavigate={vi.fn()}
        onToggle={vi.fn()}
        weather={null}
        weatherLoading={false}
      />,
    );
    expect(screen.getByRole("link", { name: "Discovery" })).toHaveAttribute("title", "Discovery");
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });
});
