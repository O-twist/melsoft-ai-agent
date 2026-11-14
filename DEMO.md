# Two-minute live demo

The goal: show the colleague **planning**, **acting** and **correcting itself**, with the teacher checking the memo, rubric and scripts before anything is planned.

## Before you go on (5 minutes, once)

1. `.env` has `GEMINI_API_KEY` (and `OPENROUTER_API_KEY` as the backup). The top bar should read **Gemini · <model>**, not "Offline demo mode". With a real model nothing is scripted: the plan, the marks, the objections and the corrections are written by the model, and the checks are done in code.
2. `cd web && npm run build`, then `python run.py`, and open http://localhost:8000.
3. Do one full rehearsal run. A free-tier key spaces calls about 4 s apart (`GEMINI_MIN_GAP`), so the marking takes a minute or two. Talk through the plan while it runs.
4. Backup if the network fails: `MOCK=1 python run.py` gives the same workflow offline. Its marks come from text heuristics that read the topic words from the memo; the rubric and memo are still the ones on disk.

## The run (2 minutes)

| Time | Do | Say |
|---|---|---|
| 0:00 | Open **Marking desk**. Pick **Mark and send feedback**. Leave **Check materials first** on and switch on **Inject a fault**. Press **Start work**. | "I give it a goal in plain English, the way I'd ask a colleague." |
| 0:10 | The **Memo, rubric and scripts** card opens and the top bar says *Waiting for you to check the materials*. Click **Memo**, then **Rubric**, then **Scripts** and step to E06 (a soccer essay: off topic), E08 (9 words) and E11 (tries to instruct the marker). | "Before it plans anything, it shows me what it will work from: my memo, my rubric and every learner's script. Nothing has been planned or marked yet." |
| 0:35 | In the note box type: *Don't email learners yet, I only want the mark sheet and class report.* Press **Looks right, plan the work**. | "I can steer it here. That note goes to the Planner with my goal." |
| 0:45 | **Plan** card and the team lanes. The plan says no messages to learners; the Coach and Designer lanes read *Not needed*; E08 is set aside for resubmission. | "**Planning**: it read my goal and the scripts and decided what to do and who to bring in. My note changed the plan." |
| 1:00 | **Live log**: the Marker marks batch 1, then *Fault injection is on: … changed from X to Y. Nobody told the Reviewer.* | "**Acting**: it marks in batches against the rubric and memo, quoting the essay. Now I've planted a mistake." |
| 1:15 | Filter the log on **Corrections**: the Reviewer's blind mark disagrees, *Sent back to the Marker*, then *Corrected the mark*. | "**Correcting itself**: the Reviewer marks every essay again without seeing the first mark. Code compares the two, finds the gap, and sends it back. The Marker fixes it." |
| 1:40 | Open **How we corrected ourselves**, then download **Mark sheet (CSV)**. | "Every correction is written up as a story, and only agreed marks are delivered." |

## Questions you may get

**How does your agent decide what to do next?**

At two levels.

1. **The plan.** The Planner is a model call ([app/agents.py](app/agents.py), `plan`). It reads the teacher's goal, any note added at the check, whether there is a memo, and an inventory of the submissions (word counts and flags such as "too short" or "tries to instruct the marker"). It returns a plan as JSON: what to deliver, which colleagues to bring in, the batch size and who to exclude. Code checks that plan before it is used (`_clean_plan` in [app/orchestrator.py](app/orchestrator.py)): sizes are clamped, unknown learner ids are dropped, and the Coach and Designer join only when the plan explicitly asks for them. The orchestrator then runs those steps. Change the goal or the note and you get a different plan; no plan is written into the code.
2. **Step by step, from the checks.** After every action, the result of a check picks the next step. If the two marks agree, the essay goes to feedback. If they disagree, or the quoted evidence is not in the essay, it goes back to the Marker. If they still disagree after one correction, it goes to the teacher. A failed feedback message goes back to the Messenger, and is held after a second failure.

**How does it detect its own mistakes?**

It never trusts a single model answer. Every check is in code, so a model can't talk its way past one:

- **Blind second marking**: the Reviewer marks without seeing the Marker's mark. Code compares the two per criterion, with a tolerance of 15% of the criterion's maximum (`disagreements` in [app/tools.py](app/tools.py)).
- **Evidence check**: every mark must quote the essay, and code confirms the quote really appears in it (`quote_in_text`). An invented quote sends the mark back.
- **Arithmetic and ranges in code**: totals are added up by code and every score is range-checked (`clean_mark`).
- **Feedback check**: a message with the wrong mark, the wrong name, or another learner's name is rejected (`check_feedback`).
- **Handwritten pages**: low confidence, a line count that doesn't match, or a name that isn't on the class list triggers a re-read (`check_read`, `match_learner`).
- **Knowing when to stop**: one round of correction, then the teacher decides. Nothing uncertain reaches a learner.

**Isn't the injected fault fake?**

The fault is planted on purpose, so the audience can see a mistake on demand. The detection is real: the Reviewer is never told, and the same path catches genuine disagreements between the two model passes without the switch.

**What's hard-coded?**

The workflow is fixed: plan, mark, second-mark, correct, deliver. That is the colleague's way of working. The content is not fixed. The goal, rubric, memo, class list and scripts are the teacher's files (upload your own under **Class**). The plan and the marks come from the model. The minimum length and the support rules are in the rubric file. The 15% marking tolerance is in code (`disagreements` in [app/tools.py](app/tools.py)).
