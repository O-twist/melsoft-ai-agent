import Icon from "./Icon.jsx";
import { statusOf } from "../format.js";

/** A filled disc carrying a glyph. State is never shown by colour alone: a label always sits beside it. */
export function Disc({ tone = "idle", icon = "dot" }) {
  return (
    <span className={`disc tone-${tone}`}>
      <Icon name={icon} size={10} />
    </span>
  );
}

export function Pill({ tone, icon, children }) {
  return (
    <span className={`pill tone-${tone}`}>
      <Disc tone={tone} icon={icon} />
      {children}
    </span>
  );
}

/** Where one submission is in the workflow. */
export function StatusPill({ sub }) {
  const meta = statusOf(sub);
  return <Pill tone={meta.tone} icon={meta.icon}>{meta.label}</Pill>;
}
