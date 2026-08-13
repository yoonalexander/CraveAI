import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  ChatQuotaError,
  ChatRecommendation,
  ChatTimeoutError,
  fetchChatStatus,
  LocationHint,
  sendChat,
  UsageMetadata,
} from "../api/chat";
import type { Suggestion } from "../api/places";
import { ArrowUpIcon, CopyIcon, MicIcon, ShareIcon } from "./Icons";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  recommendations?: ChatRecommendation[];
};

type ChatPanelProps = {
  location?: LocationHint | null;
  onRecommendations?: (recommendations: ChatRecommendation[]) => void;
  candidatePlaces?: Suggestion[];
  onConversationStart?: () => void;
};

const DEFAULT_DAILY_CHAT_LIMIT = 3;
const CHAT_USAGE_STORAGE_KEY = "craveai-chat-usage";

const createMessageId = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export function ChatPanel({
  location,
  onRecommendations,
  candidatePlaces = [],
  onConversationStart,
}: ChatPanelProps): JSX.Element {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageMetadata | null>(() => readCachedUsage());
  const conversationRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const noticeTimer = useRef<number | null>(null);

  const hasConversation = messages.length > 0;

  useEffect(() => {
    let mounted = true;
    fetchChatStatus()
      .then((status) => {
        if (!mounted || !status.usage) return;
        setUsage(status.usage);
        writeCachedUsage(status.usage);
      })
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const conversation = conversationRef.current;
    if (!conversation || !hasConversation) return;
    if (typeof conversation.scrollTo === "function") {
      conversation.scrollTo({ top: conversation.scrollHeight, behavior: "smooth" });
    } else {
      conversation.scrollTop = conversation.scrollHeight;
    }
  }, [hasConversation, isLoading, messages]);

  useEffect(() => {
    return () => {
      if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    };
  }, []);

  const showNotice = (message: string) => {
    setNotice(message);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 2600);
  };

  const resizeTextarea = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 132)}px`;
  };

  const submit = async () => {
    if (isLoading) return;
    const trimmed = draft.trim();
    if (!trimmed) return;

    if (!hasConversation) onConversationStart?.();

    const userMessage: Message = {
      id: createMessageId("user"),
      role: "user",
      content: trimmed,
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError(null);
    setIsLoading(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    try {
      const response = await sendChat(trimmed, {
        location: location ?? undefined,
        candidatePlaces,
      });
      const nextUsage = response.usage ?? estimateNextUsage(usage);
      setUsage(nextUsage);
      writeCachedUsage(nextUsage);

      const recommendations = response.recommendations.length
        ? response.recommendations
        : undefined;
      onRecommendations?.(recommendations ?? []);

      const assistantMessages: Message[] = response.messages.length
        ? response.messages.map((message, index) => ({
            id: createMessageId(`assistant-${index}`),
            role: "assistant",
            content: message.content,
            recommendations: index === 0 ? recommendations : undefined,
          }))
        : [
            {
              id: createMessageId("assistant"),
              role: "assistant",
              content: response.reply || "I've gathered a few nearby ideas for you.",
              recommendations,
            },
          ];
      setMessages((current) => [...current, ...assistantMessages]);
    } catch (reason) {
      let assistantMessage = "Sorry, I ran into a problem finding recommendations. Please try again.";
      if (reason instanceof ChatQuotaError) {
        assistantMessage = reason.message;
        if (reason.usage) {
          setUsage(reason.usage);
          writeCachedUsage(reason.usage);
        }
      } else if (reason instanceof ChatTimeoutError) {
        assistantMessage = reason.message;
      }
      setError(assistantMessage);
      onRecommendations?.([]);
      setMessages((current) => [
        ...current,
        {
          id: createMessageId("assistant-error"),
          role: "assistant",
          content: assistantMessage,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const remaining = usage?.unlimited
    ? "Unlimited messages"
    : `${usage?.remaining ?? DEFAULT_DAILY_CHAT_LIMIT} message${(usage?.remaining ?? DEFAULT_DAILY_CHAT_LIMIT) === 1 ? "" : "s"} left today`;

  return (
    <section
      className={`chat-panel${hasConversation ? " has-conversation" : " is-idle"}`}
      aria-label="CraveAI chat"
    >
      <div className="chat-active-toolbar" aria-hidden={!hasConversation}>
        <button onClick={() => showNotice("Conversation sharing is coming soon.")} type="button">
          <ShareIcon /> Share
        </button>
      </div>

      <div className="chat-idle-heading">
        <h1>What’s your craving today?</h1>
      </div>

      <div className="chat-conversation" ref={conversationRef}>
        <div className="chat-thread">
          {messages.map((message) => (
            <article className={`chat-message is-${message.role}`} key={message.id}>
              <div className="chat-message-content">
                <p>{message.content}</p>
                {message.recommendations?.length ? (
                  <div className="chat-recommendations">
                    {message.recommendations.map((recommendation, index) => (
                      <div key={`${message.id}-${recommendation.place_id || recommendation.name}-${index}`}>
                        <strong>{recommendation.name}</strong>
                        <span>
                          {typeof recommendation.rating === "number" ? `★ ${recommendation.rating.toFixed(1)}` : ""}
                          {recommendation.address ? `${typeof recommendation.rating === "number" ? " · " : ""}${recommendation.address}` : ""}
                        </span>
                        {recommendation.confidence ? (
                          <div className={`recommendation-confidence is-${recommendation.confidence}`}>
                            {recommendation.confidence === "high" ? "Strong match" : "Relevant match"}
                            {typeof recommendation.match_score === "number"
                              ? ` · ${Math.round(recommendation.match_score * 100)}%`
                              : ""}
                          </div>
                        ) : null}
                        {recommendation.matched_preferences?.length ? (
                          <div className="recommendation-preferences" aria-label="Matched preferences">
                            {recommendation.matched_preferences.map((preference) => (
                              <span key={preference}>{preference}</span>
                            ))}
                          </div>
                        ) : null}
                        {recommendation.matching_dishes?.length ? (
                          <ul className="recommendation-dishes">
                            {recommendation.matching_dishes.map((dish) => <li key={dish}>{dish}</li>)}
                          </ul>
                        ) : null}
                        {recommendation.reason ? <p>{recommendation.reason}</p> : null}
                        {recommendation.evidence?.some((item) => item.source_url) ? (
                          <div className="recommendation-sources">
                            {recommendation.evidence
                              .filter((item) => item.source_url)
                              .slice(0, 2)
                              .map((item, sourceIndex) => (
                                <a
                                  href={item.source_url || undefined}
                                  key={`${item.type}-${item.label}-${sourceIndex}`}
                                  rel="noreferrer"
                                  target="_blank"
                                >
                                  View source
                                </a>
                              ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              {message.role === "assistant" ? (
                <button
                  aria-label="Copy response"
                  className="chat-message-action"
                  onClick={() => {
                    void navigator.clipboard?.writeText(message.content);
                    showNotice("Response copied.");
                  }}
                  type="button"
                >
                  <CopyIcon />
                </button>
              ) : null}
            </article>
          ))}
          {isLoading ? (
            <div className="chat-thinking" aria-label="CraveAI is thinking">
              <span /><span /><span />
            </div>
          ) : null}
        </div>
      </div>

      <form className="chat-composer" onSubmit={handleSubmit}>
        <div className="chat-composer-field">
          <textarea
            aria-label="Ask CraveAI"
            disabled={isLoading}
            onChange={(event) => {
              setDraft(event.target.value);
              resizeTextarea();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything"
            ref={textareaRef}
            rows={1}
            value={draft}
          />
          <button
            aria-label="Voice input coming soon"
            className="composer-mic"
            onClick={() => showNotice("Voice input is coming soon.")}
            title="Voice input coming soon"
            type="button"
          >
            <MicIcon />
          </button>
          <button
            aria-label="Send message"
            className="composer-send"
            disabled={isLoading || !draft.trim()}
            type="submit"
          >
            <span>Send</span><ArrowUpIcon />
          </button>
        </div>
        <div className="chat-composer-meta">
          <span>{remaining}</span>
          {error ? <span className="chat-error" role="alert">{error}</span> : null}
        </div>
      </form>

      <p className="chat-disclaimer">CraveAI can make mistakes. Check important details.</p>
      {notice ? <div className="chat-notice" role="status">{notice}</div> : null}
    </section>
  );
}

function estimateNextUsage(currentUsage: UsageMetadata | null): UsageMetadata {
  const limit = currentUsage?.limit ?? DEFAULT_DAILY_CHAT_LIMIT;
  const used = Math.min(limit, (currentUsage?.used ?? 0) + 1);
  return {
    limit,
    used,
    remaining: Math.max(limit - used, 0),
    reset_at: currentUsage?.reset_at ?? nextUtcResetAt(),
  };
}

function nextUtcResetAt(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)).toISOString();
}

function readCachedUsage(): UsageMetadata | null {
  if (!canUseLocalStorage()) return null;
  const raw = window.localStorage.getItem(CHAT_USAGE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const usage = JSON.parse(raw) as UsageMetadata;
    if (!isUsageMetadata(usage) || new Date(usage.reset_at).getTime() <= Date.now()) {
      window.localStorage.removeItem(CHAT_USAGE_STORAGE_KEY);
      return null;
    }
    return usage;
  } catch {
    window.localStorage.removeItem(CHAT_USAGE_STORAGE_KEY);
    return null;
  }
}

function writeCachedUsage(usage: UsageMetadata | null): void {
  if (!canUseLocalStorage()) return;
  if (!usage || usage.unlimited) {
    window.localStorage.removeItem(CHAT_USAGE_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(CHAT_USAGE_STORAGE_KEY, JSON.stringify(usage));
}

function isUsageMetadata(usage: Partial<UsageMetadata>): usage is UsageMetadata {
  return (
    typeof usage.limit === "number" &&
    typeof usage.used === "number" &&
    typeof usage.remaining === "number" &&
    typeof usage.reset_at === "string"
  );
}

function canUseLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && Boolean(window.localStorage);
  } catch {
    return false;
  }
}
