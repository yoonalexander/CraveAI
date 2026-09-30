import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SuggestionCard } from "./SuggestionCard";
import { fetchPlacePhoto } from "../api/photos";

vi.mock("../context/AuthContext", () => ({ useAuth: () => ({ user: null, loading: false }) }));
vi.mock("../api/photos", () => ({ fetchPlacePhoto: vi.fn(), PhotoLimitError: class extends Error {} }));
beforeEach(() => vi.mocked(fetchPlacePhoto).mockResolvedValue({ place_id: "place-1", index: 0, total: 0, photo: null }));
describe("SuggestionCard", () => {
  it("shows a branded photo fallback and preserves signed-out save behavior", async () => {
    render(<SuggestionCard description="10 Main Street" distance="1.2 km" placeId="place-1" rating={4.6} tags={["Thai"]} title="Green Basil" />);
    expect(await screen.findByRole("img", { name: "No photo available for Green Basil" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to save" })).toHaveAttribute("href", "/login");
    expect(screen.getByLabelText("4.6 out of 5 stars")).toBeInTheDocument();
  });
  it("loads photos without a map SDK and credits every contributor", async () => {
    vi.mocked(fetchPlacePhoto).mockResolvedValue({ place_id: "place-1", index: 0, total: 2, photo: {
      uri: "https://lh3.googleusercontent.com/photo", source_uri: "https://maps.google.com/photo", report_uri: null,
      authors: [{ name: "Photo Owner", uri: "https://maps.google.com/owner", avatar_uri: null }, { name: "Coauthor", uri: null, avatar_uri: null }],
    } });
    render(<SuggestionCard description="10 Main Street" placeId="place-1" title="Photo Cafe" />);
    expect(await screen.findByRole("img", { name: "Google Maps photo of Photo Cafe" })).toHaveAttribute("src", "https://lh3.googleusercontent.com/photo");
    expect(screen.getByRole("link", { name: "Photo: Photo Owner" })).toHaveAttribute("href", "https://maps.google.com/owner");
    expect(screen.getByText("Photo: Coauthor")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Google Maps" })).toHaveAttribute("href", "https://maps.google.com/photo");
  });
  it("illustrates a supported cuisine label and keeps unfamiliar cuisines readable with a neutral icon", () => {
    const { container, rerender } = render(<SuggestionCard placeId="place-1" title="Sushi Spot" description="Test Street" tags={["Restaurant"]} cuisineLabels={[{ value: "Japanese", source: "google", evidence: [] }]} />);
    expect(container.querySelector(".restaurant-food-tag")).toHaveTextContent("Japanese");
    expect(container.querySelector(".restaurant-food-tag svg")).toHaveAttribute("data-food-icon", "sushi");
    expect(screen.getByText("Label sources")).toBeInTheDocument();
    rerender(<SuggestionCard placeId="place-1" title="New Spot" description="Test Street" tags={["Ethiopian"]} />);
    expect(container.querySelector(".restaurant-food-tag")).toHaveTextContent("Ethiopian");
    expect(container.querySelector(".restaurant-food-tag svg")).toHaveAttribute("data-food-icon", "plate");
  });
});
