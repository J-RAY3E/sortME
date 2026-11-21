# Skill: relationship graph

A `pre` edge means a REAL dependency: the reader needs the prerequisite to
understand the target. A `rel` edge only means topically close material.

Rules for `pre` (max two):
- Only add it when the target builds on concepts introduced by the prerequisite.
- Tutorials and explainers are prerequisites for papers, not the other way round.
- Never create a self-loop, and never point to an index outside the catalog.

Rules for `rel` (max two):
- Use it for alternative implementations, follow-up work or the same idea in a
  different domain.
- Do not duplicate a `pre` edge as a `rel` edge.
- It is better to return fewer edges than to invent weak connections.

The final list must contain one entry for EVERY index in the catalog.
