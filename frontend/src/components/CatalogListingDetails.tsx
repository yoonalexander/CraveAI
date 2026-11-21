import type { Suggestion } from "../api/places";

export function CatalogListingDetails({ place }: { place: Suggestion }): JSX.Element | null {
  const website = /^https?:\/\//i.test(place.website || "") ? place.website : null;
  if (!website && !place.hours && !place.phone) return null;
  return <div className="catalog-listing-details">
    {place.hours ? <p>{place.hours}</p> : null}
    {place.phone ? <a href={`tel:${place.phone.replace(/[^+\d]/g, "")}`}>{place.phone}</a> : null}
    {website ? <a href={website} target="_blank" rel="noreferrer">Restaurant website</a> : null}
  </div>;
}
