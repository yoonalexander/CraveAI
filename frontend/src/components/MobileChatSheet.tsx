import { PointerEvent, ReactNode, useEffect, useRef, useState } from "react";
import { ChevronDownIcon } from "./Icons";

type MobileChatSheetProps = {
  children: ReactNode;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
};

export function MobileChatSheet({
  children,
  expanded,
  onExpandedChange,
}: MobileChatSheetProps): JSX.Element {
  const [dragOffset, setDragOffset] = useState(0);
  const dragStart = useRef<number | null>(null);

  useEffect(() => setDragOffset(0), [expanded]);

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    dragStart.current = event.clientY;
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStart.current === null) return;
    setDragOffset(Math.max(-180, Math.min(180, event.clientY - dragStart.current)));
  };
  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStart.current === null) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    if (dragOffset < -48) onExpandedChange(true);
    if (dragOffset > 48) onExpandedChange(false);
    dragStart.current = null;
    setDragOffset(0);
  };

  return (
    <section
      className={`mobile-chat-sheet${expanded ? " is-expanded" : ""}`}
      style={{ "--sheet-drag": `${dragOffset}px` } as React.CSSProperties}
    >
      <div
        className="mobile-sheet-grabber"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <span aria-hidden="true" />
        <button
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse chat" : "Expand chat"}
          onClick={() => onExpandedChange(!expanded)}
          type="button"
        >
          <ChevronDownIcon />
        </button>
      </div>
      <div className="mobile-sheet-content">{children}</div>
    </section>
  );
}
