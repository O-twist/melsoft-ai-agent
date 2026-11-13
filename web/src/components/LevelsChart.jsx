import { Tip, useTip } from "./Tip.jsx";
import { useSize } from "./useSize.js";
import { LEVELS, levelOf, pct, plural, settled, workNoun } from "../format.js";

/** A column that is square on the baseline and rounded at its data end. */
function column(x, y, w, h) {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

function LevelTip({ bin, max }) {
  return (
    <>
      <div className="tip-title">Level {bin.n} · {bin.name}</div>
      <dl className="tip-rows">
        <div><dt>{bin.lo}–{bin.hi}%</dt><dd>{plural(bin.learners.length, "learner")}</dd></div>
        {bin.learners.slice(0, 8).map((s) => (
          <div key={s.id} className="tip-sub"><dt>{s.learner}</dt><dd>{s.final.total}/{max}</dd></div>
        ))}
      </dl>
      {bin.learners.length > 8 && <div className="tip-note">and {bin.learners.length - 8} more</div>}
    </>
  );
}

/** The class average as the one headline figure, then how the class spreads across the CAPS levels. */
export default function LevelsChart({ subs, rubric }) {
  const [ref, { width }] = useSize();
  const tip = useTip();
  const max = rubric.total;
  const done = subs.filter(settled);
  const mean = done.length ? done.reduce((sum, s) => sum + s.final.total, 0) / done.length : 0;
  const meanPct = pct(mean, max);
  const level = levelOf(meanPct);
  const bins = LEVELS.map((l) => ({ ...l, learners: done.filter((s) => levelOf(pct(s.final.total, max)).n === l.n) }));
  const peak = Math.max(1, ...bins.map((b) => b.learners.length));

  const top = 22;
  const base = 112;
  const height = base + 40;
  const slot = width / LEVELS.length;
  const barW = Math.min(24, Math.max(8, slot * 0.42));

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>How the class did</h2>
          <p>Final marks grouped by CAPS achievement level.</p>
        </div>
      </header>

      {done.length === 0 ? (
        <p className="empty-note">The class picture builds up as marks are approved.</p>
      ) : (
        <div className="hero">
          <div className="hero-figure">{meanPct}<span>%</span></div>
          <div className="hero-text">
            <b>Class average</b>
            <span>{mean.toFixed(1)} out of {max} · Level {level.n}, {level.name}</span>
            <span>{plural(done.length, workNoun(rubric))} with a final mark</span>
          </div>
        </div>
      )}

      <div ref={ref} className="chart-box">
        {done.length > 0 && width > 0 && (
          <svg className="chart" width={width} height={height} role="img" aria-label={`Number of learners at each achievement level: ${bins.map((b) => `level ${b.n}, ${b.learners.length}`).join("; ")}.`}>
            {bins.map((b, i) => {
              const n = b.learners.length;
              const h = n ? Math.max(4, (n / peak) * (base - top)) : 0;
              const x0 = i * slot + (slot - barW) / 2;
              const mid = i * slot + slot / 2;
              return (
                <g key={b.n} className="col" {...tip.bind(<LevelTip bin={b} max={max} />)}>
                  <rect className="col-hit" x={i * slot + 2} y={0} width={Math.max(0, slot - 4)} height={height} rx={8} />
                  {n > 0 && <path className="col-bar" d={column(x0, base - h, barW, h)} />}
                  {n > 0 && <text className="col-val" x={mid} y={base - h - 7} textAnchor="middle">{n}</text>}
                  <text className="col-level" x={mid} y={base + 18} textAnchor="middle">{b.n}</text>
                  <text className="tick" x={mid} y={base + 33} textAnchor="middle">{b.lo}–{b.hi}</text>
                </g>
              );
            })}
            <line className="axisline" x1={0} x2={width} y1={base + 0.5} y2={base + 0.5} />
          </svg>
        )}
      </div>
      {done.length > 0 && <p className="chart-caption">Level, with its percentage band underneath. Bars count learners.</p>}
      <Tip tip={tip.tip} />
    </section>
  );
}
