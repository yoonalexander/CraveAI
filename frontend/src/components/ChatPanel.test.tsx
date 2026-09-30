import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";
import { ChatQuotaError, ChatTimeoutError, fetchChatStatus, streamChat } from "../api/chat";

const authState = vi.hoisted(() => ({
  user: null as null | { user_id: string; email: string; email_verified: boolean },
}));

vi.mock("../api/chat", async () => {
  const actual = await vi.importActual<typeof import("../api/chat")>("../api/chat");
  return {
    ...actual,
    fetchChatStatus: vi.fn(),
    streamChat: vi.fn(),
  };
});

vi.mock("../context/AuthContext", () => ({
  useAuth: () => authState,
}));

const mockedSendChat = vi.mocked(streamChat);
const mockedFetchChatStatus = vi.mocked(fetchChatStatus);

beforeEach(() => {
  authState.user = null;
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.sessionStorage.setItem("craveai-age-18", "true");
  mockedFetchChatStatus.mockReset();
  mockedFetchChatStatus.mockRejectedValue(new Error("unavailable"));
  mockedSendChat.mockReset();
  mockedSendChat.mockResolvedValue({
    reply: "Try the neighbourhood noodle house.",
    messages: [],
    recommendations: [],
  });
});

describe("ChatPanel", () => {
  it("keeps the decorative indicator mounted through multiple genuine stage updates and completion", async () => {
    let finish!: (value: Awaited<ReturnType<typeof streamChat>>) => void;
    mockedSendChat.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const { container } = render(<ChatPanel />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Noodles" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    const indicator = container.querySelector(".chat-thinking-dots");
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Getting your search ready…");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(indicator).toHaveAttribute("aria-hidden", "true");
    expect(status).not.toContainElement(indicator as HTMLElement);
    for (const stage of ["Finding nearby restaurants…", "Checking public menus for your preferences…", "Putting your recommendations together…"]) {
      act(() => mockedSendChat.mock.calls[0][2]?.onStage?.(stage));
      expect(status).toHaveTextContent(stage);
      expect(container.querySelector(".chat-thinking-dots")).toBe(indicator);
    }
    await act(async () => finish({ reply: "Here are your noodle spots.", messages: [], recommendations: [] }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(container.querySelector(".chat-thinking")).not.toBeInTheDocument();
    expect(composer).toBeEnabled();
  });

  it("stops the active response and ignores its late stages, results and cleanup during a retry", async () => {
    const finishes: Array<(value: Awaited<ReturnType<typeof streamChat>>) => void> = [];
    mockedSendChat.mockImplementation(() => new Promise((resolve) => { finishes.push(resolve); }));
    const onRecommendations = vi.fn();
    render(<ChatPanel onRecommendations={onRecommendations} />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "First request" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    const [, firstOptions, firstCallbacks] = mockedSendChat.mock.calls[0];
    act(() => mockedSendChat.mock.calls[0][2]?.onStage?.("First stage"));
    fireEvent.click(screen.getByRole("button", { name: "Stop response" }));
    expect(firstOptions.signal?.aborted).toBe(true);
    expect(screen.queryByText("First stage")).not.toBeInTheDocument();
    expect(screen.getByText("Response stopped.")).toBeInTheDocument();
    expect(composer).toBeEnabled();
    fireEvent.change(composer, { target: { value: "Retry" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    expect(screen.getByText("Getting your search ready…")).toBeInTheDocument();
    act(() => mockedSendChat.mock.calls[1][2]?.onStage?.("Fresh stage"));
    const stale = { name: "Stale restaurant", place_id: "stale" };
    act(() => {
      firstCallbacks?.onStage?.("Stale stage");
      firstCallbacks?.onRecommendation?.(stale);
    });
    await act(async () => finishes[0]({ reply: "Stale reply", messages: [], recommendations: [stale] }));
    expect(screen.queryByText("Stale reply")).not.toBeInTheDocument();
    expect(screen.queryByText("Stale stage")).not.toBeInTheDocument();
    expect(screen.getByText("Fresh stage")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop response" })).toBeEnabled();
    expect(onRecommendations).not.toHaveBeenCalledWith([stale]);
    await act(async () => finishes[1]({ reply: "Fresh reply", messages: [], recommendations: [] }));
    expect(screen.getByText("Fresh reply")).toBeInTheDocument();
    expect(screen.queryByText("Fresh stage")).not.toBeInTheDocument();
  });

  it.each([new Error("provider failure"), new ChatTimeoutError(), new ChatQuotaError("Daily limit reached.")])("clears progress after an error and starts the next attempt without an old stage (%s)", async (failure) => {
    mockedSendChat.mockImplementationOnce(async (_query, _options, callbacks) => {
      callbacks?.onStage?.("Checking menus…");
      throw failure;
    });
    render(<ChatPanel />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Dinner" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    await screen.findByRole("alert");
    expect(screen.queryByText("Checking menus…")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop response" })).not.toBeInTheDocument();
    expect(composer).toBeEnabled();
    mockedSendChat.mockImplementationOnce(() => new Promise(() => undefined));
    fireEvent.change(composer, { target: { value: "Try again" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    expect(screen.getByText("Getting your search ready…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop response" }));
  });

  it("aborts pending work on unmount and ignores subsequent recommendation callbacks", () => {
    mockedSendChat.mockImplementationOnce(() => new Promise(() => undefined));
    const onRecommendations = vi.fn();
    const { unmount } = render(<ChatPanel onRecommendations={onRecommendations} />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Dinner" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    const options = mockedSendChat.mock.calls[0][1];
    unmount();
    expect(options.signal?.aborted).toBe(true);
    mockedSendChat.mock.calls[0][2]?.onRecommendation?.({ name: "Late restaurant" });
    expect(onRecommendations).not.toHaveBeenCalled();
  });
  it("shows menu evidence counts, distinct sources, and a map action", async () => {
    const recommendation = {
      name: "Spicy Kitchen", place_id: "spicy", lat: 43.7, lng: -79.4,
      confidence: "high" as const, match_score: 0.98, menu_match_count: 3,
      evidence: [
        { type: "official_website", label: "Site", source_url: "https://example.com/menu" },
        { type: "official_menu", label: "Spicy fish", source_url: "https://example.com/menu" },
        { type: "official_menu", label: "Spicy ribs", source_url: "https://example.com/menu" },
        { type: "official_website", label: "Home", source_url: "https://example.com" },
        { type: "provider_query", label: "Spicy", source_url: "https://maps.google.com" },
      ],
    };
    mockedSendChat.mockResolvedValue({ reply: "Try this kitchen.", messages: [], recommendations: [recommendation] });
    const onShowOnMap = vi.fn();
    render(<ChatPanel onShowOnMap={onShowOnMap} />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Spicy food" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    await screen.findByText("Strong match · 3 menu matches");
    expect(screen.queryByText(/98%/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View menu" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Restaurant website" })).toHaveAttribute("href", "https://example.com");
    expect(screen.queryByRole("link", { name: "View source" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Google Maps" })).toHaveAttribute("href", expect.stringContaining("query_place_id=spicy"));
    fireEvent.click(screen.getByRole("button", { name: "Show on map" }));
    expect(onShowOnMap).toHaveBeenCalledWith(recommendation);
  });

  it("keeps provider-only matches honest and hides map actions without coordinates", async () => {
    mockedSendChat.mockResolvedValue({ reply: "Nearby result.", messages: [], recommendations: [{
      name: "Nearby", confidence: "medium", menu_match_count: 0, match_score: 0.82,
      evidence: [{ type: "provider_query", label: "Spicy", source_url: "https://maps.google.com" }],
    }] });
    render(<ChatPanel onShowOnMap={vi.fn()} />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Spicy" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    await screen.findByText("Relevant match");
    expect(screen.queryByText(/menu matches|82%/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show on map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View source" })).not.toBeInTheDocument();
  });

  it("shows the published guest daily chat allowance", () => {
    render(<ChatPanel />);
    expect(screen.getByText("9 messages left today")).toBeInTheDocument();
  });

  it("replaces admin usage when authentication changes to a guest", async () => {
    authState.user = {
      user_id: "admin-user",
      email: "proto95430@gmail.com",
      email_verified: true,
    };
    mockedFetchChatStatus.mockResolvedValueOnce({
      usage: {
        limit: 0,
        used: 0,
        remaining: 0,
        reset_at: "2099-01-02T00:00:00Z",
        unlimited: true,
      },
    });
    const { rerender } = render(<ChatPanel />);
    await waitFor(() => expect(screen.getByText("Unlimited messages")).toBeInTheDocument());

    authState.user = null;
    mockedFetchChatStatus.mockResolvedValueOnce({
      usage: {
        limit: 9,
        used: 7,
        remaining: 2,
        reset_at: "2099-01-02T00:00:00Z",
      },
    });
    rerender(<ChatPanel />);

    await waitFor(() => expect(screen.getByText("2 messages left today")).toBeInTheDocument());
    expect(mockedFetchChatStatus).toHaveBeenCalledTimes(2);
  });

  it("starts empty and moves into conversation mode after Enter", async () => {
    const { container } = render(<ChatPanel />);
    expect(screen.getByRole("heading", { name: "What’s your craving today?" })).toBeVisible();
    expect(screen.getByText(/prompts and bounded context go to OpenAI/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(container.querySelector(".chat-panel")).toHaveClass("is-idle");

    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Cozy and spicy" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: false });

    expect(screen.getByText("Cozy and spicy")).toBeInTheDocument();
    expect(screen.queryByText(/your prompt and location may be sent to AI and search providers/i)).not.toBeInTheDocument();
    expect(screen.getByText("CraveAI can make mistakes. Check important details.")).toBeInTheDocument();
    expect(container.querySelector(".chat-panel")).toHaveClass("has-conversation");
    await waitFor(() => expect(screen.getByText("Try the neighbourhood noodle house.")).toBeInTheDocument());
    expect(mockedSendChat).toHaveBeenCalledWith(
      "Cozy and spicy",
      expect.objectContaining({ location: undefined, candidatePlaces: [], ageConfirmed: true }),
      expect.objectContaining({ onStage: expect.any(Function) }),
    );
  });

  it("uses Shift+Enter for a newline without submitting", () => {
    render(<ChatPanel />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "First line\nSecond line" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: true });

    expect(mockedSendChat).not.toHaveBeenCalled();
    expect(composer).toHaveValue("First line\nSecond line");
  });

  it("prevents duplicate submission while the assistant is loading", async () => {
    let resolveChat: ((value: Awaited<ReturnType<typeof streamChat>>) => void) | undefined;
    mockedSendChat.mockImplementation(
      () => new Promise((resolve) => { resolveChat = resolve; }),
    );
    render(<ChatPanel />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "Pizza" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    fireEvent.keyDown(composer, { key: "Enter" });

    expect(mockedSendChat).toHaveBeenCalledOnce();
    await act(async () => {
      resolveChat?.({ reply: "Pizza time.", messages: [], recommendations: [] });
    });
  });

  it("reports unsupported voice recording without requesting unavailable media", () => {
    render(<ChatPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Record voice input" }));
    expect(screen.getByText("Voice recording is not supported in this browser.")).toBeInTheDocument();
  });

  it("notifies the mobile sheet only when the first message starts a conversation", async () => {
    const onConversationStart = vi.fn();
    render(<ChatPanel onConversationStart={onConversationStart} />);
    const composer = screen.getByRole("textbox", { name: "Ask CraveAI" });
    fireEvent.change(composer, { target: { value: "First" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    await waitFor(() => expect(mockedSendChat).toHaveBeenCalledOnce());
    expect(onConversationStart).toHaveBeenCalledOnce();

    fireEvent.change(composer, { target: { value: "Second" } });
    fireEvent.keyDown(composer, { key: "Enter" });
    await waitFor(() => expect(mockedSendChat).toHaveBeenCalledTimes(2));
    expect(onConversationStart).toHaveBeenCalledOnce();
  });
});
