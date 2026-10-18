# First-use workflow

[Planning index](index.md)

Status: topic recorded for later review. No setup behavior approved or implemented.

## Goal

Define how a researcher goes from installing the bib-lint agent skill to inspecting a bibliography audit report without guessing the next step. Use this as the first concrete workflow before generalizing to other tools.

## Proposed journey

1. The researcher installs the agent skill.
2. They ask their agent to check a bibliography.
3. The agent checks for the required tool and runtime dependencies.
4. The tool is set up according to an agreed installation policy.
5. The agent runs the audit on the selected bibliography.
6. The researcher receives a concise explanation and can inspect the report and source evidence.

## Questions for review

- How is the underlying tool installed and versioned?
- How does the skill detect an existing installation and missing dependencies?
- What setup and execution may happen automatically, and what needs user input?
- How does the agent identify the bibliography and choose an output location?
- How are external scholarly lookups explained?
- How are findings, incomplete coverage, and source errors presented?
- How does the researcher open the report and inspect evidence?
- What does a successful first use look like, and how will we test it?

## Dependencies

- [Skill installation](skill-installation.md)
- [Repository and distribution](repository.md)
- [Tool and skill pages](tool-pages.md)

## Decisions and implementation

Pending discussion and review. This document records a proposed journey, not an implemented feature or approved automation policy.

## Approved setup and page refinements

The intended interface includes `/sciskill init`: check required tools, install missing dependencies, and reuse existing installations. A compact copyable setup step follows the centered installation command and precedes the two action sections. Backend dependency handling remains to implement before publication.

## Agreed execution model

Use uvx for every underlying tool. Do not require a clone plus uv sync or installation into the user project environment. Init should check uv availability and prepare or verify required tool versions through uvx. Exact setup policy remains to define.
