import Icon from "./Icon.jsx";
import { Tip, useTip } from "./Tip.jsx";
import { useSize } from "./useSize.js";
import { outcomeOf, wasCorrected, workNoun } from "../format.js";

/** Round tick values from zero up to the rubric total. */
function ticksFor(max) {
  const step = [1, 2, 5, 10, 20, 25, 50, 100].find((s) => max / s <= 6) || Math.ceil(max / 5);
  const ticks = [];
  for (let v = 0; v <= max; v += step) ticks.push(v);
  return ticks;
}

function RowTip({ s, max }) {
  const outcome = outcomeOf(s);
  return (
    <>
      <div className="tip-title">{s.id} · {s.learner}</div>
      <dl className="tip-rows">
        <div className="a-MK"><dt><i className="key" />Marker</dt><dd>{s.marker.total}/{max}</dd></div>
        {s.reviewer && <div className="a-RV"><dt><i className="key" />Reviewer</dt><dd>{s.reviewer.total}/{max}</dd></div>}
        {wasCorrected(s) && <div><dt><i className="key key-muted" />First mark, sent back</dt><dd>{s.rejected.total}/{max}</dd></div>}
      </dl>
      {outcome && <div className="tip-note">{outcome.label}</div>}
    </>
  );
}

/**
 * One row per essay: the Marker's mark and the Reviewer's blind second mark on the same scale.
 * Marks that sit together agree. A mark that was sent back shows as a cross, with an arrow to
 * where the Marker moved it. The figures are also in the Submissions table.
 */
export default function AgreementChart({ subs, rubric, selectedId, onOpen }) {
  const [ref, { width, height: boxH }] = useSize();
  const tip = useTip();
  const rows = subs.filter((s) => s.marker);
  const max = rubric.total;

  // Rows share whatever height the card has been given, between a compact and a roomy limit.
  const MIN_ROW = 26;
  const MAX_ROW = 40;
  const top = 6;
  const axisBand = 26;
  const rowH = Math.max(MIN_ROW, Math.min(MAX_ROW, Math.floor((boxH - top - axisBand) / Math.max(1, rows.length))));
  const narrow = width < 560;
  const left = 46;
  const right = narrow ? 34 : 190;
  const plotW = Math.max(80, width - left - right);
  const plotH = rows.length * rowH;
  const height = top + plotH + axisBand;
  const x = (v) => left + (Math.max(0, Math.min(max, v)) / max) * plotW;
  const ticks = ticksFor(max);

  function onKey(e, id) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpen(id);
    }
  }

  return (
    <section className="card agree-card">
      <header className="card-head">
        <div>
          <h2>Two markers, every {workNoun(rubric)}</h2>
          <p>The Reviewer marks each {workNoun(rubric)} without seeing the Marker's mark. Marks out of {max}.</p>
        </div>
      </header>

      <ul className="legend" aria-hidden="true">
        <li>
          <svg width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="4.5" className="dot-mk" /></svg>
          Marker
        </li>
        <li>
          <svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.75" className="ring-rv" /></svg>
          Reviewer, marking blind
        </li>
        <li>
          <svg width="14" height="14" viewBox="0 0 14 14" className="rej"><path d="M3 3l8 8M11 3l-8 8" /></svg>
          Marker's mark that was sent back
        </li>
      </ul>

      <div ref={ref} className="chart-box fill" style={{ minHeight: top + rows.length * MIN_ROW + axisBand }}>
        {rows.length === 0 ? (
          <p className="empty-note">Marks appear here as each batch is marked and second-marked.</p>
        ) : width > 0 && (
          <svg className="chart" width={width} height={height} role="group" aria-label={`Marker and Reviewer marks for ${rows.length} ${workNoun(rubric)}s. The same figures are in the Submissions table.`}>
            {ticks.map((t) => (
              <g key={t}>
                <line className="gridline" x1={x(t)} x2={x(t)} y1={top} y2={top + plotH} />
                <text className="tick" x={x(t)} y={top + plotH + 17} textAnchor="middle">{t}</text>
              </g>
            ))}
            {rows.map((s, i) => {
              const cy = top + i * rowH + rowH / 2;
              const mk = x(s.marker.total);
              const rv = s.reviewer ? x(s.reviewer.total) : null;
              const moved = wasCorrected(s);
              const was = moved ? x(s.rejected.total) : null;
              const dir = moved ? Math.sign(mk - was) : 0;
              const outcome = outcomeOf(s);
              return (
                <g
                  key={s.id}
                  className={`drow ${s.id === selectedId ? "on" : ""}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${s.id}, ${s.learner}. Marker ${s.marker.total}${s.reviewer ? `, Reviewer ${s.reviewer.total}` : ""}${moved ? `, first mark ${s.rejected.total} was sent back` : ""}. ${outcome ? outcome.label : ""}. Open the details.`}
                  onClick={() => onOpen(s.id)}
                  onKeyDown={(e) => onKey(e, s.id)}
                  {...tip.bind(<RowTip s={s} max={max} />)}
                >
                  <rect className="drow-hit" x={1} y={cy - rowH / 2 + 1} width={width - 2} height={rowH - 2} rx={7} />
                  <text className="drow-id" x={left - 14} y={cy} dy="0.35em" textAnchor="end">{s.id}</text>
                  {rv != null && rv !== mk && <line className="conn" x1={Math.min(mk, rv)} x2={Math.max(mk, rv)} y1={cy} y2={cy} />}
                  {moved && Math.abs(mk - was) > 30 && (
                    <>
                      <line className="fix" x1={was + dir * 8} x2={mk - dir * 15} y1={cy} y2={cy} />
                      <path className="fix-head" d={`M${mk - dir * 9},${cy} l${-dir * 7},-4 v8 z`} />
                    </>
                  )}
                  {moved && (
                    <path className="rej" d={`M${was - 4},${cy - 4} l8,8 M${was + 4},${cy - 4} l-8,8`} />
                  )}
                  {rv != null && <circle className="ring-rv" cx={rv} cy={cy} r={6.5} />}
                  <circle className="dot-mk" cx={mk} cy={cy} r={4.5} />
                  {outcome && (
                    <>
                      <circle className={`disc-bg tone-${outcome.tone}`} cx={left + plotW + 24} cy={cy} r={8} />
                      <Icon name={outcome.icon} size={10} x={left + plotW + 19} y={cy - 5} className={`disc-fg tone-${outcome.tone}`} strokeWidth="3" />
                      {!narrow && <text className="drow-out" x={left + plotW + 38} y={cy} dy="0.35em">{outcome.label}</text>}
                    </>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
      <Tip tip={tip.tip} />
    </section>
  );
}
