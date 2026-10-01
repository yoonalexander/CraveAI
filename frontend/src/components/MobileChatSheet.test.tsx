import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MobileChatSheet } from "./MobileChatSheet";

describe("MobileChatSheet", () => {
  it("offers an accessible expand and collapse control", () => {
    const onExpandedChange = vi.fn();
    const { rerender } = render(
      <MobileChatSheet expanded={false} onExpandedChange={onExpandedChange}>
        <p>Chat content</p>
      </MobileChatSheet>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Expand chat" }));
    expect(onExpandedChange).toHaveBeenCalledWith(true);

    rerender(
      <MobileChatSheet expanded onExpandedChange={onExpandedChange}>
        <p>Chat content</p>
      </MobileChatSheet>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Collapse chat" }));
    expect(onExpandedChange).toHaveBeenLastCalledWith(false);
  });

  it("snaps upward or downward after a decisive pointer drag", () => {
    const onExpandedChange = vi.fn();
    const { container } = render(
      <MobileChatSheet expanded={false} onExpandedChange={onExpandedChange}>
        <p>Chat content</p>
      </MobileChatSheet>,
    );
    const handle = container.querySelector(".mobile-sheet-grabber") as HTMLElement;
    handle.setPointerCapture = vi.fn();
    handle.releasePointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { clientY: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientY: 390, pointerId: 1 });
    fireEvent.pointerUp(handle, { clientY: 390, pointerId: 1 });
    expect(onExpandedChange).toHaveBeenCalledWith(true);
  });

  it("uses the release position even without a preceding move event", () => {
    const onExpandedChange = vi.fn();
    const { container } = render(<MobileChatSheet expanded onExpandedChange={onExpandedChange}>Chat</MobileChatSheet>);
    const handle = container.querySelector(".mobile-sheet-grabber") as HTMLElement;
    handle.setPointerCapture = vi.fn();
    handle.releasePointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { clientY: 100, pointerId: 1 });
    fireEvent.pointerUp(handle, { clientY: 220, pointerId: 1 });
    expect(onExpandedChange).toHaveBeenCalledWith(false);
  });

  it.each(["pointerCancel", "lostPointerCapture"] as const)("resets a %s gesture without changing expansion", (event) => {
    const onExpandedChange = vi.fn();
    const { container } = render(<MobileChatSheet expanded={false} onExpandedChange={onExpandedChange}>Chat</MobileChatSheet>);
    const sheet = container.querySelector(".mobile-chat-sheet") as HTMLElement;
    const handle = container.querySelector(".mobile-sheet-grabber") as HTMLElement;
    handle.setPointerCapture = vi.fn();
    handle.releasePointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { clientY: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientY: 350, pointerId: 1 });
    expect(sheet).toHaveClass("is-dragging");
    fireEvent[event](handle, { pointerId: 1 });
    expect(sheet).not.toHaveClass("is-dragging");
    expect(sheet.style.getPropertyValue("--sheet-drag")).toBe("0px");
    fireEvent.pointerUp(handle, { clientY: 350, pointerId: 1 });
    expect(onExpandedChange).not.toHaveBeenCalled();
  });

  it("does not capture the expand button's pointer", () => {
    const { container } = render(<MobileChatSheet expanded={false} onExpandedChange={vi.fn()}>Chat</MobileChatSheet>);
    const handle = container.querySelector(".mobile-sheet-grabber") as HTMLElement;
    handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Expand chat" }), { pointerId: 1 });
    expect(handle.setPointerCapture).not.toHaveBeenCalled();
  });
});
