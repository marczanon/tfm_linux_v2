import type { ReactNode } from "react";

export function PanelTitle({
  eyebrow,
  icon,
  title,
}: {
  eyebrow: string;
  icon?: ReactNode;
  title: string;
}) {
  return (
    <div className="panel-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {icon}
    </div>
  );
}
