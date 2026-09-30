import type { FilterLabel } from "../api/places";

export function FilterEvidence({ labels = [] }: { labels?: FilterLabel[] }): JSX.Element | null {
  if (!labels.length) return null;
  return <details className="filter-evidence">
    <summary>Label sources</summary>
    <ul>{labels.map((label) => <li key={`${label.source}:${label.value}`}>
      <strong>{label.value}</strong> · {label.source === "google" ? "Google data" : "Menu inference"}
      {label.evidence.map((item) => <a key={item.id} href={item.source_url} rel="noreferrer" target="_blank">{item.label}</a>)}
    </li>)}</ul>
  </details>;
}
