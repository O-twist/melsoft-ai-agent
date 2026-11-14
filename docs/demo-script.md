# LabLess: the 3-minute demo

Melsoft Colleague Zero, Saturday 14 November 2026, 12:00, WeWork The Link, Rosebank.

One person talks, one person clicks. The words in quotation marks are what to say. Everything else is what to do. The timings add up to three minutes.

## Before you walk on

1. Start LabLess on the laptop: double-click `start.cmd`, then open http://localhost:8000. The header must say **Offline demo mode**. The demo does not need the internet in this mode, apart from the Windows simulator and the online 3D models.
2. Start from a clean state so the numbers are the ones in the story: stop the server, delete the `output` folder, start it again. The home screen must show **3** learners at risk and Bongani Sithole as **High**.
3. Open the **Lab** tab once, choose **PC assembly practical**, and press **Start the simulator** in the Windows card so it is already loaded. Go back to **Home**.
4. Have `output/demo/lablest-backup-demo.mp4` open in a video player, paused at the start, in case the laptop or the Wi-Fi fails.
5. Keep the browser at 100% zoom, full screen.

## The demo

| Time | Do | Say |
|---|---|---|
| 0:00 – 0:20 | Stay on **Home**. | "Many South African schools teach Grade 12 Computer Applications Technology without a working computer lab. Learners must pass practical tasks they have barely practised. Their teachers are stretched, so practicals go unmarked and the learners who are falling behind are found too late. LabLess is a team of seven AI agents that works alongside the teacher." |
| 0:20 – 0:35 | Point at the navy card (**3** learners at risk), then at Bongani Sithole's row. | "This is the teacher's home screen. The Planner has scored the class, and every score comes with its reason. Look at Bongani Sithole. He passed, with 57 out of 100, but he is still High risk, because his practical shows gaps. A pass mark alone would have hidden him." |
| 0:35 – 1:05 | **Lab** tab. Choose **PC assembly practical**. Press **The whole job**. Switch on **Inject a fault**. Press **Start work**. Let the loop and the team board run. | "The teacher gives one goal in plain words. The Planner reads it and decides who is needed. Watch the loop: Plan, Do, Check, Correct, Deliver. The Marker marks each attempt. The Reviewer marks it again blind, without ever seeing the Marker's mark. The Coach writes the rescue plans. The Designer drafts the next lesson and never sees a learner's name. The Messenger writes the feedback. Seven agents, one plan." |
| 1:05 – 1:30 | Scroll down to **How we corrected ourselves**. Open the first story. | "Before we started, we planted a fault in one of the Marker's marks, and told nobody. The Reviewer caught it, from the attempt log and from its own blind mark, and sent it back. The Marker corrected it. Anything that fails a check goes back once. If it fails again, it is held for the teacher. Nothing uncertain is ever sent to a learner." |
| 1:30 – 1:45 | **Home** tab. Press **Build rescue plan** on Bongani's row. His plan opens. Scroll to the Coach's three steps. Close it. | "Here is Bongani's rescue plan: what both markers found in his attempt log, and three catch-up steps from the Coach, each tied to a learning outcome." |
| 1:45 – 2:10 | **Reports** tab, choose Bongani. Scroll to **Where to improve**. Press **Open the virtual lab at the motherboard step**. Place the motherboard, the CPU and the RAM. Press **View model** on a part. | "This is his score report. Every gap links straight to the practice that closes it. This one opens the PC Assembly Challenge at the step he got wrong. No lab needed: he builds the PC in the browser, every try is logged, and that log is what the agents mark. And each part opens as a 3D model he can turn around." |
| 2:10 – 2:25 | **Reports** tab, Bongani again. Press **Open the Windows task: find system info**. Type `Liber-V NS14A8` in the S4 box. Press **Hand in the proofs**. | "The same for software. He does the task in a Windows simulator and types a proof answer. The Reviewer checks the proof and maps it to the Windows outcomes." |
| 2:25 – 2:45 | **Home** tab. Press **Their week 2** on Bongani's row. Point at the table. | "Now the important part. A week later, the loop runs again on his rescue plan. Bongani goes from a risk score of 53, High, to 22, Low. His mark goes from 57 to 78. The teacher can see that the catch-up worked." |
| 2:45 – 2:55 | **Reports** tab, choose Bongani, press **Week 2**. Point at **Print or save as PDF**. | "And this is the report he takes home: 78 out of 100, Low risk, ready to print." |
| 2:55 – 3:00 | Stay on the report. | "Next for LabLess: a mobile app for learners who only have a phone, more subjects than CAT, and a pilot in one school with a real class. Thank you." |

## Things that can go wrong, and what to do

- **The numbers on Home are not 3 at risk and Bongani High.** Something was saved from an earlier practice run. Stop the server, delete the `output` folder, start it again.
- **Do not press "Save for marking" in the PC Assembly Challenge with Bongani selected, and do not run the "Handwritten scripts too" goal, before the Week 2 step.** Both change his Week 1 numbers on the home screen, because practice and newly marked work count straight away. The Week 2 table is safe either way: it always measures from Week 1 as marked, so it always reads 53 → 22 and 57 → 78.
- **After the Windows step, Bongani's row on Home can change.** That is correct: the proofs he has just handed in count at once, so his Week 1 risk moves (four good proofs take him to Medium, and Home then shows 2 at risk). If a judge asks, say exactly that. To keep Home unchanged for the whole demo, type the proof but do not press **Hand in the proofs**.
- **The Windows simulator is blank.** It is an outside website and needs the internet. Say "the simulator needs a connection", and move on to Week 2. The checklist and the Reviewer's check still work without it.
- **A 3D model does not load.** LabLess shows the offline PC model instead, by itself. Carry on.
- **The venue Wi-Fi is down.** Everything except the simulator and the online 3D models works offline on the laptop. If the laptop itself fails, play the backup video.
- **The loop seems to have stopped.** It takes about 14 seconds in offline mode. Keep talking through the agents. If the header says **Stopped**, press **Run again**.

## If you demo from the website instead of the laptop

The same steps work on the Vercel address. There the team does the whole loop in a single request and the page plays the run back, so it looks and paces the same. Two differences: the **Your own class** and **Handwritten scripts** cards are left out, and a refresh keeps the last run and the Week 2 result in that browser tab only.
