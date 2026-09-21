import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import { fetchCurrentUser } from "../api/auth";

vi.mock("../api/auth", () => ({
  fetchCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));

const mockedFetchCurrentUser = vi.mocked(fetchCurrentUser);

function AccountState(): JSX.Element {
  const { loading, status, user } = useAuth();
  return (
    <div>
      <span>{loading ? "checking" : status}</span>
      <span>{user?.email || "no confirmed user"}</span>
    </div>
  );
}

async function flushEffects(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("AuthProvider startup", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedFetchCurrentUser.mockReset();
  });

  it("leaves the blocking state after a deadline and recovers in the background", async () => {
    mockedFetchCurrentUser
      .mockImplementationOnce((signal?: AbortSignal) => new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("Timed out", "AbortError")));
      }))
      .mockResolvedValueOnce({
        user_id: "user-1",
        email: "signed-in@example.com",
        email_verified: true,
      });

    render(<AuthProvider><AccountState /></AuthProvider>);
    expect(screen.getByText("checking")).toBeInTheDocument();

    await act(async () => vi.advanceTimersByTime(4_000));
    await flushEffects();
    expect(screen.getByText("offline")).toBeInTheDocument();
    expect(screen.getByText("no confirmed user")).toBeInTheDocument();

    await act(async () => vi.advanceTimersByTime(15_000));
    await flushEffects();
    expect(screen.getByText("authenticated")).toBeInTheDocument();
    expect(screen.getByText("signed-in@example.com")).toBeInTheDocument();
  });
});
