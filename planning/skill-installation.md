# Skill installation

[Planning index](index.md)

Status: discussion draft; do not implement before review.

## Agreed requirement

Make Science Skillset skills installable through the skills.sh ecosystem, with installation instructions surfaced on the website.

## Verified mechanism

The open-source skills CLI can install skills directly from a GitHub repository. It discovers directories such as skills/<name>/ containing SKILL.md with name and description frontmatter. It supports selecting a particular skill and project-local or global installation.

Sources:
- https://www.skills.sh/docs
- https://github.com/vercel-labs/skills

## Proposed implementation

- Store public, reusable skills under skills/<skill-name>/SKILL.md in the collection repository, with supporting resources beside each skill.
- Use the existing skills CLI rather than building a custom installer.
- Show collection-level and individual-skill installation commands on the website after testing them.
- Document tool runtime dependencies separately: installing agent instructions is not the same as installing the underlying Python tool.
- Test discovery and installation in a temporary project, then verify the installed skill works with its required tool.
- Decide directory listing/discoverability separately from repository installation; do not claim a skills.sh listing before verifying it.

## Illustrative commands — not available yet

The repository and skill names below are proposals, not released endpoints.

```sh
npx skills add Am1n3e/science-skills
npx skills add Am1n3e/science-skills --skill bib-lint
```

## Open decisions

- Final public source repository and skill names.
- Which skills are ready for the first release.
- Supported agents and tested compatibility.
- How each skill obtains and checks its underlying tool dependencies.
- Project-local installation as the documented default, and whether to show global installation as an alternative.

## Implementation and validation

Pending review. No skills installed, created, or published during this discussion.

## Homepage preview approved and applied

The homepage shows the proposed collection command `npx skills add Am1n3e/science-skills` in a centered block with a copy button and “Planned installation · not released yet.” This is a presentation change only; repository creation, CLI installation testing, and release remain pending.
