import { pct, settled } from "../format.js";

/** The class average on each rubric criterion, each against its own maximum. */
export default function CriteriaMeters({ subs, rubric }) {
  const done = subs.filter(settled);
  const rows = rubric.criteria.map((c) => {
    const mean = done.length ? done.reduce((sum, s) => sum + s.final.scores[c.id].score, 0) / done.length : 0;
    return { id: c.id, name: c.name, max: c.max, mean, percent: pct(mean, c.max) };
  });
  const lowest = Math.min(...rows.map((r) => r.percent));
  const weakest = rows.filter((r) => r.percent === lowest);

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>Where the marks were won and lost</h2>
          <p>Class average on each part of the rubric.</p>
        </div>
      </header>

      {done.length === 0 ? (
        <p className="empty-note">Averages appear once marks are approved.</p>
      ) : (
        <div className="meter-list">
          {rows.map((r) => (
            <div className="meter-row" key={r.id}>
              <span className="meter-name">
                {r.name}
                {weakest.length === 1 && weakest[0].id === r.id && <span className="tag">Lowest</span>}
              </span>
              <span className="meter-fig"><b>{r.percent}%</b><small>{r.mean.toFixed(1)} / {r.max}</small></span>
              <span className="meter thick" role="img" aria-label={`${r.name}: ${r.percent} percent`}>
                <span style={{ width: `${r.percent}%` }} />
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
