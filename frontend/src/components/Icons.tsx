import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps): JSX.Element {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      {...props}
    >
      {children}
    </svg>
  );
}

export const MenuIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M4 6h16M4 12h16M4 18h16" /></IconBase>
);
export const PanelIcon = (props: IconProps) => (
  <IconBase {...props}><rect height="16" rx="2" width="18" x="3" y="4" /><path d="M15 4v16" /></IconBase>
);
export const PenIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" /></IconBase>
);
export const CompassIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5Z" /></IconBase>
);
export const HeartIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z" /></IconBase>
);
export const HistoryIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></IconBase>
);
export const SettingsIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></IconBase>
);
export const HelpIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="M9.8 9a2.5 2.5 0 1 1 4.3 1.7c-1.1 1-2.1 1.5-2.1 3.3M12 18h.01" /></IconBase>
);
export const BadgeIcon = (props: IconProps) => (
  <IconBase {...props}><path d="m12 2 2.3 2.1 3.1-.4.6 3 2.7 1.6-1.3 2.8 1.3 2.8-2.7 1.6-.6 3-3.1-.4L12 20.2l-2.3-2.1-3.1.4-.6-3-2.7-1.6 1.3-2.8-1.3-2.8L6 6.7l.6-3 3.1.4Z" /><path d="m9.5 12 1.6 1.6 3.5-3.7" /></IconBase>
);
export const PinIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></IconBase>
);
export const SlidersIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></IconBase>
);
export const ClockIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></IconBase>
);
export const DollarIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M12 2v20M17 6.5H9.5a3.5 3.5 0 1 0 0 7h5a3.5 3.5 0 1 1 0 7H6" /></IconBase>
);
export const MicIcon = (props: IconProps) => (
  <IconBase {...props}><rect height="11" rx="3" width="6" x="9" y="2" /><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8" /></IconBase>
);
export const ArrowUpIcon = (props: IconProps) => (
  <IconBase {...props}><path d="m6 11 6-6 6 6M12 5v14" /></IconBase>
);
export const ChevronRightIcon = (props: IconProps) => (
  <IconBase {...props}><path d="m9 18 6-6-6-6" /></IconBase>
);
export const ChevronDownIcon = (props: IconProps) => (
  <IconBase {...props}><path d="m6 9 6 6 6-6" /></IconBase>
);
export const BookmarkIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1Z" /></IconBase>
);
export const ShareIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M12 3v12M8 7l4-4 4 4" /><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7" /></IconBase>
);
export const CopyIcon = (props: IconProps) => (
  <IconBase {...props}><rect height="13" rx="2" width="13" x="8" y="8" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></IconBase>
);
export const UserIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></IconBase>
);
export const CloseIcon = (props: IconProps) => (
  <IconBase {...props}><path d="m6 6 12 12M18 6 6 18" /></IconBase>
);
export const SearchIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></IconBase>
);
export const SunIcon = (props: IconProps) => (
  <IconBase {...props}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></IconBase>
);
export const CloudIcon = (props: IconProps) => (
  <IconBase {...props}><path d="M17.5 19H6a4 4 0 1 1 1.1-7.9A6 6 0 0 1 19 12.5 3.3 3.3 0 0 1 17.5 19Z" /></IconBase>
);
