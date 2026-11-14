# LabLess handoff

Updated Saturday 14 November 2026, about 08:00 SAST, on branch `redesign/app-shell` (draft PR into `cursor/lablest-demo-ready-9ca7`).

## What is done

**App shell and navigation**
- A fixed left sidebar on a laptop: logo, class switcher, Today, New run, Runs, Learners, Classes, Lab, Messages, and Settings & test mode. It shows a status line ("AI marking on · Gemini" or "Offline mode") and badges for what needs attention.
- On a phone: a top bar with a ☰ button that opens a slide-out side panel over a dim backdrop. There is no bottom pill nav.
- Hash routes (`#/learners/E10?tab=essay`), so deep links and refresh work on any host without server rewrites.

**Test mode**
- "Plant a wrong mark", "Plant a bad handwriting reading" and "Use the sample handwritten scripts" live only in Settings → Test mode. All are off by default.
- A **Test mode on** badge shows in the top bar while either fault is on. Runs started in test mode are labelled, and planted faults are tagged in Checks.

**Pages (one job each)**

| Page | What it shows |
|---|---|
| Today | Four stat tiles, Needs your attention (held scripts, disputed marks, flagged essays, each with plain actions), Who needs help this week with one next step each, Latest run, and Recent runs. |
| New run | A 3-step form (Class and work, What to do, Check and start) with option cards, an editable brief, a "What will happen" preview of the colleagues who join, and a confirm dialog before starting. |
| Run | A plain headline ("Second-marking 4 of 11", about N seconds left), a progress bar, a step list with result lines, and Who is working. Tabs: Progress, Team (loop, timeline, plan, glossary), Checks (counts plus the corrections story with Planted fault tags), Results (downloads, charts, catch-up plans, lesson, consistency, class report, Clerk's review) and Activity log. A stopped run shows "This run stopped" with **Run again**. |
| Runs | History table: when, what, how long it took, marked, fixed, held and status. |
| Learners | Needs help, All learners and Catch-up plans, with search and a Week 1 / Week 2 switch. Each learner has a plain reason and one next step (the risk number is secondary). Clicking a learner opens a right-hand drawer: Overview (your decision, areas, what to work on with Lab and 3D links, catch-up plan, score report, Week 2), Essay (marks per criterion from both markers, the text, the history), Practical (H1–H6 and S1–S4 by name) and Messages. |
| Classes | Class cards, the learner list with essay marks, the rubric and outcomes viewers, and the upload form (local only). |
| Lab | Tabs for PC assembly, 3D parts (falls back to the local model when offline), Windows tasks (the simulator loads only when started) and Attempts. |
| Messages | Messages written, held for you, and catch-up plans, with a filter, a preview pane and Copy. |
| Settings | General (profile, sign out), AI marking (main model, backup, offline), Test mode, and About the agents. |
| Score report | `#/report/E10` and `#/report?mode=class`: the printable report, Week 1 or Week 2. |

**Look**
- Flat white cards with 1 px borders and 12 px radius. Inter. Navy primary buttons. High, Medium and On track chips in the approved colours.
- Grey text darkened to #5F6779 (about 5.8:1 on white). Tap targets are 44 px on a phone.
- The main desktop pages fit 1440 × 900 with no page-level scroll. Lab's PC tab scrolls about 70 px inside the content area.
- There are skeleton loaders, empty states with one action, and plain error states.

**Teacher accounts**
- Log in, Create account, Forgot password, Check your email, and Sign out, using Supabase Auth over REST with no SDK.
- The browser gets the Supabase URL and anon key at runtime from `GET /api/config`, so no `VITE_` variables are used. The anon key is public by design. The service role key is never sent to the browser or used by the account code.
- The backend verifies `Authorization: Bearer <jwt>` with `{SUPABASE_URL}/auth/v1/user` and calls PostgREST **with the teacher's own token**, so row level security does the isolation. Endpoints: `GET /api/me`, `POST /api/profile`, `POST /api/runs`, `POST /api/classes/sample`.
- Each run records the teacher who started it. Another teacher or a guest sees an empty desk, and can't download that run's files or decide on its marks. Run history in the browser is kept per teacher, and signing out clears the run the tab was holding.
- Onboarding for a new teacher: "Welcome, {name}" with **Load the sample Grade 12 CAT class** or **Upload your own class**.
- **Try the sample class without an account** on the login page is a safety valve if email confirmation blocks a judge.

**Reliability**
- On Vercel, a run happens inside the request that starts it and the browser plays it back step by step (from earlier today). Any instance can serve the next request, and a refresh keeps the run in that tab.
- Live models get about 35 seconds per run, then the offline marker finishes the run and the log says so.

**Tests**
- 183 Python tests, including a fake Supabase that checks teacher B can't see teacher A's runs, classes or files.
- 19 web tests. `npm run build` passes.

## What is left (in priority order)

1. **Apply the accounts migration** (steps below). Until it is applied, sign-up and login still work, but saved run history and profile edits fail quietly; the browser's own history still shows.
2. **Switch off "Confirm email"** in Supabase if judges should sign up instantly (steps below).
3. **Persist runs and events in Supabase** (`run_events`, `messages`), so a run started on one device can be watched from another. The tables and policies are in the migration; the server does not write them yet. Today a run lives in the browser tab that started it (Vercel) or in the local server's memory.
4. **Uploads on Vercel**: put photographed scripts in the private `scripts` bucket under `{uid}/...` instead of `/tmp`, then turn uploads back on there. The bucket and policies are in the migration.
5. **Classes per teacher**: "Load the sample class" records a `classes` row, but runs still use the class files on the server. Uploaded classes are kept on the local server only.
6. **Runs page**: earlier runs open as a summary, not as a full Run page.
7. Polish: a dark theme (switched off for now), a Search box in the top bar, and the phone layout of some reused cards (charts, PC lab).

## Architecture

- `web/` is React and Vite.
  - `src/App.jsx` holds the auth gate and the workspace, `src/pages/*` the pages, and `src/pages/Shell.jsx` the sidebar and phone panel.
  - Helpers: `src/router.js` (hash routes), `src/auth.js` (Supabase Auth over REST, and adds the token to `/api/*` calls), `src/prefs.js` (per-browser settings and history), `src/plain.js` (plain-language reasons and run progress, tested) and `src/replay.js` (plays back a run recorded on Vercel).
  - The pages reuse the existing, tested components in `src/components/` (PC assembly, 3D parts, Windows station, team board, corrections, charts, catch-up plans, lesson, score report).
- `run.py` is the standard-library HTTP server, and `api/index.py` serves the same handler on Vercel. `app/accounts.py` holds the token checks and PostgREST calls made as the teacher.
- The agents and the loop are unchanged: `app/orchestrator.py`, `app/agents.py`, `app/tools.py`.

## Environment variables (names only)

`GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `MOCK`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (optional, used only by the old class-copy writer in `app/store.py`), `RUN_SECONDS` (live-model time per run on Vercel, default 35), `LLM_DEADLINE`, `ACCOUNTS` (set to `0` to switch accounts off even when Supabase is set).

## Migration steps (owner to apply)

1. Supabase dashboard → project "LabLess - Agentic AI" → **SQL editor** → New query.
2. Paste all of `supabase/migrations/20261114060000_accounts.sql` and press **Run**. It creates `profiles` (with a sign-up trigger), `classes`, `class_learners`, `submissions`, `runs`, `run_events`, `messages` and `uploads`, turns on row level security (`owner_id = auth.uid()`), and creates the private `scripts` storage bucket with per-teacher folder policies. The first migration's tables and the seed are not touched.
3. To make judge sign-up instant: **Authentication → Sign In / Providers → Email** → switch off **Confirm email** → Save. With it on, new teachers see "Check your email".
4. Optional: **Authentication → URL Configuration** → set the Site URL to the Vercel address, so reset links come back to LabLess.

## Deploy steps (owner)

1. Vercel project `labless` already has `SUPABASE_URL` and `SUPABASE_ANON_KEY`. With them set, the site shows the login page. To demo without accounts, add `ACCOUNTS=0`.
2. Redeploy from this branch the usual way (file upload): `vercel --prod` from the repo root, or upload the folder. `vercel.json` builds `web/dist` and sends `/api/*` to `api/index.py` (max duration 60 s).
3. After deploying, check that `/api/config` returns `{"auth": true, ...}` with the anon key only, then sign up a test teacher and start one run.

## Known risks

- **Email confirmation on** blocks instant judge sign-up. Switch it off (step 3), or use the guest link.
- **Migration not applied**: accounts work, but history and profile saving fail quietly.
- **Vercel Hobby limit**: a live-model run is capped at about 35 seconds, then finished offline. For a full live run, use the laptop (`python run.py`).
- **Local server, two teachers at once**: one run at a time. The second teacher is told another run is in progress.
- **The backup video** (`output/demo/lablest-backup-demo.mp4`) shows the old single-page look.
