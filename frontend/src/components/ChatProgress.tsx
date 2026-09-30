/** Streamed public status only; decorative motion stays out of the live region. */
export function ChatProgress({ stage }: { stage: string | null }): JSX.Element {
  const message = stage?.trim() || "Getting your search ready…";
  return (
    <div className="chat-thinking">
      <span className="chat-thinking-dots" aria-hidden="true"><i /><i /><i /></span>
      <div className="chat-progress-copy">
        <p className="chat-progress-heading" aria-hidden="true">Finding your next good meal</p>
        <div className="chat-progress-status" role="status" aria-live="polite" aria-atomic="true">
          <span className="chat-progress-message" key={message} title={message}>{message}</span>
        </div>
      </div>
    </div>
  );
}
