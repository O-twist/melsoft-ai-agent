import { Disc } from "./Badge.jsx";
import { capital, workNoun } from "../format.js";

/** The headline numbers of a run. Two of them are progress towards a known total, so they carry a meter. */
export default function StatTiles({ stats, subs, plan, rubric }) {
  const n = (key) => stats[key] ?? 0;
  const toMark = subs.filter((s) => s.status !== "resubmit").length;
  const wantsFeedback = !plan || plan.deliver.feedback;
  const tiles = [
    { label: `${capital(workNoun(rubric))}s marked`, value: n("marked"), of: toMark, icon: "check", tone: "good" },
    { label: "Sent back by the Reviewer", value: n("sent_back"), icon: "undo", tone: "warn" },
    { label: "Marks corrected", value: n("fixed"), icon: "refresh", tone: "accent" },
    { label: "Waiting for the teacher", value: n("escalated"), icon: "alert", tone: "serious" },
    { label: "Feedback delivered", value: n("delivered"), of: wantsFeedback ? toMark : null, note: wantsFeedback ? null : "not asked for", icon: "send", tone: "good" },
    { label: "Teacher decisions", value: n("human_interventions"), icon: "user", tone: "accent" },
  ];

  return (
    <section className="tiles" id="progress" aria-label="Progress of this run">
      {tiles.map((t) => (
        <div className="tile" key={t.label}>
          <div className="tile-label">
            <span>{t.label}</span>
            <Disc tone={t.value > 0 ? t.tone : "idle"} icon={t.icon} />
          </div>
          <div className="tile-value">
            {t.value}
            {t.of != null && <small>of {t.of}</small>}
            {t.note && <small>{t.note}</small>}
          </div>
          {t.of != null && (
            <div className="meter" role="img" aria-label={`${t.value} of ${t.of}`}>
              <span style={{ width: `${t.of ? Math.min(100, (100 * t.value) / t.of) : 0}%` }} />
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
