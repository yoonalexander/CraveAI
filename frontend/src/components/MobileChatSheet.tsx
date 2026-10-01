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
  const dragStart = useRef<{ y: number; pointerId: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => setDragOffset(0), [expanded]);

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || dragStart.current) return;
    dragStart.current = { y: event.clientY, pointerId: event.pointerId };
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStart.current?.pointerId !== event.pointerId) return;
    setDragOffset(event.clientY - dragStart.current.y);
  };
  const endDrag = () => {
    dragStart.current = null;
    setIsDragging(false);
    setDragOffset(0);
  };
  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStart.current?.pointerId !== event.pointerId) return;
    const offset = event.clientY - dragStart.current.y;
    endDrag();
    event.currentTarget.releasePointerCapture(event.pointerId);
    if (offset < -48) onExpandedChange(true);
    if (offset > 48) onExpandedChange(false);
  };

  return (
    <section
      className={`mobile-chat-sheet${expanded ? " is-expanded" : ""}${isDragging ? " is-dragging" : ""}`}
      style={{ "--sheet-drag": `${dragOffset}px` } as React.CSSProperties}
    >
      <div
        className="mobile-sheet-grabber"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={endDrag}
        onLostPointerCapture={endDrag}
      >
        <span aria-hidden="true" />
        <button
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse chat" : "Expand chat"}
          onClick={() => onExpandedChange(!expanded)}
          onPointerDown={(event) => event.stopPropagation()}
          type="button"
        >
          <ChevronDownIcon />
        </button>
      </div>
      <div className="mobile-sheet-content">{children}</div>
    </section>
  );
}
