# LabLess: answers for the judges

Short answers first. The detail underneath is there if a judge digs.

## How do the agents check each other?

**Short answer:** No agent's work is trusted until another agent, or code, has checked it. The Reviewer marks every piece of work a second time without seeing the first mark.

- **Blind second marking.** The Reviewer is sent the work and the rubric, and nothing else. It never receives the Marker's mark. We test this: whatever the Marker says, the Reviewer is sent the same request, word for word.
- **Evidence checks in code.** Every mark must quote the learner's work. Code checks that the quote is really there, that the totals add up, and, for the practical, that no mark is higher than the attempt log allows.
- **The Reviewer checks the others too.** It tries every exercise the Designer writes without seeing the answer or the outcome it is labelled with. It compares the Coach's rescue plans with the Designer's lesson. It checks the Windows proof answers.
- **Separation.** The Marker and the Reviewer never see who wrote the work. The Designer only ever gets class figures, never a name. The Messenger is only handed marks that both markers have settled on.
- **Show it:** switch on **Inject a fault** and run. The panel **How we corrected ourselves** lists each time a check stopped the work, who caught it and how it ended.

## What happens when the AI is wrong?

**Short answer:** It goes back once to be fixed. If it is still wrong, it is held for the teacher. Nothing uncertain reaches a learner.

- A mark the Reviewer disagrees with goes back to the Marker with the reasons. The Marker corrects it or defends it. If they still disagree, the teacher chooses.
- Feedback that states the wrong mark, or mentions another learner, is rejected and rewritten once. If it fails again it is not sent.
- A rescue plan or a lesson that fails its checks twice is held back, and the teacher is told why.
- If a model gives a broken answer or stops answering, the run does not crash. Gemini hands over to OpenRouter, and if neither can answer, the offline marker finishes the run and the live log says so.
- The teacher is always the last word. LabLess is a colleague, not a replacement.

## How is learner data kept private?

**Short answer:** The demo uses made-up learners only. The design keeps names away from the models wherever they are not needed.

- The twelve learners in the demo are example data. No real learner's work is in it.
- Marking is anonymous: the Marker and the Reviewer see the work and an id, never a name.
- The Designer never receives a name or an id, only class averages.
- Only the Messenger and the Coach use a first name, because they write to and about one learner.
- API keys and the database keys stay on the server. None is in the code repository or in the web page.
- In offline mode nothing leaves the computer at all.
- **Before a real school uses it** we would need the school's and the parents' consent under POPIA, a data agreement with the model provider, and a decision on where the data is stored. We have not done that yet, and we say so.

## What does it cost to run?

**Short answer:** The demo costs nothing. A real class is a few rand per marking run at most, and can be free.

- With no key, LabLess runs on its own offline marker: no cost and no internet. That is what makes it usable in a school with a poor connection.
- With a key, it uses Gemini's Flash model first and falls back to OpenRouter's free models.
- A full run for a class of twelve is about twenty model calls, because the agents mark in batches rather than one learner at a time.
- Week 2 and the Windows proof check never call a model, so they are free and always give the same answer.
- Hosting is a static site plus one small function, which fits the free tier of Vercel. The database is optional.

## How does it scale?

**Short answer:** One class today. The cost and the time grow with the number of learners, in batches, and nothing in the design is tied to one class or one subject.

- Work is marked in batches, not one learner at a time, so a class of forty needs a few times the model calls of the demo class, not forty times.
- A teacher can already upload their own class list, written work and rubric, and the same loop runs on it.
- The rubric, the learning outcomes and the risk rules are data files, not code. A new subject is a new rubric and a new set of outcomes.
- Each class is independent, so many classes can run side by side.
- **What we would still need for a whole school or district:** logins for teachers, a proper job queue so long runs do not depend on one web request, and storage for every class in the database rather than in files. Those are known next steps, not hidden problems.

## Questions that might come up

**Is the risk score made by the AI?** No. It is worked out by fixed rules in code from the theory mark, the PC assembly outcomes H1 to H6 and the Windows outcomes S1 to S4. That is why every score can show its reason, and why it is the same every time.

**Why is Bongani High risk if he passed?** His overall mark is 57, a pass. But the pass comes from theory. In the practical he placed parts out of order and two of his Windows proofs were wrong. The score report says this in one line, and the Planner lists each reason.

**Is the Week 2 result real?** It is a simulation of a learner who completes the rescue plan, scored again with exactly the same rules. It shows the teacher what the plan is aiming for and gives a before and after to track against. With a real class the Week 2 numbers would come from the learners' real second attempts.

**What does "offline demo mode" mean? Is there really an AI?** In offline mode the agents' answers come from a built-in marker, so the demo works without internet and gives the same result every time. The whole team, the checks and the corrections are the same code either way. With a key in place, the same loop runs on Gemini or OpenRouter.

**Does it work on a phone?** The teacher's screens work on a phone browser today. A mobile app for learners is the next step.

**Where does the Windows simulator come from?** It is an open web simulator, win11.blueedge.me, shown inside our page and credited there. It sends nothing back, which is why learners type a proof answer that the Reviewer checks.

**What is not finished?** No teacher logins yet, no real school data yet, and the dark colour theme is switched off until every screen is restyled for it.
