import { FormEvent, useState } from "react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

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

export function ChatPanel(): JSX.Element {
  const [messages, setMessages] = useState<Message[]>(seededMessages);
  const [draft, setDraft] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed) {
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: trimmed,
      },
      {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content:
          "Nice! Once the backend is connected I'll fetch real recommendations.",
      },
    ]);

    setDraft("");
  };

  return (
    <div className="flex h-full flex-col rounded-3xl border border-slate-800 bg-slate-900/60 shadow-lg">
      <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-white">CraveAI Concierge</h2>
          <p className="text-sm text-slate-400">
            Describe your mood, craving, or dietary needs.
          </p>
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
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-800 p-4">
        <div className="flex items-center gap-3 rounded-full bg-slate-800 px-4">
          <input
            className="flex-1 bg-transparent py-3 text-sm text-white placeholder:text-slate-500 focus:outline-none"
            placeholder="Try “Cozy soup spots under $20 near Yonge & Bloor.”"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button
            type="submit"
            className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-primary-dark"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
