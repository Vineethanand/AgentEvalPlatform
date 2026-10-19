# Skill: changelog-format (house format for release changelog entries)

When writing a changelog entry, use exactly this layout:

- First line: `## <version> (<YYYY-MM-DD>)`
- Then up to three sections, always in this order and each preceded by a blank line: `### Added`,
  `### Changed`, `### Fixed`. Leave out a section that has no items.
- `feat:` lines go under Added, `change:` lines under Changed, `fix:` lines under Fixed.
  Ignore `chore:` lines completely.
- One bullet per item: `- <text after the prefix, first letter capitalised> (#<PR number>)`, with no trailing period.
- Inside a section, order the bullets by PR number, lowest first.
