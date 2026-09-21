import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";

const { authState } = vi.hoisted(() => ({
  authState: {
    user: null as null | { user_id: string; email: string; email_verified: boolean },
    loading: false,
    status: "guest",
  },
}));

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: authState.user,
    loading: authState.loading,
    status: authState.status,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

describe("Sidebar", () => {
  beforeEach(() => {
    authState.user = null;
    authState.loading = false;
    authState.status = "guest";
  });

  it("announces weather loading in the collapsed sidebar and replaces it when settled", () => {
    const props = {
      collapsed: true,
      currentPath: "/",
      mobileOpen: false,
      onCloseMobile: vi.fn(),
      onNavigate: vi.fn(),
      onToggle: vi.fn(),
    };
    const { rerender } = render(<Sidebar {...props} weather={null} weatherLoading />);

    expect(screen.getByRole("status", { name: "Checking weather" })).toHaveAttribute("title", "Checking weather");
    expect(screen.queryByText("Weather unavailable")).not.toBeInTheDocument();

    rerender(<Sidebar {...props} weather={{ temperature: 18.4, condition: "Clear", isDay: true }} weatherLoading={false} />);
    expect(screen.getByRole("status", { name: "18°C Clear" })).toBeInTheDocument();
    expect(screen.queryByText("Checking weather")).not.toBeInTheDocument();

    rerender(<Sidebar {...props} weather={null} weatherLoading={false} />);
    expect(screen.getByRole("status", { name: "Weather unavailable" })).toBeInTheDocument();
    expect(screen.queryByText("Checking weather")).not.toBeInTheDocument();
  });

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

  it("does not offer login while account status is still loading", () => {
    authState.loading = true;
    authState.status = "checking";

    render(
      <Sidebar
        collapsed={false}
        currentPath="/"
        mobileOpen={false}
        onCloseMobile={vi.fn()}
        onNavigate={vi.fn()}
        onToggle={vi.fn()}
        weather={null}
        weatherLoading={false}
      />,
    );

    expect(screen.getByText("Checking account…")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log in" })).not.toBeInTheDocument();
  });
});
