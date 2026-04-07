interface MetricCardProps {
  label: string;
  value: string;
  tone?: string;
}

export function MetricCard({ label, value, tone = "neutral" }: MetricCardProps) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
