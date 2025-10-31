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
    <article className="flex flex-col gap-3 rounded-3xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-100 shadow-md backdrop-blur">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">{title}</h3>
        {rating && (
          <span className="rounded-full bg-amber-500/20 px-2 py-1 text-xs font-medium text-amber-300">
            ★ {rating.toFixed(1)}
          </span>
        )}
      </div>
      <p className="text-slate-400">{description}</p>
      <div className="flex flex-wrap gap-2 text-xs text-slate-400">
        {tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-slate-700 px-3 py-1"
          >
            {tag}
          </span>
        ))}
        {distance && (
          <span className="rounded-full border border-slate-700 px-3 py-1">
            {distance}
          </span>
        )}
      </div>
    </article>
  );
}
