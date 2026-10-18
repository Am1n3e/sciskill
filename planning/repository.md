# Repository and distribution

[Planning index](index.md)

Status: to discuss; no implementation approved.

## Scope

Repository organization and distribution of tools and agent skills. No repository restructuring has been approved.

## Discussion topics

- Decide whether the collection is a catalog, a monorepo, or a combination.
- Decide where tool source and skill definitions live.
- Decide installation and versioning conventions.

## Agreed decisions

None recorded for this work group yet.

## Implementation and validation

To define after review.

## Related plan

[Skill installation](skill-installation.md) records the requested skills.sh compatibility.

## Agreed tool execution requirement

All collection tools must be runnable with uvx (uv tool run), using isolated tool environments rather than installing dependencies into the researcher’s project environment. Package each Python tool with appropriate console entry points. Apply this to the extracted Rebuttal Desk and bib-lint. Users need uv available; uvx manages tool dependencies and may cache environments. Final distribution names and pinned release versions remain to decide.
