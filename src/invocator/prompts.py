from invocator.models import Category

SYSTEM_PROMPT = (
    "You are a documentation synthesist.\n"
    "\n"
    "Your job is to consolidate classified GitHub project signals (pull requests,"
    " issues, commits, review comments, and mined terms) into a single coherent"
    " markdown file that a future engineer can read to absorb the project's"
    " accumulated wisdom.\n"
    "\n"
    "Output rules — non-negotiable:\n"
    '- Output ONLY markdown. No preamble (no "Here is the synthesis...").'
    " No postscript. No XML tags. No code fences wrapping the whole document.\n"
    "- Cite every claim with the source refs provided in the corpus, in the form"
    " `PR#12`, `issue#34`, or `commit:abc1234`. When multiple sources support the"
    " same claim, list them comma-separated:"
    " `(sources: PR#12, PR#88, commit:abc1234)`.\n"
    "- Deduplicate near-identical entries. If two items describe the same rule,"
    " pattern, or decision, merge them into one entry whose sources list contains"
    " both refs.\n"
    "- Preserve information density. Do not pad with filler sentences. Prefer"
    " crisp, declarative bullets over flowing prose.\n"
    "- Group related entries under H2 (`##`) topical sections. Within a section"
    " use H3 (`###`) or bullets per the per-category instructions.\n"
    "- If the corpus is sparse on a category, write a short file — do not invent"
    " content. An empty section is better than fabricated guidance.\n"
    "- Never expose raw GitHub user logins, internal URLs, or PII. Refer only to"
    " the source refs given.\n"
)

RULES_INSTRUCTION = (
    "Write `rules.md`.\n"
    "\n"
    "Structure:\n"
    "- Start with a single H1 title: `# Rules`.\n"
    "- Group rules under H2 (`##`) sections by topic (e.g. `## API design`,"
    " `## Error handling`, `## Testing`, `## Style & conventions`). Pick topical"
    " headings that emerge from the corpus — do not force the example list.\n"
    "- Under each H2, list rules as bullets in this exact shape:\n"
    "  `- **Rule:** <imperative statement>. _(sources: PR#12, PR#88)_`\n"
    '- Imperative voice: "Always validate inputs at the boundary." not'
    ' "We try to validate inputs."\n'
    "- One rule per bullet. If two corpus items state the same rule with"
    " different wording, merge them and list both sources.\n"
    "- Skip items whose signal is purely a bug pattern with no actionable rule —"
    " those belong in `prevencoes.md`.\n"
)

PREVENCOES_INSTRUCTION = (
    "Write `prevencoes.md` — a catalog of bug patterns and how to avoid them.\n"
    "\n"
    "Structure:\n"
    "- Start with a single H1 title: `# Prevenções`.\n"
    "- One H3 (`###`) per distinct bug pattern. Title the section with the"
    " pattern name (e.g. `### Race condition on cache write`).\n"
    "- Under each H3, write exactly these three labeled lines:\n"
    "  - `**Symptom:** <observable failure mode>`\n"
    "  - `**Root cause:** <why it happens>`\n"
    "  - `**Prevention:** <what to do instead>`\n"
    "  - `_(sources: PR#12, commit:abc1234)_`\n"
    "- Merge near-duplicate patterns into a single H3 with combined sources.\n"
    "- Group related patterns under H2 (`##`) sections only if there is a clear"
    " cluster (e.g. `## Concurrency`, `## Data integrity`). Otherwise flat H3"
    " list is fine.\n"
)

PATTERNS_INSTRUCTION = (
    "Write `patterns.md` — reusable patterns adopted in this project.\n"
    "\n"
    "Structure:\n"
    "- Start with a single H1 title: `# Patterns`.\n"
    "- One H3 (`###`) per pattern. Title with the pattern name"
    " (e.g. `### Result[T] for expected errors`).\n"
    "- Under each H3, write exactly these three labeled lines:\n"
    "  - `**When:** <situation in which the pattern applies>`\n"
    "  - `**How:** <concise description of the pattern>`\n"
    "  - `**Examples:** <one or two source refs that demonstrate it>`\n"
    "  - `_(sources: PR#12, PR#88)_`\n"
    "- Patterns are deliberate, reusable solutions — not one-off code changes."
    " Skip refactors that are purely cosmetic.\n"
    "- Group under H2 if a clear cluster emerges"
    " (e.g. `## Error handling`, `## Caching`).\n"
)

DECISIONS_INSTRUCTION = (
    "Write `decisions.md` — an ADR-lite log of architectural decisions.\n"
    "\n"
    "Structure:\n"
    "- Start with a single H1 title: `# Decisions`.\n"
    "- One H3 (`###`) per decision, dated, in this exact shape:\n"
    "  `### YYYY-MM-DD — <short title>`\n"
    "- Under each H3, write exactly these three labeled lines:\n"
    "  - `**Context:** <what forced the decision>`\n"
    "  - `**Decision:** <what was chosen>`\n"
    "  - `**Consequences:** <trade-offs accepted>`\n"
    "  - `_(sources: PR#12, issue#7)_`\n"
    "- Order entries newest-first.\n"
    "- If a source ref does not carry a date, omit the date prefix"
    " (write `### <title>` instead).\n"
)

GLOSSARY_INSTRUCTION = (
    "Write `glossary.md` — a project-specific terminology reference.\n"
    "\n"
    "Structure:\n"
    "- Start with a single H1 title: `# Glossary`.\n"
    "- One bullet per term, alphabetized case-insensitively, in this exact"
    " shape:\n"
    "  `- **Term** — <one-sentence definition>. _(sources: PR#12, issue#7)_`\n"
    "- Terms include domain nouns, internal jargon, and backticked identifiers"
    " that appear repeatedly in the corpus.\n"
    "- If a term has no clear definition in the corpus, skip it rather than"
    " inventing one.\n"
    "- Do not include H2 sections; a flat alphabetized bullet list is the"
    " contract.\n"
)

INDEX_INSTRUCTION = (
    "Write `INDEX.md` — a one-page overview of the synthesized learnings.\n"
    "\n"
    "Structure:\n"
    "- H1 title with the repo name.\n"
    "- One short paragraph: when synthesized, total classified items, model"
    " used.\n"
    "- An `## Files` H2 with one bullet per generated file (`rules.md`,"
    " `prevencoes.md`, `patterns.md`, `decisions.md`, `glossary.md`), each with"
    " an item count and a one-line description.\n"
    "- A `## Run` H2 with bullets: repo slug, model, total cost,"
    " cached-vs-synthesized split.\n"
)

CATEGORY_TO_INSTRUCTION: dict[Category, str] = {
    Category.RULES: RULES_INSTRUCTION,
    Category.PREVENCOES: PREVENCOES_INSTRUCTION,
    Category.PATTERNS: PATTERNS_INSTRUCTION,
    Category.DECISIONS: DECISIONS_INSTRUCTION,
    Category.GLOSSARY: GLOSSARY_INSTRUCTION,
}
