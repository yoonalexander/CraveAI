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
});
