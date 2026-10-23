---
name: writing
description: >-
  Draft, revise, review, or harden prose a person will read: email, memo, report, README, one-pager, blog post. A five-step method (frame, draft, check, review, hand over) with a lint script and sized review. Not for documents an agent consumes (skills, AGENTS.md, prompts for models): writing-for-agents.
metadata:
  version: 1.1.0
---

# Writing

One skill for every piece with a reader. Five steps, each ending where you can check it. The reference behind a step lives in this folder and loads only when the step names it.

## 1. Frame

Fill the brief before a word of draft.

**Reader and purpose.** One person, one job, what they know cold, what they will not know. Then one sentence: "this piece makes the reader ___."

**Genre.** The branch. Open `genres/<genre>.md` and take its defaults: length budget, register, ask rules, review floor. Genres on file: cold-email, follow-up-bump, internal-report, one-pager, readme. A piece with no file takes the nearest genre and says which. Add your own by copying a genre file and its frontmatter (`words`, `bold_leads`, `review`).

**Spine.** One line naming the path the reader walks. Leading words: design (how it is built and why), chronicle (what happened, in order), argument (claim, evidence, ask), ask, update, story, explainer, rebuttal, comparison. A builder's question ("how did you set it up?") gets a design spine; a chronicle answers a different question.

**Voice owner.** Whose name goes on the piece. If the owner has samples of their own writing, read them before drafting; `voice.md` says how to use them. With no samples, write in the house register `voice.md` describes.

**Hard constraints, apart from preferences.** Legal lines, confidentiality, and locked wording are constraints: they survive every revision verbatim. Tone, naming, length, and whether to ask are preferences: the owner can reverse them, so they sit on their own line.

**Skeleton.** When a person's name goes on the piece and they care about its shape, get their own skeleton first (their order, their emphasis, their sentences where they have them) before drafting. A ten-minute outline from the owner beats an hour of rewriting after.

Complete when every slot holds a value and the skeleton, where one is owed, is on disk.

## 2. Draft

Write from `voice.md` and the genre file, camera on the subject. Facts the owner asserts are ground truth: a fact stated without a source file is still a fact. The one inline flag is `[CHECK: ...]`, reserved for a contradiction with the public record or a legal line, and a draft carries at most three. A listing, pitch, or bio takes its topics from the author's stated premise and plans; one sample artifact (a single episode, one email) is an instance, so name it as one and never generalize its topics into the range. Live co-writing runs through `modes/` (explore, shape, beats).

Complete when the draft is on disk within the genre's budget, in the owner's voice, with every checkable fact traced to the brief or a source.

## 3. Check

Run `python3 <skill-dir>/lint.py --genre <genre> <file>` (`--to-owner` for anything addressed to the person who owns the work, `--internal` for internal documents) and fix every hit. Then the subtractive pass: at each sentence, "if I cut this, what does the reader lose?", and cut where the answer is nothing; in sourced writing, hold every number, name, date, source, and hedge. Then read it aloud in your head; a paragraph that sounds like a press release or a deck of index cards gets redrafted.

Complete when lint is clean and the read-aloud finds nothing.

## 4. Review, sized to the stakes

Judge the stakes on five heuristics: who can say no, how far it travels, whether it can be unsent, whose byline it carries, how new its claims are. State the call in one line ("stakes: a cold ask to a stranger with one new claim, so one cold read"); the owner can override it.

| Rung | Pieces | What runs |
| --- | --- | --- |
| lint | short note, bump, reply, scheduling note | step 3 only |
| cold read | external email with a new claim, blog post | one fresh-context audit per `review/cold-audit.md` |
| readers | brief, memo, one-pager going to a room | adversarial readers per `review/readers.md` |
| crucible | bet-the-outcome | decorrelated review loop per `review/crucible.md` |

Every reviewer brief carries the step-1 brief and the record the piece rests on, with owner-asserted facts declared ground truth in the reviewer's prompt. A reviewer reads the piece against its reader and its record; the pattern checklist stays with the cold auditor. Fold findings with `revision.md` (patch before rewrite, reframe before cut).

Complete when the chosen rung has run, each finding is applied or rejected with a reason, and every hard constraint from step 1 still reads verbatim.

## 5. Hand over

Save the draft as delivered: copy the file to `.delivered/<filename>` beside it, so the owner's edits have a "before" to diff against. Then hand over the file, state the stakes call, and name the one thing the owner decides.

When the owner pastes back an edited version or says what they changed, that pair is the best signal of their voice. Keep such pairs in a samples file the owner controls and read it in step 1 next time.

Complete when the snapshot exists and the file is handed over.

## Maintenance

Loading this skill injects only this file and its base directory; a session sees nothing else in the tree. A file exists to a session only when a sentence here, or in a file named here, points at it. A new genre, review, or sample file therefore lands with its pointer in the same edit, and a file nothing names gets deleted.
