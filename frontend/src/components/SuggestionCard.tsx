type SuggestionCardProps = {
  title: string;
  description: string;
  tags?: string[];
  distance?: string;
  rating?: number;
};

export function SuggestionCard({
  title,
  description,
  tags = [],
  distance,
  rating,
}: SuggestionCardProps): JSX.Element {
  return (
    <article className="flex flex-col gap-3 rounded-3xl border border-border bg-secondary/40 p-5 text-sm text-foreground shadow-md backdrop-blur">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        {rating && (
          <span className="rounded-full bg-highlight/20 px-2 py-1 text-xs font-medium text-highlight-foreground">
            ★ {rating.toFixed(1)}
          </span>
        )}
      </div>
      <p className="text-muted-foreground">{description}</p>
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        {tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-border px-3 py-1"
          >
            {tag}
          </span>
        ))}
        {distance && (
          <span className="rounded-full border border-border px-3 py-1">
            {distance}
          </span>
        )}
      </div>
    </article>
  );
}
