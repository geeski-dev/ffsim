interface Props {
  collapsed: boolean;
}

export default function CollapseChevron({ collapsed }: Props) {
  return (
    <svg
      className="collapse-chevron"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={collapsed ? 'M4 6l4 4 4-4' : 'M4 10l4-4 4 4'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
