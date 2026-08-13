export type Coordinates = {
  lat: number;
  lng: number;
};

export type ViewportBounds = {
  north: number;
  south: number;
  east: number;
  west: number;
};

export type SearchArea = {
  center: Coordinates;
  bounds?: ViewportBounds;
  radius: number;
  label: string;
};
