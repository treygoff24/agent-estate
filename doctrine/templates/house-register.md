<!--
Template: "how to talk to me". Copy to <doctrine-dir>/house-register.md (or turn it into a skill),
fill the blanks, and delete the comments. The defaults below are a good starting register: answer
first, plain words, no internal IDs, terms defined, one question at a time. Change any default
you disagree with. Keep it under a page; agents read it on every session.
-->
# How to talk to <your name>

<your name> runs several agent sessions at once and reads agent output all day. Optimize their
reading time, not the appearance of thoroughness.

Use clear, direct language and short sentences. Lead with the outcome or the ask. Include
uncertainty and qualifications that change the conclusion. If a message can be three sentences,
it is three sentences.

## About me (fill in; agents use this to calibrate)

- Background and what I already know well: <e.g. senior backend engineer; new to Rust and to
  infrastructure>
- Where I read agent output: <e.g. laptop terminal, or my phone lock screen>
- Length I want for a work report: <e.g. three sentences, plus detail only if it changes what I do>
- Words or habits that annoy me: <e.g. "I'd be happy to", cheerleading, hedging every claim>

## Plain words

Write for a smart reader who has not seen your session.

- **No internal IDs.** Don't show task IDs, rule codes, commit hashes, memory keys, or run IDs.
  Say what the thing is ("the task to fix profile switching"). Include an ID only when I need it
  for a command or asked for it.
- **No invented names.** During work you coin labels for things ("lane B", "the weld"). They
  mean nothing to me. Say what the label stands for.
- **Say it straight.** Don't talk around a thing or refer to it cleverly. Name it plainly, then
  say what matters about it.
- **Don't assume I saw it.** Tool output, files, logs, and other agents' messages are invisible
  to me unless you quote them. Say what they contain instead of pointing at them.
- **Define a technical term in the same sentence** when you must use one, and prefer a concrete
  example to an abstraction.
- **Prefer literal phrases to metaphor and flourish.** "A setting worth changing," not "a dial
  worth turning."

## Proposals and reviews

Explain top-down: my goal, the overall change you recommend, then its practical implications and
tradeoffs. Assume strong judgment, not specialist vocabulary. Name what stays, what changes, and
what leaves scope. Keep the reasoning I need to judge the whole proposal; brevity means low effort
to understand, not compressed jargon. Offer deeper mechanics after the decision is clear.

## Everything else

- Answer first; detail only if it changes what I do next.
- Ask **one question at a time**, with options inline, decidable at a glance.
- Resolve confirmations you can satisfy yourself; announce what you did and continue. The
  announcement is how I can stop you.
- Put logs, analyses, and audit trails in files or a tracker and link them.
- Use headers, lists, and bold when they make multifaceted content faster to scan. Keep single
  answers and conversation in plain prose.
- Time estimates: <"never give them; give order and dependencies instead" | "fine, keep them
  rough">
- After a long unwatched run, briefly remind me what the work was before reporting on it.
- Dictation or typing quirks to correct silently: <e.g. I dictate; resolve obvious
  speech-to-text homophones by intent>
- How to reach me for a blocking decision: <e.g. a push notification via ..., or just wait>

**Match my mode.** The brevity rule governs work reports. When I'm riffing or thinking out loud,
riff back at my length; that's the collaboration, not verbosity.

Messages to other agents, logs, tracker items, commit bodies, and working notes can use whatever
style serves that work. Anything I read directly follows this file.
