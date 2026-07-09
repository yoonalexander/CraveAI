import { FormEvent, useEffect, useState } from "react";
import {
  ChatQuotaError,
  fetchChatStatus,
  sendChat,
  ChatRecommendation,
  LocationHint,
  UsageMetadata,
} from "../api/chat";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  recommendations?: ChatRecommendation[];
};

const createMessageId = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const DEFAULT_DAILY_CHAT_LIMIT = 3;
const FALLBACK_CHAT_MESSAGE_COST = 1;
const CHAT_USAGE_STORAGE_KEY = "craveai-chat-usage";

const seededMessages: Message[] = [
  {
    id: "intro",
    role: "assistant",
    content: "What are you craving today? Tell me a mood, cuisine, or vibe.",
  },
  {
    id: "sample-user",
    role: "user",
    content: "I'm in the mood for something cozy and spicy near downtown.",
  },
  {
    id: "sample-assistant",
    role: "assistant",
    content:
      "Great choice! Soon I'll pull nearby ramen and pho spots that fit that vibe.",
  },
];

type ChatPanelProps = {
  location?: LocationHint | null;
  locationStatus?: string;
  onRecommendations?: (recommendations: ChatRecommendation[]) => void;
};

export function ChatPanel({
  location,
  locationStatus,
  onRecommendations,
}: ChatPanelProps): JSX.Element {
  const [messages, setMessages] = useState<Message[]>(seededMessages);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageMetadata | null>(() =>
    readCachedUsage(),
  );

  useEffect(() => {
    let isMounted = true;

    fetchChatStatus()
      .then((status) => {
        if (!isMounted || !status.usage?.unlimited) {
          return;
        }
        setUsage(status.usage);
        writeCachedUsage(status.usage);
      })
      .catch(() => {
        // Status is only used for the visual mode indicator.
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isLoading) {
      return;
    }

    const trimmed = draft.trim();
    if (!trimmed) {
      return;
    }

    const userMessage: Message = {
      id: createMessageId("user"),
      role: "user",
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    setDraft("");
    setError(null);
    setIsLoading(true);

    try {
      const response = await sendChat(trimmed, {
        location: location ?? undefined,
      });
      setUsage((currentUsage) => {
        const nextUsage = response.usage ?? estimateNextUsage(currentUsage);
        writeCachedUsage(nextUsage);
        return nextUsage;
      });
      const recommendations =
        response.recommendations.length > 0
          ? response.recommendations
          : undefined;
      if (onRecommendations) {
        onRecommendations(recommendations ?? []);
      }

      const assistantMessages: Message[] =
        response.messages.length > 0
          ? response.messages.map((message, index) => ({
            id: createMessageId("assistant"),
            role: "assistant",
            content: message.content,
            recommendations:
              index === 0 && recommendations ? recommendations : undefined,
          }))
          : [
            {
              id: createMessageId("assistant"),
              role: "assistant",
              content:
                response.reply ||
                "I've gathered a few ideas you might enjoy.",
              recommendations,
            },
          ];

      setMessages((prev) => [...prev, ...assistantMessages]);
    } catch (err) {
      if (err instanceof ChatQuotaError) {
        setUsage((currentUsage) => {
          const nextUsage = err.usage ?? currentUsage;
          writeCachedUsage(nextUsage);
          return nextUsage;
        });
        setError(err.message);
        onRecommendations?.([]);
        setMessages((prev) => [
          ...prev,
          {
            id: createMessageId("assistant"),
            role: "assistant",
            content: err.message,
          },
        ]);
        return;
      }

      const message =
        err instanceof Error
          ? err.message
          : "Unexpected issue while contacting the assistant.";
      setError(message);
      onRecommendations?.([]);
      setMessages((prev) => [
        ...prev,
        {
          id: createMessageId("assistant"),
          role: "assistant",
          content:
            "Sorry, I ran into a problem fetching recommendations. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const resolvedLocationStatus =
    locationStatus ||
    (location
      ? "Using your current location for nearby matches."
      : "Share your location in the browser to dial in the map.");
  const displayedLimit = usage?.limit ?? DEFAULT_DAILY_CHAT_LIMIT;
  const displayedUsed = usage?.used ?? 0;
  const displayedRemaining = usage?.remaining ?? displayedLimit;
  const isUnlimited = usage?.unlimited === true;
  const remainingPercent =
    displayedLimit > 0
      ? Math.min(100, Math.max(0, (displayedRemaining / displayedLimit) * 100))
      : 0;
  const resetTime = usage
    ? new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(new Date(usage.reset_at))
    : null;

  return (
    <div className="flex h-full flex-col rounded-3xl border border-border bg-secondary/60 shadow-lg backdrop-blur-sm">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">CraveAI Concierge</h2>
          <p className="text-sm text-muted-foreground">
            Describe your mood, craving, or dietary needs.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{resolvedLocationStatus}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className="rounded-full bg-primary/20 px-3 py-1 text-xs font-medium text-primary">
            Prototype
          </span>
          <div
            className="w-44 rounded-2xl border border-border bg-background/70 px-3 py-2 text-right shadow-sm"
            aria-label={
              isUnlimited
                ? "Developer mode: unlimited chats"
                : `Daily chat limit: ${displayedRemaining} messages left`
            }
          >
            <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-foreground">
              <span>Daily chats</span>
              <span>{isUnlimited ? "Unlimited" : `${displayedRemaining.toLocaleString()} ${displayedRemaining === 1 ? "message" : "messages"} left`}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${isUnlimited ? 100 : remainingPercent}%` }}
              />
            </div>
            <p className="mt-1 text-[10px] text-muted-foreground">
              {isUnlimited
                ? "Developer mode"
                : `${displayedUsed.toLocaleString()} / ${displayedLimit.toLocaleString()} sent${resetTime ? ` - resets ${resetTime}` : " - updates after chat"}`}
            </p>
          </div>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
              }`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${message.role === "user"
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-secondary-foreground"
                }`}
            >
              {message.content}
              {!!message.recommendations?.length && (
                <div className="mt-3 space-y-2">
                  {message.recommendations.map(
                    (recommendation: ChatRecommendation, index: number) => (
                      <div
                        key={`${message.id}-rec-${index}`}
                        className="rounded-2xl border border-border bg-background/40 px-4 py-3 text-xs text-foreground"
                      >
                        <p className="text-sm font-semibold text-foreground">
                          {recommendation.name}
                        </p>
                        {typeof recommendation.rating === "number" && (
                          <p className="mt-1 text-muted-foreground">
                            Rating: {recommendation.rating.toFixed(1)}
                          </p>
                        )}
                        {recommendation.reason && (
                          <p className="mt-2 text-muted-foreground">
                            {recommendation.reason}
                          </p>
                        )}
                        {recommendation.address && (
                          <p className="mt-2 text-muted-foreground">
                            {recommendation.address}
                          </p>
                        )}
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-2xl bg-secondary px-4 py-3 text-sm leading-relaxed text-secondary-foreground">
              Thinking...
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="mx-6 mb-3 rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-2 text-xs text-red-200">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="border-t border-border p-4">
        <div className="flex items-center gap-3 rounded-full border border-input bg-background px-4 shadow-sm focus-within:ring-1 focus-within:ring-ring">
          <input
            className="flex-1 bg-transparent py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            placeholder='Try "Cozy soup spots under $20 near Yonge & Bloor."'
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={isLoading}
          />
          <button
            type="submit"
            className="rounded-full bg-secondary px-4 py-2 text-sm font-semibold text-secondary-foreground transition hover:opacity-90 disabled:opacity-70 dark:bg-primary dark:text-primary-foreground"
            disabled={isLoading}
          >
            {isLoading ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

function estimateNextUsage(currentUsage: UsageMetadata | null): UsageMetadata {
  const limit = currentUsage?.limit ?? DEFAULT_DAILY_CHAT_LIMIT;
  const used = Math.min(
    limit,
    (currentUsage?.used ?? 0) + FALLBACK_CHAT_MESSAGE_COST,
  );

  return {
    limit,
    used,
    remaining: Math.max(limit - used, 0),
    reset_at: currentUsage?.reset_at ?? nextUtcResetAt(),
  };
}

function nextUtcResetAt(): string {
  const now = new Date();
  return new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + 1,
    ),
  ).toISOString();
}

function readCachedUsage(): UsageMetadata | null {
  if (!canUseLocalStorage()) {
    return null;
  }

  const rawUsage = window.localStorage.getItem(CHAT_USAGE_STORAGE_KEY);
  if (!rawUsage) {
    return null;
  }

  try {
    const usage = JSON.parse(rawUsage) as Partial<UsageMetadata>;
    if (!isUsageMetadata(usage) || !isActiveUsage(usage)) {
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
  if (!canUseLocalStorage()) {
    return;
  }

  if (!usage || usage.unlimited || !isActiveUsage(usage)) {
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
    typeof usage.reset_at === "string" &&
    (usage.unlimited === undefined || typeof usage.unlimited === "boolean")
  );
}

function isActiveUsage(usage: UsageMetadata): boolean {
  const resetTime = new Date(usage.reset_at).getTime();
  return Number.isFinite(resetTime) && resetTime > Date.now();
}

function canUseLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && Boolean(window.localStorage);
  } catch {
    return false;
  }
}
