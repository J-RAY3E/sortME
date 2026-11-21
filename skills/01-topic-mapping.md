# Skill: topic mapping

Map each source to the most SPECIFIC topics available in the supplied taxonomy.
Prefer "Transformers & Attention" over "General" when the title mentions
attention, even if the source is really about astrophysics.

Rules:
- Use exact topic names, never paraphrases.
- Maximum three topics per source (respect the configured limit).
- "General" is a last resort, only when nothing else fits.
- When a source spans two areas (for example retrieval + evaluation), include
  both instead of collapsing into one broad label.
- Never create topic names that are not in the taxonomy.
