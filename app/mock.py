"""Offline replies for every agent task, built from simple text heuristics (no AI involved)."""
import json
import os
import re
from pathlib import Path

from . import tools

MISSPELT = r"\b(alot|becuase|thier|wich|definately|recieve|untill|freind|dont|cant|then harm|then bad)\b"


def _on_topic(text, terms):
    """How far an answer uses the topic's own words (from the teacher's memo, else the task), from 0 to 1."""
    hits = 0
    for term in terms or []:
        stem = term[:-1] if term.endswith("y") and len(term) > 4 else term  # technology -> technolog(y|ies|ical)
        hits += len(re.findall(re.escape(stem), text, re.I))
    return min(1.0, hits / 4)


def _facts(text, terms=()):
    """What the heuristics can measure in an essay. terms: the words that show it is on the topic that was set."""
    return {
        "words": len(re.findall(r"[A-Za-z']+", text)),
        "paras": len([p for p in re.split(r"\n\s*\n", text) if p.strip()]),
        "sents": [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()],
        "slips": len(re.findall(r"\bi\b", text)) + len(re.findall(MISSPELT, text, re.I)),
        "on_topic": _on_topic(text, terms),
    }


def _score(text, rubric, nudge=0):
    f = _facts(text, tools.topic_terms(rubric))
    n, paras, sents, errors = f["words"], f["paras"], f["sents"], f["slips"]
    quality = {
        "content": (0.6 * min(1, n / 230) + 0.4 * min(1, paras / 5)) * (0.25 + 0.75 * f["on_topic"]),
        "language": 0.55 * max(0, 1 - errors / 6) + 0.45 * min(1, (n / max(1, len(sents))) / 15),
        "structure": min(1, paras / 5),
    }
    evidence = " ".join((sents[1] if len(sents) > 1 else text).split()[:8])
    scores = {}
    for c in rubric["criteria"]:
        q = quality.get(c["id"], 0.6)
        score = round(c["max"] * q * 0.95) + (nudge if c["id"] == "content" else 0)
        scores[c["id"]] = {
            "score": max(0, min(c["max"], score)),
            "evidence": evidence,
            "reason": f"Heuristic estimate for {c['name'].lower()} ({n} words, {paras} paragraphs, {errors} language slips).",
        }
    return scores


# ---- question-paper tests (Mathematics, Physical Sciences, History) ------------------------------------

def _maths_text(text):
    """An answer as the patterns in a test rubric expect it: lower case, superscripts and signs spelt plainly."""
    t = str(text).lower()
    for old, new in (("²", "^2"), ("³", "^3"), ("⁶", "^6"), ("−", "-"), ("–", "-"),
                     ("×", "x"), ("→", "->"), ("’", "'")):
        t = t.replace(old, new)
    return re.sub(r"(?<=\d),(?=\d)", ".", t)  # a decimal comma is a decimal point


def _matches(patterns, answer):
    """The patterns that fit the answer as written (spaces kept) or with every space taken out."""
    spaced = re.sub(r"\s+", " ", _maths_text(answer))
    compact = re.sub(r"\s+", "", spaced)
    return [p for p in patterns or [] if re.search(p, spaced) or re.search(p, compact)]


def test_answers(text):
    """A test script split into its numbered parts: {"1.1": "the learner's answer", ...}."""
    answers, label = {}, None
    for line in str(text).splitlines():
        m = re.match(r"\s*(\d+\.\d+)\s*[).:-]?\s+(.*)", line)
        if m:
            label = m.group(1)
            answers[label] = m.group(2).strip()
        elif label and line.strip() and not re.match(r"\s*question\s+\d+\s*$", line, re.I):
            answers[label] += " " + line.strip()
    return answers


def part_score(part, answer):
    """(marks, why) for one numbered part, from the memo's patterns: the right answer, method marks, or points."""
    marks = int(part.get("marks") or 0)
    if not answer:
        return 0, "not answered"
    if part.get("points"):
        got = _matches(part["points"], answer)
        each = int(part.get("each") or 1)
        return min(marks, each * len(got)), f"{len(got)} of the memo's points"
    if _matches(part.get("accept"), answer):
        return marks, "matches the memo"
    if _matches(part.get("method"), answer):
        return (max(1, marks // 2) if marks > 1 else 0), "right method, wrong answer"
    return 0, "does not match the memo"


def _test_score(text, rubric):
    """Marks for one answer script, part by part against the memo, with a learner's own line as evidence."""
    answers = test_answers(text)
    first = next((line.strip() for line in str(text).splitlines() if len(tools._norm(line)) >= 8), "")
    scores = {}
    for c in rubric["criteria"]:
        total, notes, lines = 0, [], []
        for part in c.get("parts") or []:
            got, why = part_score(part, answers.get(part["label"], ""))
            total += got
            notes.append(f"{part['label']} {got}/{part['marks']} ({why})")
            if answers.get(part["label"]):
                lines.append(answers[part["label"]])
        quote = " ".join(max(lines, key=len, default="").split()[:12])
        scores[c["id"]] = {
            "score": max(0, min(c["max"], total)),
            "evidence": quote if len(tools._norm(quote)) >= 8 else first,
            "reason": ("Against the memo: " + "; ".join(notes) + ".") if notes else "No parts listed for this question.",
        }
    return scores


def _topic(name):
    """'Question 2: Equations and inequalities' -> 'Equations and inequalities'."""
    return name.split(": ", 1)[-1]


def _catch_up_test(c, outcomes, rubric):
    """A catch-up plan for one learner on a subject test, from the question they lost most marks on."""
    first, text, scores = c["first_name"], c["text"], c["scores"]
    subject = (rubric.get("subject") or "the subject").replace("Grade 10 ", "")
    if not scores:
        return {
            "id": c["id"],
            "why": (f"{first} has no {subject} test on record that could be marked, so there is no evidence yet of what "
                    f"{first} can do. The gap may be about time or confidence more than skill, which is worth a quiet conversation."),
            "evidence": "",
            "strength": "",
            "steps": [{"outcome": o["id"], "minutes": 25,
                       "activity": f"Answer this part of the test under test conditions and hand it in: {o['text']}"}
                      for o in _three(list(outcomes), outcomes)],
            "check": f"A complete answer script from {first} that can be marked against the memo.",
        }
    order = sorted(scores, key=lambda s: s["score"] / s["max"])
    weak, best = order[0], order[-1]
    parts = next((x.get("parts") or [] for x in rubric["criteria"] if x["id"] == weak["id"]), [])
    answers = test_answers(text)
    marked = [(p, *part_score(p, answers.get(p["label"], ""))) for p in parts]
    lost = [p["label"] for p, got, _ in marked if got < p["marks"]]
    why = (f"{first} lost most marks on {_topic(weak['name']).lower()} ({weak['score']}/{weak['max']})"
           + (f", in parts {', '.join(lost)}" if lost else "") + ". ")
    if any(why_part == "right method, wrong answer" for _, _, why_part in marked):
        why += "The working shows the right method in places but the final answers slip, so careful checking will win marks back."
    else:
        why += "The memo's method is not there yet, so this needs re-teaching before more practice."
    picks = [o for o in outcomes if weak["id"] in o["criteria"]][:2]
    for s in order[1:]:
        picks += [o for o in outcomes if s["id"] in o["criteria"] and o not in picks][:1]
    activities = [
        (f"Redo parts {', '.join(lost) or 'of this question'} with the memo's worked answers open, copying each step "
         "and saying why it follows.", 20),
        ("Cover the memo and do the same parts again from scratch, then mark them yourself and correct every slip "
         "in a different colour.", 20),
        ("Do three fresh questions of the same kind from the textbook and check them with a study partner.", 15),
    ]
    evidence = " ".join((answers.get(lost[0]) or "" if lost else "").split()[:12])
    return {
        "id": c["id"],
        "why": why,
        "evidence": evidence if len(tools._norm(evidence)) >= 8 else _quote(text),
        "strength": (f"{_topic(best['name'])} is {first}'s strongest area at {best['score']}/{best['max']}, "
                     "so the plan builds on something that already works."),
        "steps": [{"outcome": o["id"], "activity": a, "minutes": m} for o, (a, m) in zip(_three(picks, outcomes), activities)],
        "check": f"Ask {first} to redo parts {', '.join(lost) or 'of the weakest question'} without the memo, and look for full marks on each.",
    }


# ---- the Coach: catch-up plans -----------------------------------------------------------------

# What a learner does with an essay that was marked, by the id of the outcome it practises: (activity, minutes).
_ACTIVITY = {
    "W1": ("Before rewriting anything, spend ten minutes on a plan: list six ideas for the topic, cross out the two "
           "weakest and number the rest in the order they will be used.", 10),
    "W2": ("Take the thinnest paragraph of the essay and rebuild it as three sentences: the point, a specific example "
           "from real life, and why that example proves the point.", 20),
    "W3": ("Copy the essay question at the top of a page and underline its key words. Write one sentence that answers "
           "it directly, then tick every paragraph of the essay that supports that sentence.", 15),
    "W4": ("Cut the essay into its paragraphs, label each one introduction, point or conclusion, and put them in the "
           "strongest order. Write whichever part is missing.", 20),
    "W5": ("Join the paragraphs of the essay with linking words: choose from 'firstly', 'in addition', 'however', "
           "'as a result' and 'in conclusion', using each one once.", 15),
    "W6": ("Read the essay aloud with a pencil in hand: circle every 'i' that should be a capital, every missing "
           "apostrophe and every 'then' that should be 'than', and correct them.", 15),
    "W7": ("Find five casual words or phrases in the essay and replace each with a more formal one, using a "
           "dictionary or a thesaurus.", 15),
    "W8": ("Make a five-point checklist (capital letters, full stops, spelling, paragraphs, answers the question) and "
           "check the essay against it with a study partner.", 15),
}
# The same for a learner with no essay yet, where the first job is to get a complete draft on paper.
_FRESH = {
    "W1": ("Spend ten minutes planning the essay: write the question at the top of a page, list six ideas, cross out "
           "the two weakest and number the rest in order.", 10),
    "W4": ("Write the essay from that plan in one sitting: an introduction, one paragraph for each idea and a "
           "conclusion. A complete draft matters more than a perfect one.", 30),
    "W8": ("Check the draft against a five-point checklist (capital letters, full stops, spelling, paragraphs, answers "
           "the question) and hand it in.", 10),
}
_LOOK_FOR = {
    "content": "paragraphs that each make one point and back it with a specific example",
    "language": "fewer basic slips with capital letters, apostrophes and commonly confused words",
    "structure": "a clear introduction, paragraphs in a sensible order and a conclusion",
}


def _quote(text, slip=False):
    """A short phrase lifted word for word from the essay: with slip, one that shows a language slip if there is one."""
    lines = [s.strip() for line in text.splitlines() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    if slip:
        hit = next((s for s in lines if re.search(r"\bi\b", s) or re.search(MISSPELT, s, re.I)), None)
        if hit:
            return " ".join(hit.split()[:10])
    after_heading = next((s for s in lines[1:] if len(s.split()) >= 4), text)
    return " ".join(after_heading.split()[:8])


def _step(o, bank, have_essay=True):
    known = bank.get(o["id"])
    if not known:
        on = "one paragraph of the essay, rewritten" if have_essay else "one new paragraph on the essay topic"
        known = (f"Practise this outcome on {on}, and bring the paragraph to class: {o['text']}", 20)
    return {"outcome": o["id"], "activity": known[0], "minutes": known[1]}


def _three(picks, outcomes):
    """Exactly three outcomes for a plan: the ones picked, topped up from the rest of the list."""
    picks = picks + [o for o in outcomes if o not in picks]
    return [picks[i % len(picks)] for i in range(3)]


def _catch_up(c, outcomes, rubric):
    """A catch-up plan for one learner, from what the heuristics can measure in the essay and the marks."""
    first, text, scores = c["first_name"], c["text"], c["scores"]
    f = _facts(text, tools.topic_terms(rubric))
    if not scores:  # nothing could be marked: the first job is a complete draft
        handed_in = f"only {f['words']} words" if f["words"] else "nothing"
        before = re.search(r"\d", c["previous"])
        return {
            "id": c["id"],
            "why": (f"{first} handed in {handed_in}, so there is no evidence yet of what {first} can do on this task. "
                    "The gap may be about time or confidence more than skill, which is worth a quiet conversation."),
            "evidence": _quote(text) if f["words"] else "",
            "strength": f"The last essay earned {c['previous']}, so {first} has done this kind of work before." if before else "",
            "steps": [_step(o, _FRESH, have_essay=False) for o in _three([o for o in outcomes if o["id"] in _FRESH], outcomes)],
            "check": f"A complete draft from {first}, however rough, that can be marked against the rubric.",
        }

    order = sorted(scores, key=lambda s: s["score"] / s["max"])  # weakest first; ties stay in rubric order
    weak, best = order[0], order[-1]
    off_topic = weak["id"] == "content" and f["on_topic"] < 0.5
    if off_topic:
        why = (f"{first} wrote about something other than the topic that was set, so the writing could not earn "
               "content marks however well it was told.")
        want = r"on the topic"
    elif weak["id"] == "content" and f["words"] < 180:
        why = (f"{first}'s ideas are relevant but stop early: {f['words']} words in {f['paras']} paragraphs leaves each "
               "point stated, not developed with an example.")
        want = r"paragraph|example"
    elif weak["id"] == "content":
        why = f"{first}'s points are relevant but stay general, with few specific examples to develop them."
        want = r"paragraph|example"
    elif weak["id"] == "language":
        why = (f"{first} has things to say, but {f['slips']} basic slips with capital letters, spelling and apostrophes "
               "pull the language mark down and make the writing look weaker than it is.")
        want = r"grammar|spelling|proofread"
    elif weak["id"] == "structure":
        why = (f"{first}'s ideas are there, but they are not grouped into an introduction, ordered paragraphs and a "
               "conclusion, so the argument is hard to follow.")
        want = r"introduction|paragraph"
    else:
        why = (f"{first}'s lowest area is {weak['name'].lower()} at {weak['score']}/{weak['max']}; the other parts of "
               "the rubric are holding up better.")
        want = None
    fell = next((s for s in c["signs"] if s.startswith("Down ")), None)
    if fell:
        why += f" The mark is {fell[0].lower()}{fell[1:]}, so this is a recent slide and worth catching early."

    def serving(criterion, matching=None):
        found = [o for o in outcomes if criterion in o["criteria"]]
        return sorted(found, key=lambda o: not (matching and re.search(matching, o["text"], re.I)))

    picks = serving(weak["id"], want)[:2]  # two steps on the weakest area, then one on the next weakest
    for s in order[1:]:
        picks += [o for o in serving(s["id"]) if o not in picks][:1]
    look = "an opening sentence that answers the question that was set" if off_topic else \
        _LOOK_FOR.get(weak["id"], f"progress in {weak['name'].lower()}")
    return {
        "id": c["id"],
        "why": why,
        "evidence": _quote(text, slip=weak["id"] == "language"),
        "strength": (f"{best['name']} is {first}'s strongest area at {best['score']}/{best['max']}, so the plan starts "
                     "from something that already works."),
        "steps": [_step(o, _ACTIVITY) for o in _three(picks, outcomes)],
        "check": f"Ask {first} for the reworked essay, and look first for {look}.",
    }


# ---- the Designer: the next lesson ---------------------------------------------------------------

TOPIC = "'Technology has done more good than harm for young South Africans'"
# The exercise bank below is written for the sample class's topic (and the PC practical). For any other task the
# mock builds its exercises from the outcome's own words instead, so a teacher's own class never gets this topic.


def _fits(outcome_id, task=""):
    """Whether the banked text was written for the task that was set (the PC practical's always is)."""
    return outcome_id.startswith("H") or not task or TOPIC.strip("'").lower() in task.lower()


def _bank(outcome_id, level, task=""):
    """A banked (task, model answer) for an outcome, only if the bank was written for the task that was set."""
    return _EXERCISES.get(outcome_id, {}).get(level) if _fits(outcome_id, task) else None
# Exercises the mock Designer can set, by the outcome each practises and its level: (task, model answer).
_EXERCISES = {
    "W1": {
        "support": (
            f"A learner brainstormed six ideas for the essay {TOPIC}: (a) learning from online videos, (b) how to bake "
            "bread, (c) keeping in touch with family far away, (d) cyberbullying, (e) what I ate yesterday, "
            "(f) applying for jobs and bursaries online. Cross out the two ideas that do not belong in this essay and say why.",
            "Cross out (b) and (e). Neither is about what technology has done for young people, so they would take the "
            "essay off the topic. The other four are all relevant."),
        "core": (
            f"You have ten minutes to plan the essay {TOPIC}. Brainstorm at least six ideas, choose the four most "
            "relevant, and number them in the order you would write about them. Next to each number, write one word "
            "that says why it goes there.",
            "Any plan with four relevant ideas in a deliberate order. For example: 1 learning online (strongest first), "
            "2 staying in touch with family, 3 cyberbullying (the other side), 4 jobs and bursaries (ends on the future)."),
    },
    "W2": {
        "core": (
            "This paragraph has a main idea but no development: 'Technology helps us learn. There are videos and "
            "websites. It is good.' Rewrite it in three or four sentences: keep the one main idea, open with a topic "
            "sentence, and add one specific example from real life that proves the point.",
            "For example: 'Technology has made it easier for young South Africans to learn outside the classroom. When "
            "I could not follow equations in class, I watched a free ten-minute video twice and finally understood the "
            "method. Without a phone and data I would have waited a week to ask my teacher.' Look for one idea, a topic "
            "sentence and a specific example."),
        "extension": (
            "Write one paragraph of five or six sentences arguing that technology has harmed young South Africans in "
            "one specific way. Open with a topic sentence, develop the idea with a specific example and a precise "
            "detail such as a number, a place or a time, and end by saying why the example matters.",
            "Look for a single main idea stated in the first sentence, a concrete example and not a general claim, at "
            "least one precise detail, and a closing sentence that ties the example back to the idea. For example, a "
            "paragraph on learners who are on their phones past midnight and fall asleep in the first period."),
    },
    "W4": {
        "support": (
            "These are the opening sentences of the five paragraphs of an essay, in the wrong order. Number them 1 to 5 "
            "so that the essay has an introduction, three ordered points and a conclusion. (a) 'In conclusion, the good "
            "that technology does is greater than the harm.' (b) 'Secondly, technology keeps families in touch across "
            "long distances.' (c) 'Technology has changed the lives of young South Africans, mostly for the better.' "
            "(d) 'However, technology also causes harm, such as cyberbullying.' (e) 'Firstly, technology helps learners to study.'",
            "c, e, b, d, a. (c) introduces the topic and takes a position, (e) and (b) give the points in favour, "
            "(d) gives the other side, and (a) concludes."),
        "core": (
            f"Write only the skeleton of an essay on {TOPIC}: one sentence for the introduction that states your "
            "position, the first sentence of each of three body paragraphs in a logical order, and one sentence for the conclusion.",
            "Five sentences: an introduction that takes a position, three body openers that each announce a different "
            "point in a sensible order, and a conclusion that returns to the position without repeating the introduction."),
    },
    "W5": {
        "core": (
            "Fill each gap with one connecting word or phrase from this list, using each once: however, for example, "
            "as a result, in addition. 'Technology helps learners to study. ____, a learner can watch a video on a "
            "lesson she missed. ____, phones keep families in touch. ____, some learners stay online all night. ____, "
            "they are tired at school the next day.'",
            "For example; In addition; However; As a result."),
        "extension": (
            "Rewrite these four sentences as one flowing paragraph, joining them with connecting words and phrases of "
            "your own choice. You may combine sentences, but keep all four ideas. 'Phones are useful for homework. "
            "Phones distract learners in class. Some schools ban phones. Learners need to manage their own time.'",
            "For example: 'Although phones are useful for homework, they also distract learners in class. For this "
            "reason, some schools ban them. However, a ban does not teach self-control, so learners still need to "
            "manage their own time.' Look for at least three different connectives, used correctly."),
    },
    "W6": {
        "support": (
            "Correct every mistake in capital letters, spelling and subject-verb agreement in these two sentences. "
            "'i think phones is usefull for school becuase you can look things up. my sister use her phone to study in durban.'",
            "'I think phones are useful for school because you can look things up. My sister uses her phone to study in "
            "Durban.' Seven corrections: I, are, useful, because, My, uses, Durban."),
        "core": (
            "Choose the correct word in each pair. (1) Technology has done more good (then / than) harm. (2) Learners "
            "leave (their / there) phones at home. (3) Each of the learners (has / have) a tablet. (4) The internet and "
            "television (is / are) sources of news. Then write one correct sentence of your own that names a town.",
            "(1) than (2) their (3) has (4) are. Own sentence: any correct sentence with a capital letter for the town, "
            "such as 'My cousin studies in Polokwane.'"),
    },
    "W7": {
        "core": (
            "Rewrite each sentence in a formal tone that suits an essay, keeping its meaning. (1) 'Kids these days are "
            "glued to their phones.' (2) 'The internet is super cool for homework and stuff.' (3) 'Cyberbullying is really, really bad.'",
            "For example: (1) 'Many young people spend a great deal of time on their phones.' (2) 'The internet is a "
            "valuable resource for schoolwork.' (3) 'Cyberbullying causes serious harm.' Look for no slang, no vague "
            "words such as 'stuff', and no repetition for emphasis."),
        "extension": (
            "Write three formal sentences that argue for or against banning phones in schools. Do not use contractions, "
            "slang, or the words 'good', 'bad', 'nice' and 'thing'. Underline the two most precise words you chose.",
            "A formal register throughout, no contractions or slang, none of the four banned words, and precise "
            "vocabulary such as 'distraction', 'concentration' or 'responsibility'. For example: 'Phones are a constant "
            "distraction in the classroom.'"),
    },
}
# A plain exercise for an outcome the bank does not cover (your own outcomes.json, for example).
_TEMPLATES = {
    "support": lambda text: (
        f"Read this learning outcome: '{text}' Find one sentence or paragraph in your own essay that does not show it "
        "yet, copy it out, and underline the part you would change.",
        "Any passage from the learner's own essay with a sensible part underlined. Accept it if the learner can say what is missing."),
    "core": lambda text: (
        f"Rewrite one paragraph of your own essay so that it clearly shows this learning outcome: '{text}' Then write "
        "one sentence that says what you changed.",
        "A rewritten paragraph in which the outcome can be pointed to, and a sentence naming the change."),
    "extension": lambda text: (
        f"Write a new paragraph of six sentences on the essay topic that a marker could use as a model of this "
        f"learning outcome: '{text}' Swap with a partner and check each other's paragraph against it.",
        "A paragraph that shows the outcome throughout, and a partner's comment that refers to the outcome."),
}
_LESSONS = {  # by the first outcome a lesson targets: (title, exit ticket)
    "W1": ("Plan it, then prove it: from a list of ideas to a paragraph that makes its point",
           "Write the topic sentence of a paragraph you could add to your own essay, and the example you would use to prove it."),
    "W4": ("Building the frame: introduction, ordered points, conclusion",
           "In one sentence each, say what an introduction, a body paragraph and a conclusion are for."),
    "W6": ("Getting it right: accurate sentences in a formal voice",
           "Write one formal sentence about how you use technology, with no language errors, and circle its verb."),
}
_BY_TASK = {task: (outcome, answer) for outcome, levels in _EXERCISES.items() for task, answer in levels.values()}


# ---- the PC assembly practical ----------------------------------------------------------------------

def _log_facts(text):
    """What the mock can read off an attempt log: the summary lines the log always starts with."""
    num = lambda pattern: int(m.group(1)) if (m := re.search(pattern, text)) else 0
    return {"installed": num(r"Installed: (\d+) of"), "parts": num(r"of (\d+) parts") or 6,
            "wrong": num(r"\((\d+) parts? tried out of order"), "slot_misses": num(r"(\d+) dropped outside"),
            "hints": num(r"Hints used: (\d+)"), "seconds": num(r"Time taken: (\d+) seconds"),
            "target": num(r"target of (\d+) seconds") or 240, "finished": "Finished: yes" in text}


def _log_line(text, wrong=False):
    """A step of the log, word for word: a wrong placement when asked and there is one, otherwise a right one."""
    steps = re.findall(r"^\d+\. ((?:Right|Wrong): [^.]+)\.", text, re.M)
    pick = next((s for s in steps if s.startswith("Wrong")), None) if wrong else None
    return pick or next((s for s in steps if s.startswith("Right")), steps[0] if steps else text[:40])


def _practical_score(text, rubric):
    """Marks for one attempt, following the bands, and never above what the log allows."""
    f = _log_facts(text)
    lim = rubric.get("limits") or {}
    scores = {}
    for c in rubric["criteria"]:
        if c["id"] == "order":
            score = c["max"] - lim.get("order_penalty", 3) * f["wrong"]
            evidence = _log_line(text, wrong=f["wrong"] > 0)
            reason = f"{f['wrong']} part{'' if f['wrong'] == 1 else 's'} tried out of order."
        elif c["id"] == "correctness":
            score = round(c["max"] * f["installed"] / f["parts"]) - (1 if f["wrong"] + f["slot_misses"] else 0) - f["slot_misses"]
            evidence = _log_line(text)
            reason = f"{f['installed']} of {f['parts']} parts installed, {f['slot_misses']} dropped outside their slot."
        else:
            score = c["max"] - lim.get("hint_penalty", 2) * f["hints"] - (1 if f["seconds"] > f["target"] else 0)
            if f["seconds"] > f["target"] * lim.get("slow_factor", 2):
                score = min(score, round(c["max"] * lim.get("slow_cap_pct", 50) / 100) - 1)
            evidence = f"Hints used: {f['hints']}"
            reason = f"{f['hints']} hint{'' if f['hints'] == 1 else 's'}, {f['seconds']} seconds against a target of {f['target']}."
        scores[c["id"]] = {"score": max(0, min(c["max"], score)), "evidence": evidence, "reason": reason}
    return scores


# What a learner can do to catch up on each hardware outcome: (activity, minutes).
_HW_ACTIVITY = {
    "H1": ("Label a photo of an open PC: name the motherboard, CPU, RAM, GPU, SSD and power supply, and write one "
           "line on what each does.", 15),
    "H2": ("Write the six parts on cards, shuffle them and lay them out in installation order, saying aloud why each "
           "one has to wait for the one before it.", 10),
    "H3": ("In the virtual lab, install only the motherboard, CPU and RAM three times in a row without a wrong "
           "placement, then explain to a partner why the CPU goes in before the RAM.", 20),
    "H4": ("Match each expansion card and drive to its slot or bay on a motherboard diagram: the GPU to the long "
           "PCIe slot, the SSD to its bay.", 15),
    "H5": ("Practise the last step of the build: connect the power supply only after every other part is in, and "
           "tick a five-point safety checklist before switching on.", 15),
    "H6": ("Plan the build on paper first, with the six parts in order, then do the full assembly in the virtual lab "
           "against a timer of four minutes and without pressing Hint.", 20),
}
_HW_FRESH = {
    "H2": ("Before going back to the lab, write the six parts in installation order from memory and check the list "
           "with the teacher.", 10),
    "H3": ("Book a session in the virtual lab and install the motherboard, CPU and RAM with the parts list beside "
           "you.", 20),
    "H6": ("Do the whole PC assembly practical in the virtual lab, in one sitting, so that it can be marked.", 25),
}
_HW_LOOK_FOR = {
    "order": "a full build with no part tried before the part it sits on",
    "correctness": "every part installed in its slot first time, and the build finished",
    "efficiency": "a finished build in about four minutes with no hints",
}


def _catch_up_practical(c, outcomes):
    first, text, scores = c["first_name"], c["text"], c["scores"]
    if not scores:
        return {
            "id": c["id"],
            "why": (f"{first} has no attempt at the PC assembly practical on record, so there is no evidence yet of what "
                    f"{first} can do. It may be about time in the lab more than skill, which is worth checking."),
            "evidence": "", "strength": "",
            "steps": [{"outcome": o["id"], "activity": _HW_FRESH[o["id"]][0], "minutes": _HW_FRESH[o["id"]][1]}
                      for o in _three([o for o in outcomes if o["id"] in _HW_FRESH], outcomes)],
            "check": f"A complete attempt from {first} in the virtual lab that can be marked against the rubric.",
        }
    f = _log_facts(text)
    order = sorted(scores, key=lambda s: s["score"] / s["max"])
    weak, best = order[0], order[-1]
    why = {
        "order": f"{first} tried {f['wrong']} parts before the parts they depend on, so the build order is not secure yet.",
        "correctness": (f"{first} installed {f['installed']} of {f['parts']} parts" + ("" if f["finished"] else " and did not finish")
                        + ", so getting each part into the right slot needs practice."),
        "efficiency": (f"{first} used {f['hints']} hint{'' if f['hints'] == 1 else 's'} and took {f['seconds']} seconds against a "
                       f"target of {f['target']}, so the build is not yet done independently."),
    }.get(weak["id"], f"{first}'s lowest area is {weak['name'].lower()} at {weak['score']}/{weak['max']}.")
    serving = lambda cid: [o for o in outcomes if cid in o["criteria"]]
    picks = serving(weak["id"])[:2]
    for s in order[1:]:
        picks += [o for o in serving(s["id"]) if o not in picks][:1]
    steps = []
    for o in _three(picks, outcomes):
        activity, minutes = _HW_ACTIVITY.get(o["id"], (f"Practise this outcome in the virtual lab and show the teacher: {o['text']}", 15))
        steps.append({"outcome": o["id"], "activity": activity, "minutes": minutes})
    return {
        "id": c["id"], "why": why, "evidence": _log_line(text, wrong=weak["id"] == "order"),
        "strength": f"{best['name']} is {first}'s strongest area at {best['score']}/{best['max']}, so the plan starts from it.",
        "steps": steps,
        "check": f"Ask {first} to do the practical again, and look first for {_HW_LOOK_FOR.get(weak['id'], 'progress')}.",
    }


PARTS_LIST = "motherboard, CPU, RAM, GPU, SSD, power supply"
# Exercises for the hardware outcomes, by outcome and level: (task, model answer).
_EXERCISES.update({
    "H1": {
        "support": ("Match each part to its job: (a) CPU, (b) RAM, (c) SSD, (d) power supply. Jobs: (1) stores files "
                    "when the PC is off, (2) carries out instructions, (3) holds what is being worked on right now, "
                    "(4) turns mains power into what the parts need.", "a-2, b-3, c-1, d-4."),
        "core": ("Name the six parts of the PC you assembled and write one sentence each on what the part does: "
                 f"{PARTS_LIST}.", "Motherboard connects everything; CPU processes instructions; RAM holds working "
                 "data; GPU draws the picture on screen; SSD stores files; power supply powers the parts."),
    },
    "H2": {
        "support": (f"Put these parts in the order a technician installs them, and number them 1 to 6: {PARTS_LIST}.",
                    "1 motherboard, 2 CPU, 3 RAM, 4 GPU, 5 SSD, 6 power supply."),
        "core": ("A learner installed the graphics card before the CPU. Explain in two sentences why a technician puts "
                 "the CPU in first, and what could go wrong the other way round.",
                 "The CPU sits in a socket next to where the graphics card goes; with the card in, there is no room to "
                 "seat the CPU and its cooler safely. The learner would have to take the card out again, and could "
                 "bend the CPU's pins."),
        "extension": ("Write a six-step installation checklist for a new technician. For every step after the first, "
                      "say which earlier step it depends on and why.",
                      "Motherboard first; CPU needs the motherboard's socket; RAM sits beside the CPU; GPU needs the "
                      "PCIe slot clear of the CPU and RAM; SSD goes in its bay once the cards are in; power last, so "
                      "nothing is live while parts are fitted."),
    },
    "H3": {
        "support": ("Look at the motherboard diagram: point to the CPU socket and the RAM slots. Which goes in first, "
                    "the CPU or the RAM, and which way does the CPU's golden triangle face?",
                    "The CPU goes in first, with its golden triangle lined up with the triangle on the socket; the RAM "
                    "goes into the slots beside it afterwards."),
        "core": ("In the virtual lab, install the motherboard, CPU and RAM. Write down the order you used and one "
                 "thing you checked before pushing each part in.",
                 "Motherboard, CPU, RAM. Checks: the motherboard sits on its standoffs; the CPU's triangle matches the "
                 "socket; the RAM's notch matches the slot and the clips click."),
        "extension": ("A PC will not start after a build. The RAM clips are not closed and the CPU cooler is loose. "
                      "Explain in which order you would fix these and why.",
                      "Fix the CPU cooler first, since the CPU must be seated and cooled before anything is tested, "
                      "then reseat the RAM until both clips click, then try again."),
    },
    "H4": {
        "core": ("Say which slot or bay each part goes in: the graphics card, the SSD, and a second stick of RAM. Give "
                 "one sign that each is seated properly.",
                 "Graphics card: the long PCIe x16 slot, screwed to the bracket. SSD: its drive bay or M.2 slot, "
                 "screwed down. RAM: the matching DIMM slot, clips closed."),
    },
    "H5": {
        "core": ("Write a five-point checklist to go through after the power supply is connected and before the PC is "
                 "switched on for the first time.",
                 "All parts seated; every power cable connected; no loose screws in the case; the cooler fitted; the "
                 "power switch on the supply set correctly."),
    },
    "H6": {
        "support": ("Write the six parts in installation order on a card from memory. Then time yourself reading the "
                    "card aloud and touching each part in the virtual lab, without pressing Hint.",
                    f"The card reads {PARTS_LIST}. Accept any run that follows the card without a hint."),
        "core": ("Plan, then do: write your build plan in six lines, then complete the full assembly in the virtual "
                 "lab in under four minutes without a hint. Note your time.",
                 "A six-line plan in the right order and a finished build in under four minutes with no hints."),
    },
})
_BY_TASK.update({task: (outcome, answer) for outcome, levels in _EXERCISES.items() if outcome.startswith("H")
                 for task, answer in levels.values()})
_LESSONS.update({
    "H2": ("Why order matters: building a PC the way a technician does",
           "Write the six parts in installation order, and next to the GPU say what must already be in place."),
    "H3": ("Into the socket: seating the CPU and RAM",
           "Which goes in first, the CPU or the RAM, and what do you line up before pushing the CPU in?"),
})


def _practises(task, outcomes):
    """(outcome id, model answer or None) for a task the mock recognises. This is the whole of its judgement."""
    known = _BY_TASK.get(task)
    if known and any(o["id"] == known[0] for o in outcomes):
        return known
    named = next((o for o in outcomes if o["text"] in task), None)  # an exercise built from a template quotes its outcome
    return (named["id"], None) if named else None


def _attempt(e, outcomes):
    """The mock Reviewer's blind attempt at one exercise."""
    known = _practises(e["task"], outcomes)
    if not known:
        return {"id": e["id"], "answer": "", "outcome": "", "problem": "The task does not make clear which skill it practises."}
    return {"id": e["id"], "outcome": known[0], "problem": "",
            "answer": "Offline demo mode: the task was matched to its outcome by lookup, so no answer was written out."}


def _lesson(brief, outcomes):
    """A lesson on the class's weakest area: two outcomes, with a support and a core exercise on the first and a core and an extension on the second."""
    weakest, minutes = brief["weakest"], brief["minutes"]
    serving = [o for o in outcomes if weakest["id"] in o["criteria"]]
    chosen = (serving + [o for o in outcomes if o not in serving])[:2]
    a, b = chosen[0], chosen[-1]
    wanted = [(a, "support"), (a, "core"), (b, "core"), (b, "extension")] if a is not b else [(a, "support"), (a, "core"), (a, "extension")]
    exercises = []
    for n, (o, level) in enumerate(wanted, 1):
        task, answer = _bank(o["id"], level, brief.get("task", "")) or _TEMPLATES[level](o["text"])
        exercises.append({"id": f"X{n}", "outcome": o["id"], "level": level, "task": task, "answer": answer})
    ids = [e["id"] for e in exercises]
    work = brief.get("work", "essay")
    banked = _LESSONS.get(a["id"]) if _fits(a["id"], brief.get("task", "")) else None
    title, exit_ticket = banked or (
        f"Working on {weakest['name'].split(': ', 1)[-1].lower()}",
        f"Write down one thing you will do differently in your next {'essay' if work == 'essay' else 'test' if work == 'answer script' else 'practical'} "
        "because of today's lesson, and one question you still have.")
    behind = (f", and {brief['flagged']} learner{' was' if brief['flagged'] == 1 else 's were'} flagged as falling behind"
              if brief["flagged"] else "")
    lengths = [max(1, round(minutes * share)) for share in (0.1, 0.2, 0.3, 0.25)]
    lengths.append(minutes - sum(lengths))
    phases = [
        ("Starter", f"Show the class its own figures: {weakest['name'].lower()} averaged {weakest['pct']}%, the lowest part "
                    "of the rubric. Share today's outcomes.", "Note which outcome they find hardest, to come back to at the end."),
        ("Model it", "Model the skill on the board with a fresh example, thinking aloud at every step.",
         "Follow, then explain the method to a partner in their own words."),
        ("Guided practice", f"Set {' and '.join(ids[:2])}. Sit with the learners who are behind while they work on {ids[0]}, the support exercise.",
         "Work in pairs and agree on an answer before checking it."),
        ("Independent practice", f"Set {ids[2]}" + (f", and offer {ids[3]} as the extension to anyone who finishes early." if len(ids) > 3 else "."),
         "Work alone and in silence."),
        ("Check and close", "Go through the model answers, then collect the exit ticket from every learner on the way out.",
         "Mark their own work against the model answers and answer the exit ticket."),
    ]
    return {
        "title": title,
        "why": f"{weakest['name']} is the class's lowest area at {weakest['pct']}% across {brief['marked']} marked {work}s{behind}.",
        "outcomes": [o["id"] for o in chosen],
        "phases": [{"name": name, "minutes": length, "teacher": teacher, "learners": learners}
                   for (name, teacher, learners), length in zip(phases, lengths)],
        "exercises": exercises,
        "exit_ticket": exit_ticket,
    }


def _next_exercise_id(exercises):
    nums = []
    for exercise in exercises:
        match = re.fullmatch(r"X(\d+)", str(exercise.get("id") or ""))
        if match:
            nums.append(int(match.group(1)))
    return f"X{(max(nums) if nums else len(exercises)) + 1}"


def _align_lesson(d):
    """Add a support exercise for each diagnosed weakness the current lesson's support work misses."""
    lesson, outcomes = d["lesson"], d["outcomes"]
    chosen = list(lesson["outcomes"])
    phases = [dict(phase) for phase in lesson["phases"]]
    exercises = [{"id": e["id"], "outcome": e["outcome"], "level": e["level"], "task": e["task"], "answer": e["answer"]}
                 for e in lesson["exercises"]]
    for gap in d["missing"]:
        serving = [o for o in outcomes if gap["id"] in o["criteria"]]
        if not serving:
            continue
        pick = next((o for o in serving if o["id"] in chosen), serving[0])
        if pick["id"] not in chosen:
            if len(chosen) >= 3:  # the lesson may claim at most three outcomes; a fourth gap is left for the teacher
                continue
            chosen.append(pick["id"])
        if any(e["outcome"] == pick["id"] and e["level"] == "support" for e in exercises):
            continue
        task, answer = _bank(pick["id"], "support", d.get("task", "")) or _TEMPLATES["support"](pick["text"])
        exercises.append({"id": _next_exercise_id(exercises), "outcome": pick["id"], "level": "support", "task": task, "answer": answer})
    support_ids = [e["id"] for e in exercises if e["level"] == "support"]
    if len(support_ids) > 1:  # the phase script named only the original support exercise
        named = " and ".join(support_ids)
        for phase in phases:
            phase["teacher"] = phase["teacher"].replace(
                f"work on {support_ids[0]}, the support exercise", f"work on {named}, the support exercises")
    return {
        "title": lesson["title"], "why": lesson["why"], "outcomes": chosen, "phases": phases,
        "exercises": exercises, "exit_ticket": lesson.get("exit_ticket") or "",
    }


def _align_plans(d):
    """Point a step that maps to nothing at an outcome the lesson teaches, or else one on the list."""
    by_id = {o["id"]: o for o in d["outcomes"]}
    lesson_ids = [x for x in d.get("lesson_outcomes") or [] if x in by_id]
    exercise_ids = [x for x in d.get("exercise_outcomes") or [] if x in by_id]
    known = set(lesson_ids) | set(exercise_ids) | set(by_id)

    def choose(weakest):
        for outcome in lesson_ids + exercise_ids:
            if not weakest or weakest in by_id[outcome]["criteria"]:
                return outcome
        for outcome in d["outcomes"]:
            if not weakest or weakest in outcome["criteria"]:
                return outcome["id"]
        return (lesson_ids or exercise_ids or [d["outcomes"][0]["id"]])[0]

    plans = []
    for case in d["cases"]:
        plan = {k: case["plan"][k] for k in ("why", "evidence", "strength", "check")}
        steps = []
        for step in case["plan"]["steps"]:
            step = dict(step)
            if step.get("outcome") not in known:
                step["outcome"] = choose(case.get("weakest"))
                banked = _ACTIVITY.get(step["outcome"]) or _FRESH.get(step["outcome"])
                if banked:
                    step["activity"], step["minutes"] = banked
            steps.append(step)
        plan["steps"], plan["id"] = steps, case["id"]
        plans.append(plan)
    return {"plans": plans}


# ---- the Clerk: reading photographed pages ----------------------------------------------------------

_GOLDEN = {}


def _golden():
    """The sample pages' reads, by the SHA-256 of each photo (data/scripts/golden.json)."""
    path = Path(os.getenv("MOCK_GOLDEN") or Path(__file__).resolve().parent.parent / "data" / "scripts" / "golden.json")
    if path not in _GOLDEN:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pages": []}
        _GOLDEN[path] = {p["sha256"]: p for p in doc.get("pages", [])}
    return _GOLDEN[path]


def read_page(d):
    """The mock cannot see. It knows the sample pages by their hash and gives their recorded reads: the first
    on a first read, the last on a re-read. Any other photo comes back unread, with the reason why."""
    page = _golden().get(d.get("sha256"))
    if not page:
        return {"name": "", "page": None, "of": None, "lines": 0, "text": "", "confidence": 0,
                "problem": "Offline demo mode can only read the sample scripts. Add an API key to read your own photos."}
    reads = page["reads"]
    return dict(reads[min(max(1, int(d.get("attempt") or 1)), len(reads)) - 1])


def intake(d):
    goal, pages = d["goal"].lower(), d["pages"]
    leave_out = re.search(r"\b(ignore|skip|leave out|without|not|only)\b[^.]{0,30}\b(photo|script|handwrit|scan|paper|typed)", goal)
    if leave_out:
        return {"ingest": False, "reason": "The goal says to leave the photographed scripts out, so only the typed essays are marked."}
    return {"ingest": True, "reason": (f"{pages} photographed page{'' if pages == 1 else 's'} of handwritten work came with the goal, "
                                       "so the Clerk transcribes them before anything is marked.")}


def respond(task, d):
    if task == "intake":
        return intake(d)
    if task == "read_page":
        return read_page(d)
    if task == "plan":
        goal = d["goal"].lower()
        no_send = bool(re.search(r"(don'?t|do not|no|without)\s+(send|email|feedback)", goal))
        support = bool(re.search(r"falling behind|fall(ing|en)? behind|catch[- ]?up|struggl|at risk|support plan|needs? (extra )?(help|support)", goal))
        lesson = bool(re.search(r"lesson|exercise|worksheet", goal))
        length = re.search(r"(\d{2,3})[- ]?min", goal)
        minutes = int(length.group(1)) if length else 45
        exclude = [
            {"id": s["id"], "reason": "Submission is too short to mark fairly; ask the learner to resubmit."}
            for s in d["inventory"] if "too_short" in s["flags"]
        ]
        understanding = [f"Mark every {d.get('work', 'essay')} against the rubric and double-check the marks."]
        understanding.append("No messages to learners, as asked." if no_send else "Give each learner feedback.")
        steps = ([
            "Mark the transcribed handwritten scripts exactly like the typed essays",
        ] if any(s.get("source") == "script" for s in d["inventory"]) else []) + [
            "Check every submission and set aside any that cannot be marked",
            "Mark in batches against the rubric, quoting evidence",
            "Second-mark every essay blind and send disagreements back",
            "Skip feedback, as asked" if no_send else "Write and check personal feedback",
        ]
        if support:
            understanding.append("Find who is falling behind, work out why and plan their catch-up.")
            steps.append("Spot learners falling behind, diagnose why and write catch-up plans")
        if lesson:
            understanding.append(f"Draft a {minutes}-minute lesson for the weakest area, with exercises checked against the outcomes.")
            steps.append("Draft the next lesson and have every exercise tried blind")
        if support and lesson:
            understanding.append("Then check that the catch-up plans and the lesson agree.")
            steps.append("Check the catch-up plans against the lesson and send any mismatch back once")
        steps.append("Deliver the mark sheet and a class report" if no_send else "Deliver marks, messages and a class report")
        return {
            "understanding": " ".join(understanding),
            "batch_size": 4,
            "exclude": exclude,
            "deliver": {"feedback": not no_send, "csv": True, "report": True, "support": support, "lesson": lesson},
            "lesson_minutes": minutes,
            "steps": steps,
        }
    if task == "support":
        if d["rubric"].get("kind") == "test":
            return {"plans": [_catch_up_test(c, d["outcomes"], d["rubric"]) for c in d["cases"]]}
        if d["rubric"].get("kind") == "practical":
            return {"plans": [_catch_up_practical(c, d["outcomes"]) for c in d["cases"]]}
        return {"plans": [_catch_up(c, d["outcomes"], d["rubric"]) for c in d["cases"]]}
    if task == "lesson":
        return _lesson({**d["brief"], "work": d.get("work", "essay"), "task": d.get("task", "")}, d["outcomes"])
    if task == "try":
        return {"attempts": [_attempt(e, d["outcomes"]) for e in d["exercises"]]}
    if task == "fix_exercises":
        fixed = []  # the mock cannot write a new task; it can only put a known task's label and answer right
        for f in d["failing"]:
            known = _practises(f["task"], d["outcomes"])
            fixed.append({"id": f["id"], "level": f["level"], "task": f["task"],
                          "outcome": known[0] if known else f["outcome"], "answer": (known and known[1]) or f["answer"]})
        return {"exercises": fixed}
    if task == "align_lesson":
        return _align_lesson(d)
    if task == "align_support":
        return _align_plans(d)
    if task in ("mark", "review", "remark") and d["rubric"].get("kind") == "practical":
        return {"marks": [{"id": e["id"], "scores": _practical_score(e["text"], d["rubric"]), "response": "revised",
                           "note": "Re-read the attempt log against the band descriptors."} for e in d["essays"]]}
    if task in ("mark", "review", "remark") and d["rubric"].get("kind") == "test":
        return {"marks": [{"id": e["id"], "scores": _test_score(e["text"], d["rubric"]), "response": "revised",
                           "note": "Re-marked every part against the memo."} for e in d["essays"]]}
    if task in ("mark", "review"):
        return {"marks": [
            {"id": e["id"], "scores": _score(e["text"], d["rubric"], nudge=(sum(map(ord, e["id"])) % 3 - 1) if task == "review" else 0)}
            for e in d["essays"]
        ]}
    if task == "remark":
        out = []
        for e in d["essays"]:
            scores = _score(e["text"], d["rubric"])
            out.append({"id": e["id"], "scores": scores, "response": "revised",
                        "note": "Re-read the essay against the band descriptors and the Reviewer's objections."})
        return {"marks": out}
    if task == "verify":
        return {"verdicts": [{"id": e["id"], "approve": True, "reason": "The revised mark fits the rubric."} for e in d["essays"]]}
    if task == "feedback":
        msgs = []
        for it in d["items"]:
            best = max(it["scores"], key=lambda s: s["score"] / s["max"])
            weak = min(it["scores"], key=lambda s: s["score"] / s["max"])
            work = d.get("work", "essay")
            practical, test = work == "practical attempt", work == "answer script"
            if practical:
                advice = "Say the build order aloud before you start, and check each slot before you let go of a part."
                step = "do the build once more in the virtual lab without a hint and note your time."
            elif test:
                advice = "Write out every step of your working, and check each answer against the question before you move on."
                step = f"redo the {_topic(weak['name']).lower()} questions with the memo, then try them again without it."
            else:
                advice = "Plan one clear idea per paragraph and proofread aloud before you hand in."
                step = "rewrite your weakest paragraph using this advice and bring it to class."
            body = (
                f"Hi {it['first_name']},\n\nThank you for your {'PC assembly practical' if practical else 'test' if test else 'essay'}. "
                f"You scored {it['total']}/{it['max']}.\n\n"
                f"What worked: your strongest area was {best['name'].lower()} ({best['score']}/{best['max']}). "
                f"I noticed this line in particular: \"{best['evidence']}\".\n\n"
                f"To improve: focus on {weak['name'].lower()} ({weak['score']}/{weak['max']}). "
                f"{advice}\n\nNext step: {step}\n\nKeep going!"
            )
            noun = "practical" if practical else "test" if test else "essay"
            msgs.append({"id": it["id"], "subject": f"Your {noun} feedback: {it['total']}/{it['max']}", "body": body})
        return {"messages": msgs}
    if task == "report":
        rows = d["rows"]
        weakest = min(d["criteria_avg"], key=lambda c: c["avg_pct"]) if d["criteria_avg"] else None
        return {
            "summary": f"{len(rows)} {d.get('work', 'essay')}s marked. Class average {d['average']}/{d['max']}.",
            "strengths": ["Most learners finish the build with every part in its slot." if d.get("work", "essay") == "practical attempt"
                          else "Most learners attempt every question and show their working." if d.get("work") == "answer script"
                          else "Most learners take a clear position on the topic."],
            "gaps": [f"Weakest area across the class: {weakest['name']} ({weakest['avg_pct']}%)."] if weakest else [],
            "next_lesson": [f"Spend the next lesson on {weakest['name'].lower()}, using two anonymised class examples."] if weakest else [],
        }
    raise ValueError(f"Mock has no reply for task '{task}'")
