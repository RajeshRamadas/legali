import type { ReactNode } from "react";
import { Badge, ListRow, type Tone } from "./primitives";
export default function Timeline({
  items,
}: {
  items: {
    time: string;
    title: string;
    meta?: string;
    tone?: Tone;
    action?: ReactNode;
  }[];
}) {
  return (
    <div>
      {items.map((item, i) => (
        <ListRow
          key={i}
          title={item.title}
          meta={item.meta}
          leading={<Badge tone={item.tone ?? "blue"}>{item.time}</Badge>}
          trailing={item.action}
        />
      ))}
    </div>
  );
}
