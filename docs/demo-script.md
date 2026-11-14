# LabLess: the 3-minute demo

Melsoft Colleague Zero, Saturday 14 November 2026, 12:00, WeWork The Link, Rosebank.

One person talks, one person clicks. The words in quotation marks are what to say. Everything else is what to do. The timings add up to three minutes. Everything is reached from the menu on the left (on a phone, the ☰ button).

## Before you walk on

1. Start LabLess on the laptop: double-click `start.cmd`, then open http://localhost:8000. The bottom of the sidebar says **Offline mode** when no API key is set. In that mode the demo needs no internet, apart from the Windows simulator and the online 3D models.
2. Start from a clean state, so the numbers are the ones in the story: stop the server, delete the `output` folder, start it again. **Today** must show **3** learners needing help now, and Bongani Sithole as **High**.
3. Open **Settings & test mode → Test mode** and check that both switches are **off**. You switch one on live in the demo.
4. Open **Lab → Windows tasks** and press **Start the simulator** once, so it is already loaded. Go back to **Today**.
5. Have the backup video open in a video player, paused at the start, in case the laptop or the Wi-Fi fails.
6. Browser at 100% zoom, full screen, laptop size (the pages are laid out for 1440 × 900).

If the site asks you to log in (the online version with accounts switched on), log in with the team's account, or press **Try the sample class without an account**.

## The demo

| Time | Do | Say |
|---|---|---|
| 0:00 – 0:20 | Stay on **Today**. | "Many South African schools teach Grade 12 Computer Applications Technology without a working computer lab. Learners must pass practical tasks they have barely practised. Teachers are stretched, so practicals go unmarked and the learners who are falling behind are found too late. LabLess is a team of seven AI agents that works alongside the teacher." |
| 0:20 – 0:35 | Point at **Who needs help this week**. Click **Bongani Sithole**; his drawer opens. Close it. | "This is the teacher's morning. Every learner who needs help comes with a reason in plain words. Bongani passed, 57 out of 100, but he still needs help now: the practical shows gaps. A pass mark alone would have hidden him." |
| 0:35 – 0:45 | **Settings & test mode → Test mode**. Switch on **Plant a wrong mark**. Point at **Test mode on** in the top bar. | "To prove it checks itself, we plant a mistake on purpose. It lives here in Settings, never next to the Start button, and nobody tells the agents." |
| 0:45 – 1:10 | **New run** → choose **PC assembly practical** → **Next** → **The whole job** → **Next** → **Start work** → **Start work**. The run stops at **Memo, rubric and scripts**: click **Memo**, then **Scripts**, then **Looks right, plan the work**. Point at the headline, the steps and **Who is working**. | "One brief in plain words. Before it plans anything, it shows me the memo, the rubric and every script it will work from; I say go. The Planner picks the team. Watch the headline: marking, then second-marking without seeing the first mark, then correcting, then delivering. Seven colleagues, one plan: Plan, Do, Check, Correct, Deliver." |
| 1:10 – 1:30 | When it says **Finished**, open the **Checks** tab. Point at the first story, tagged **Planted fault**. | "Here is the mistake we planted. The Reviewer caught it from the attempt log and its own blind mark, sent it back, and the Marker fixed it. Anything that fails twice is held for the teacher. Nothing uncertain reaches a learner." |
| 1:30 – 1:45 | **Learners** → click **Bongani Sithole**. Scroll the drawer to **Catch-up plan from the Coach**. | "The same run wrote Bongani's catch-up plan: three steps from the Coach, each tied to a learning outcome." |
| 1:45 – 2:05 | In the drawer, under **What to work on**, press **Open in Lab** on **Build order**. Place the Motherboard, CPU and RAM. Then **3D parts** tab. | "Every gap opens the practice that closes it. No lab needed: he builds the PC in the browser, every try is logged, and that log is what the agents mark. Each part also opens as a 3D model, even offline." |
| 2:05 – 2:20 | **Lab → Windows tasks**. Choose **Bongani Sithole**, type `Liber-V NS14A8` under **Find system info**, press **Hand in the proofs**. | "The same for software: he does the task in a Windows simulator and types a proof. The Reviewer checks it." |
| 2:20 – 2:40 | **Learners** → switch to **Week 2 (after catch-up)**. Point at Bongani's row. | "A week later the loop runs again on his plan, with the same rules. Bongani goes from a risk of 53, High, to 22, on track. His mark goes from 57 to 78." |
| 2:40 – 2:52 | Click Bongani → **Score report** → **Week 2**. Point at **Print or save as PDF**. | "And this is the report he takes home: 78 out of 100, ready to print." |
| 2:52 – 3:00 | Stay on the report. | "Next for LabLess: a mobile app for learners who only have a phone, more subjects than CAT, and a pilot in one school with a real class. Thank you." |

## Things that can go wrong, and what to do

- **Today does not show 3 needing help and Bongani as High.** Something was saved from an earlier practice run. Stop the server, delete the `output` folder, start it again.
- **After the Windows step, Bongani's Week 1 row changes.** That is correct: the proofs he handed in count at once. The Week 2 table always measures from Week 1 as marked, so it still reads 53 → 22 and 57 → 78. To keep Week 1 unchanged, type the proof but don't press **Hand in the proofs**.
- **Don't press Save for marking in the PC lab with Bongani selected before the Week 2 step.** It changes his Week 1 numbers for the same reason.
- **Test mode is still on after the demo.** Switch it off in Settings, or the next run plants a fault too. The top bar shows **Test mode on** while it is on.
- **The Windows simulator is blank.** It is an outside website and needs the internet. Say "the simulator needs a connection" and carry on; the proof check still works without it.
- **A 3D model does not load.** LabLess switches to the offline PC model by itself.
- **To skip the materials check**, untick **Check the memo, rubric and scripts first** in step 3 of New run. Online it is skipped anyway, because a run there cannot pause.
- **The run seems slow.** It takes about 14 seconds offline. Keep talking through the agents. If it says **This run stopped**, press **Run again**.

## If you demo from the website

The same steps work on the Vercel address. There, the team does the whole loop in one request and the Run page plays it back step by step, so it looks and paces the same. Uploading your own class and photographed scripts are left out online. A refresh keeps the last run and the Week 2 result in that browser tab.
