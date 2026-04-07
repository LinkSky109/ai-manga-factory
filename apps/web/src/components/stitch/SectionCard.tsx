import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function SectionCard({ title, eyebrow, actions, children }: SectionCardProps) {
  return (
    <section className="section-card">
      <header className="section-card-header">
        <div>
          {eyebrow ? <p className="section-eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        {actions}
      </header>
      <div className="section-card-body">{children}</div>
    </section>
  );
}
