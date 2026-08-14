import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";
import { fetchChatStatus, streamChat } from "../api/chat";

vi.mock("../api/chat", async () => {
  const actual = await vi.importActual<typeof import("../api/chat")>("../api/chat");
  return {
    ...actual,
    fetchChatStatus: vi.fn(),
    streamChat: vi.fn(),
  };
});

const mockedSendChat = vi.mocked(streamChat);
const mockedFetchChatStatus = vi.mocked(fetchChatStatus);

beforeEach(() => {
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
  it("shows the temporary development chat allowance", () => {
    render(<ChatPanel />);
    expect(screen.getByText("3000 messages left today")).toBeInTheDocument();
  });

  it("starts empty and moves into conversation mode after Enter", async () => {
    const { container } = render(<ChatPanel />);
    expect(screen.getByRole("heading", { name: "What’s your craving today?" })).toBeVisible();
    expect(screen.getByText(/your prompt and confirmed location may be sent to AI and search providers/i)).toBeInTheDocument();
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
