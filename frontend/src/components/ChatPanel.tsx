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
  streamChat,
  UsageMetadata,
} from "../api/chat";
import type { Suggestion } from "../api/places";
import { saveConversationMessages, submitFeedback, transcribeAudio } from "../api/product";
import { useAuth } from "../context/AuthContext";
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
const CHAT_USAGE_STORAGE_KEY = "craveai-chat-usage-v1";
const TEMP_CHAT_STORAGE_KEY = "craveai-temporary-chat";

const createMessageId = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export function ChatPanel({
  location,
  onRecommendations,
  candidatePlaces = [],
  onConversationStart,
}: ChatPanelProps): JSX.Element {
  const { user } = useAuth();
  const recovered = readTemporaryChat();
  const [messages, setMessages] = useState<Message[]>(recovered.messages);
  const [draft, setDraft] = useState(recovered.draft);
  const [isLoading, setIsLoading] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(recovered.conversationId);
  const [ageGateOpen, setAgeGateOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [submittedFeedback, setSubmittedFeedback] = useState<Set<string>>(new Set());
  const [feedbackDraft, setFeedbackDraft] = useState<{
    recommendation: ChatRecommendation; liked: boolean; notes: string; reportReason: string;
  } | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [usage, setUsage] = useState<UsageMetadata | null>(() => readCachedUsage());
  const conversationRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const noticeTimer = useRef<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingStartedRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  const currentRecommendationList = useRef<ChatRecommendation[]>([]);

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
      if (recordingTimerRef.current) window.clearTimeout(recordingTimerRef.current);
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    };
  }, []);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        TEMP_CHAT_STORAGE_KEY,
        JSON.stringify({ messages, draft, conversationId }),
      );
    } catch {
      // Session recovery is best-effort and never blocks chat.
    }
  }, [conversationId, draft, messages]);

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
    if (!user && window.sessionStorage.getItem("craveai-age-18") !== "true") {
      setAgeGateOpen(true);
      return;
    }

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
      const response = await streamChat(trimmed, {
        location: location ?? undefined,
        candidatePlaces,
        conversationId: conversationId || undefined,
        contextMessages: messages.slice(-12).map((message) => ({
          role: message.role,
          content: message.content,
          place_ids: message.recommendations?.flatMap((item) => item.place_id ? [item.place_id] : []) || [],
        })),
        ageConfirmed: Boolean(user) || window.sessionStorage.getItem("craveai-age-18") === "true",
        authenticated: Boolean(user),
      }, {
        onStage: setStage,
        onRecommendation: (recommendation) => {
          onRecommendations?.((currentRecommendationList.current = [...currentRecommendationList.current, recommendation]));
        },
      });
      if (response.conversation_id) setConversationId(response.conversation_id);
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
      setStage(null);
      currentRecommendationList.current = [];
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

  const toggleRecording = async () => {
    if (isRecording) {
      recorderRef.current?.stop();
      return;
    }
    if (!user && window.sessionStorage.getItem("craveai-age-18") !== "true") {
      setAgeGateOpen(true);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, preferred ? { mimeType: preferred } : undefined);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size) audioChunksRef.current.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        setIsRecording(false);
        if (recordingTimerRef.current) window.clearTimeout(recordingTimerRef.current);
        const duration = Math.min(60, Math.max(1, (Date.now() - recordingStartedRef.current) / 1000));
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = [];
        if (blob.size > 10 * 1024 * 1024) { setError("That recording is larger than 10 MB."); return; }
        setIsTranscribing(true);
        void transcribeAudio(blob, duration, Boolean(user))
          .then((text) => { setDraft(text); window.requestAnimationFrame(resizeTextarea); })
          .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to transcribe audio."))
          .finally(() => setIsTranscribing(false));
      };
      recorderRef.current = recorder;
      recordingStartedRef.current = Date.now();
      recorder.start(250);
      setIsRecording(true);
      recordingTimerRef.current = window.setTimeout(() => recorder.stop(), 60_000);
    } catch (reason) {
      setError(reason instanceof DOMException && reason.name === "NotAllowedError" ? "Microphone permission was denied." : "Unable to start the microphone.");
    }
  };

  const portableMessages = () => messages.map((message) => ({
    role: message.role,
    content: message.content,
    place_ids: message.recommendations?.flatMap((item) => item.place_id ? [item.place_id] : []) || [],
  }));
  const formattedConversation = () => portableMessages().map((message) => `${message.role === "user" ? "You" : "CraveAI"}: ${message.content}`).join("\n\n");
  const downloadConversation = (format: "markdown" | "json") => {
    const body = format === "json" ? JSON.stringify({ exported_at: new Date().toISOString(), messages: portableMessages() }, null, 2) : `# CraveAI conversation\n\n${formattedConversation()}`;
    const url = URL.createObjectURL(new Blob([body], { type: format === "json" ? "application/json" : "text/markdown" }));
    const link = document.createElement("a"); link.href = url; link.download = `craveai-conversation.${format === "json" ? "json" : "md"}`; link.click(); URL.revokeObjectURL(url);
    setShareOpen(false);
  };

  const saveConversation = async () => {
    if (!user) { window.location.assign("/login"); return; }
    try {
      const id = await saveConversationMessages(portableMessages());
      setConversationId(id); showNotice("Conversation saved to History.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save conversation."); }
  };

  const sendFeedback = async (recommendation: ChatRecommendation, liked: boolean, notes?: string, reportReason?: string) => {
    const token = recommendation.recommendation_token;
    if (!user) { window.location.assign("/login"); return; }
    if (!token || submittedFeedback.has(token)) return;
    try {
      await submitFeedback(token, liked, notes || undefined, reportReason || undefined);
      setSubmittedFeedback((current) => new Set(current).add(token));
      setFeedbackDraft(null);
      showNotice("Thanks for the feedback.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to send feedback."); }
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
        {user && !conversationId ? <button onClick={() => void saveConversation()} type="button">Save conversation</button> : null}
        <button aria-expanded={shareOpen} onClick={() => setShareOpen((open) => !open)} type="button">
          <ShareIcon /> Share
        </button>
        {shareOpen ? <div className="chat-share-menu"><button onClick={() => { void navigator.clipboard?.writeText(formattedConversation()); setShareOpen(false); showNotice("Conversation copied."); }}>Copy text</button><button onClick={() => downloadConversation("markdown")}>Download Markdown</button><button onClick={() => downloadConversation("json")}>Download JSON</button></div> : null}
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
                        {recommendation.place_id ? <a className="recommendation-google-source" href={`https://www.google.com/maps/search/?api=1&query_place_id=${encodeURIComponent(recommendation.place_id)}`} rel="noreferrer" target="_blank">Google Maps</a> : null}
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
                        {recommendation.recommendation_token ? <div className="recommendation-feedback" aria-label="Recommendation feedback"><button aria-label={`Mark ${recommendation.name} helpful`} disabled={submittedFeedback.has(recommendation.recommendation_token)} onClick={() => user ? setFeedbackDraft({ recommendation, liked: true, notes: "", reportReason: "" }) : window.location.assign("/login")} title="Helpful">👍</button><button aria-label={`Mark ${recommendation.name} not helpful`} disabled={submittedFeedback.has(recommendation.recommendation_token)} onClick={() => user ? setFeedbackDraft({ recommendation, liked: false, notes: "", reportReason: "" }) : window.location.assign("/login")} title="Not helpful">👎</button>{submittedFeedback.has(recommendation.recommendation_token) ? <span>Feedback submitted</span> : null}</div> : null}
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
              {stage ? <strong>{stage}</strong> : null}
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
            aria-label={isRecording ? "Stop recording" : "Record voice input"}
            className={`composer-mic${isRecording ? " is-recording" : ""}`}
            disabled={isTranscribing}
            onClick={() => void toggleRecording()}
            title={isRecording ? "Stop recording" : "Record up to 60 seconds"}
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

      {hasConversation ? (
        <p className="chat-disclaimer">CraveAI can make mistakes. Check important details.</p>
      ) : (
        <p className="chat-legal-notice">
          CraveAI uses AI. Don’t share sensitive information. Prompts and bounded context go to OpenAI; confirmed location and search data go to map, Places, and weather providers. History is off by default; chats are saved only if you enable History or explicitly save one. Review our <a href="/terms">Terms</a>, <a href="/privacy">Privacy Policy</a>, and <a href="/help/data-use">learn more</a>.
        </p>
      )}
      {notice ? <div className="chat-notice" role="status">{notice}</div> : null}
      {isTranscribing ? <div className="chat-notice" role="status">Transcribing audio…</div> : null}
      {feedbackDraft ? <div className="feedback-dialog-backdrop"><form aria-labelledby="feedback-title" aria-modal="true" className="feedback-dialog" onKeyDown={(event) => trapDialogKeys(event, () => setFeedbackDraft(null))} onSubmit={(event) => { event.preventDefault(); void sendFeedback(feedbackDraft.recommendation, feedbackDraft.liked, feedbackDraft.notes, feedbackDraft.reportReason); }} role="dialog"><p>Recommendation feedback</p><h2 id="feedback-title">{feedbackDraft.liked ? "What worked well?" : "What should we improve?"}</h2><span>Your feedback is used for aggregate quality measurement, not automatic personalization.</span>{!feedbackDraft.liked ? <label>Issue<select onChange={(event) => setFeedbackDraft({ ...feedbackDraft, reportReason: event.target.value })} value={feedbackDraft.reportReason}><option value="">General mismatch</option><option value="incorrect_information">Incorrect restaurant information</option><option value="outside_search_area">Outside the search area</option><option value="closed_or_unavailable">Closed or unavailable</option><option value="other">Other</option></select></label> : null}<label>Optional note<textarea autoFocus maxLength={1000} onChange={(event) => setFeedbackDraft({ ...feedbackDraft, notes: event.target.value })} placeholder="Tell us what was useful or incorrect" value={feedbackDraft.notes} /></label><div><button onClick={() => setFeedbackDraft(null)} type="button">Cancel</button><button className="primary-action" type="submit">Submit feedback</button></div></form></div> : null}
      {ageGateOpen ? <div className="age-gate-backdrop"><section aria-modal="true" className="age-gate" role="dialog"><img alt="" src="/craveai-pin.svg" /><p>Before you use AI chat or voice</p><h2>Confirm you are 18 or older</h2><span>CraveAI sends prompts and bounded context to OpenAI, location and search data to map/Places/weather providers, and voice clips to OpenAI for transcription. Don’t share sensitive information.</span><button onClick={() => { window.sessionStorage.setItem("craveai-age-18", "true"); setAgeGateOpen(false); void submit(); }}>I am 18 or older</button><button className="secondary" onClick={() => setAgeGateOpen(false)}>Cancel</button><small>By continuing, you agree to the <a href="/terms">Terms</a> and acknowledge the <a href="/privacy">Privacy Policy</a>.</small></section></div> : null}
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

function readTemporaryChat(): {
  messages: Message[];
  draft: string;
  conversationId: string | null;
} {
  try {
    const raw = window.sessionStorage.getItem(TEMP_CHAT_STORAGE_KEY);
    if (!raw) return { messages: [], draft: "", conversationId: null };
    const value = JSON.parse(raw) as { messages?: Message[]; draft?: string; conversationId?: string | null };
    return {
      messages: Array.isArray(value.messages) ? value.messages.slice(-24) : [],
      draft: typeof value.draft === "string" ? value.draft.slice(0, 2000) : "",
      conversationId: typeof value.conversationId === "string" ? value.conversationId : null,
    };
  } catch {
    return { messages: [], draft: "", conversationId: null };
  }
}

function trapDialogKeys(event: KeyboardEvent<HTMLFormElement>, close: () => void): void {
  if (event.key === "Escape") { event.preventDefault(); close(); return; }
  if (event.key !== "Tab") return;
  const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button, input, select, textarea, [href], [tabindex]:not([tabindex='-1'])")).filter((item) => !item.hasAttribute("disabled"));
  if (!items.length) return;
  const first = items[0]; const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
