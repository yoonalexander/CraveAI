import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RestaurantPhotos } from "./RestaurantPhotos";
import { fetchPlacePhoto, PhotoLimitError, type PlacePhoto } from "../api/photos";
vi.mock("../api/photos", () => ({ fetchPlacePhoto: vi.fn(), PhotoLimitError: class extends Error {} }));
function photo(id: string, index = 0): PlacePhoto {
  return { place_id: id, index, total: 3, photo: { uri: `https://lh3.googleusercontent.com/${id}-${index}`,
    source_uri: `https://maps.google.com/${id}-${index}`, report_uri: null,
    authors: [{ name: `Author ${index}`, uri: "https://maps.google.com/author", avatar_uri: null }],
  } };
}
beforeEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(fetchPlacePhoto).mockReset().mockImplementation(async (id, index) => photo(id, index));
});
describe("RestaurantPhotos", () => {
  it("waits until near the viewport before making a provider request", async () => {
    let intersect: IntersectionObserverCallback = () => undefined;
    const disconnect = vi.fn();
    vi.stubGlobal("IntersectionObserver", class {
      constructor(callback: IntersectionObserverCallback) { intersect = callback; }
      observe = vi.fn(); disconnect = disconnect;
    });
    render(<RestaurantPhotos placeId="cafe" title="Cafe" />);
    expect(fetchPlacePhoto).not.toHaveBeenCalled();
    await act(async () => intersect([{ isIntersecting: true }] as IntersectionObserverEntry[], {} as IntersectionObserver));
    expect(await screen.findByAltText("Google Maps photo of Cafe")).toHaveAttribute("loading", "lazy");
    expect(fetchPlacePhoto).toHaveBeenCalledTimes(1);
    expect(disconnect).toHaveBeenCalled();
  });
  it("browses one photo at a time in an accessible gallery and restores focus", async () => {
    render(<RestaurantPhotos placeId="cafe" title="Cafe" compact />);
    const open = await screen.findByRole("button", { name: "View photos of Cafe" });
    expect(screen.queryByText("Photo: Author 0")).not.toBeInTheDocument();
    open.focus(); fireEvent.click(open);
    const gallery = screen.getByRole("dialog", { name: "Photos of Cafe" });
    expect(within(gallery).getByRole("link", { name: "Photo: Author 0" })).toBeInTheDocument();
    expect(within(gallery).getByRole("button", { name: "Close photos" })).toHaveFocus();
    expect(within(gallery).getByRole("button", { name: "Previous photo" })).toBeDisabled();
    fireEvent.click(within(gallery).getByRole("button", { name: "Next photo" }));
    expect(await within(gallery).findByText("2 / 3")).toBeInTheDocument();
    expect(within(gallery).getByAltText("Google Maps photo of Cafe")).toHaveAttribute("src", photo("cafe", 1).photo!.uri);
    expect(within(gallery).getByRole("link", { name: "Photo: Author 1" })).toBeInTheDocument();
    expect(fetchPlacePhoto).toHaveBeenCalledTimes(2);
    fireEvent.click(within(gallery).getByRole("button", { name: "Previous photo" }));
    await within(gallery).findByText("1 / 3");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(open).toHaveFocus();
  });
  it("never shows a previous venue's photo while changing venue or completing stale requests", async () => {
    let complete: (data: PlacePhoto) => void = () => undefined;
    vi.mocked(fetchPlacePhoto).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    const { rerender } = render(<RestaurantPhotos placeId="old" title="Old" />);
    const oldSignal = vi.mocked(fetchPlacePhoto).mock.calls[0][2];
    rerender(<RestaurantPhotos placeId="new" title="New" />);
    expect(oldSignal.aborted).toBe(true);
    expect(await screen.findByAltText("Google Maps photo of New")).toHaveAttribute("src", photo("new").photo!.uri);
    await act(async () => complete(photo("old")));
    expect(screen.queryByAltText("Google Maps photo of Old")).not.toBeInTheDocument();
    rerender(<RestaurantPhotos title="Unidentified" />);
    expect(screen.queryByAltText("Google Maps photo of New")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "No photo available for Unidentified" })).toBeInTheDocument();
    expect(fetchPlacePhoto).toHaveBeenCalledTimes(2);
  });
  it("handles broken images, retry, empty venues, and quota failures without retry loops", async () => {
    const { rerender } = render(<RestaurantPhotos placeId="broken" title="Broken" />);
    fireEvent.error(await screen.findByAltText("Google Maps photo of Broken"));
    expect(screen.getByText("This photo could not be loaded.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry photos" }));
    await screen.findByAltText("Google Maps photo of Broken");
    vi.mocked(fetchPlacePhoto).mockResolvedValueOnce({ place_id: "empty", index: 0, total: 0, photo: null });
    rerender(<RestaurantPhotos placeId="empty" title="Empty" />);
    await screen.findByText("No photos available yet");
    vi.mocked(fetchPlacePhoto).mockRejectedValueOnce(new PhotoLimitError("Photos are temporarily paused. Try again later."));
    rerender(<RestaurantPhotos placeId="limited" title="Limited" />);
    await screen.findByText("Photos are temporarily paused. Try again later.");
    expect(screen.queryByRole("button", { name: "Retry photos" })).not.toBeInTheDocument();
    expect(fetchPlacePhoto).toHaveBeenCalledTimes(4);
  });
});
