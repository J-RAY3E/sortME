# Skill: data hygiene

- Treat the title and URL as the only trustworthy facts. Do not invent authors,
  dates, venues or results.
- Keep source titles exactly as supplied, including their original language.
  ONLY the generated description must be in English.
- Ignore tracking parameters and session ids in URLs when reasoning about them.
- If two entries look like the same paper (for example an arXiv abs page and a
  PDF mirror), mark them as `rel`, not as `pre`.
- Duplicate URLs are removed by the importer before the model sees the catalog.
- Return strict JSON. A missing index breaks the graph, so include all of them.
