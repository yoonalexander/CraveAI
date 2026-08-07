type BrandLogoProps = {
  className?: string;
};

export function BrandLogo({ className = "" }: BrandLogoProps): JSX.Element {
  return (
    <img
      src="/AY%20Logo.svg"
      alt="AY"
      className={`block object-contain dark:invert ${className}`}
    />
  );
}
