/**
 * One plain answer to "how far is it?", worked out from the run the server already reports.
 *
 * The headline is the step being worked on right now, counted ("Second-marking 6 of 10"), and the
 * step list says what each step did ("1 held for you"). Nothing here calls the server: it reads the
 * same snapshot the rest of the dashboard reads.
 */

const noun = (rubric) => rubric?.work || "essay";
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** How many submissions this run is actually marking (the ones the Planner kept in). */
export function inPlay(state) {
  const subs = state?.subs || [];
  return subs.filter((s) => s.status !== "resubmit" || s.marker || s.final).length || subs.length;
}

/** The run's steps, each with what it has done so far. */
export function steps(state) {
  const status = state?.status || "idle";
  const subs = state?.subs || [];
  const stats = state?.stats || {};
  const scripts = state?.scripts;
  const total = inPlay(state);
  const marked = subs.filter((s) => s.marker).length;
  const second = subs.filter((s) => s.reviewer || s.final).length;
  const sent = subs.filter((s) => s.feedback).length;
  const held = subs.filter((s) => s.script_hold || s.status === "escalated").length;
  const work = noun(state?.rubric);

  const rows = [
    {
      id: "plan",
      name: "Plan the work",
      done: Boolean(state?.plan),
      detail: state?.plan
        ? `${plural(state.plan.steps?.length || 0, "step")}, marking ${state.plan.batch_size || 4} at a time`
        : "Reading your brief",
    },
  ];

  if (scripts) {
    const pages = scripts.pages?.length || 0;
    rows.push({
      id: "read",
      name: `Read ${plural(pages, "handwritten page")}`,
      done: scripts.status === "done",
      detail: scripts.status === "done"
        ? (held ? `${held} held for you` : "Every page read and matched to the class list")
        : "The Clerk is reading them",
    });
  }

  rows.push(
    {
      id: "mark",
      name: `Mark ${plural(total, work)}`,
      phrase: (at, of) => `Marking ${at} of ${of} ${work}s`,
      done: total > 0 && marked >= total,
      count: [marked, total],
      detail: stats.resubmit ? `${stats.resubmit} set aside, too short to mark fairly` : "Against the rubric, quoting evidence",
    },
    {
      id: "review",
      name: "Second-mark without seeing the first mark",
      phrase: (at, of) => `Second-marking ${at} of ${of}`,
      done: total > 0 && second >= total,
      count: [second, total],
      detail: stats.sent_back ? `${plural(stats.sent_back, "mark")} sent back, ${stats.fixed} corrected` : "Marks count once two markers agree",
    },
  );

  if (state?.plan?.deliver?.feedback !== false) {
    rows.push({
      id: "send",
      name: "Write and send feedback",
      phrase: (at, of) => `Writing feedback ${at} of ${of}`,
      done: status === "done" && sent > 0,
      count: [sent, total],
      detail: sent ? `${plural(sent, "message")} written` : "Waiting for settled marks",
    });
  } else {
    rows.push({ id: "send", name: "Deliver the mark sheet and class report", done: status === "done", detail: "No messages to learners, as asked" });
  }

  // Mark the step being worked on: the first one not finished, once the run is under way.
  const current = rows.findIndex((row) => !row.done);
  return rows.map((row, i) => ({
    ...row,
    state: status === "idle" ? "waiting" : row.done ? "done" : i === current && status === "running" ? "now" : "waiting",
  }));
}

/** The one-line headline above the bar, and how full the bar is (0 to 1). */
export function headline(state) {
  const status = state?.status || "idle";
  const rows = steps(state);
  const done = rows.filter((r) => r.done).length;
  if (status === "idle") return { title: "Nothing is running", detail: "Start a run and the progress shows here.", fraction: 0 };
  if (status === "done") return { title: "Finished", detail: "Every mark is settled and the files are ready.", fraction: 1 };
  if (status === "failed") return { title: "This run stopped", detail: "Nothing further was marked or sent. Run it again.", fraction: done / rows.length };
  if (state?.review?.waiting) {
    return { title: "Waiting for you", detail: "Check the memo, the rubric and the scripts, then let the Planner plan.", fraction: 0.05 };
  }
  const now = rows.find((r) => r.state === "now") || rows[rows.length - 1];
  const [at, total] = now.count || [];
  const within = total ? at / total : 0;
  return {
    // "Second-marking 6 of 10": the step being worked on, counted, so there is one plain answer
    // to "how far is it?" rather than six tiles and a log to read.
    title: total && now.phrase ? now.phrase(at, total) : now.name,
    detail: now.detail,
    fraction: Math.min(1, (done + within) / rows.length),
  };
}

/** Everything waiting for the teacher, in the order they should deal with it. */
export function attention(state) {
  const items = [];
  const scripts = (state?.scripts?.scripts || []).filter((rec) => rec.status === "held");
  for (const rec of scripts) {
    const sub = (state.subs || []).find((s) => s.script === rec.id);
    items.push({
      kind: "script",
      id: rec.id,
      learner: sub?.learner || rec.learner_name || `Name read as “${rec.name || "none"}”`,
      sid: sub?.id || null,
      title: `${sub?.learner || rec.learner_name || "Unknown learner"} · handwritten script`,
      detail: `${(rec.problems || []).join("; ")}. Nothing has been marked from it.`,
    });
  }
  for (const s of state?.subs || []) {
    if (s.status === "escalated" && !s.script_hold) {
      items.push({
        kind: "escalated", id: s.id, sid: s.id, learner: s.learner,
        title: `${s.learner} · the two markers disagree`,
        detail: s.issue || "Choose the Marker's mark or the Reviewer's.",
      });
    } else if (s.flags?.includes("instruction_to_marker")) {
      items.push({
        kind: "flagged", id: s.id, sid: s.id, learner: s.learner,
        title: `${s.learner} · ${noun(state?.rubric)} flagged`,
        detail: `It contains text that tries to instruct the marker. It was marked normally${s.final ? ` (${s.final.total}/${state.rubric.total})` : ""} and reported to you.`,
      });
    }
  }
  return items;
}
