import { FormEvent, useState } from "react";
import { sendChat, ChatRecommendation, LocationHint } from "../api/chat";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  recommendations?: ChatRecommendation[];
};

const createMessageId = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

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

  return (
    <div className="flex h-full flex-col rounded-3xl border border-slate-800 bg-slate-900/60 shadow-lg">
      <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-white">CraveAI Concierge</h2>
          <p className="text-sm text-slate-400">
            Describe your mood, craving, or dietary needs.
          </p>
          <p className="mt-1 text-xs text-slate-500">{resolvedLocationStatus}</p>
        </div>
        <span className="rounded-full bg-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-300">
          Prototype
        </span>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                message.role === "user"
                  ? "bg-primary text-white"
                  : "bg-slate-800 text-slate-100"
              }`}
            >
              {message.content}
              {!!message.recommendations?.length && (
                <div className="mt-3 space-y-2">
                  {message.recommendations.map(
                    (recommendation: ChatRecommendation, index: number) => (
                      <div
                        key={`${message.id}-rec-${index}`}
                        className="rounded-2xl border border-slate-700/60 bg-slate-900/40 px-4 py-3 text-xs text-slate-200"
                      >
                        <p className="text-sm font-semibold text-white">
                          {recommendation.name}
                        </p>
                        {typeof recommendation.rating === "number" && (
                          <p className="mt-1 text-slate-300">
                            Rating: {recommendation.rating.toFixed(1)}
                          </p>
                        )}
                        {recommendation.reason && (
                          <p className="mt-2 text-slate-300">
                            {recommendation.reason}
                          </p>
                        )}
                        {recommendation.address && (
                          <p className="mt-2 text-slate-500">
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
            <div className="max-w-[80%] rounded-2xl bg-slate-800 px-4 py-3 text-sm leading-relaxed text-slate-100">
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

      <form onSubmit={handleSubmit} className="border-t border-slate-800 p-4">
        <div className="flex items-center gap-3 rounded-full bg-slate-800 px-4">
          <input
            className="flex-1 bg-transparent py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none"
            placeholder='Try "Cozy soup spots under $20 near Yonge & Bloor."'
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={isLoading}
          />
          <button
            type="submit"
            className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-primary-dark disabled:opacity-70"
            disabled={isLoading}
          >
            {isLoading ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
