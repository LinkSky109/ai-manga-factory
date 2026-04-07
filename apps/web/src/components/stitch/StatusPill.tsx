interface StatusPillProps {
  children: string;
  tone?: string;
}

export function StatusPill({ children, tone = "neutral" }: StatusPillProps) {
  return <span className={`status-pill tone-${tone}`}>{children}</span>;
}
