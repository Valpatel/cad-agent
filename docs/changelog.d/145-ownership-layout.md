**Changed**
- The canonical agent-kit assets live under `.agents/skills/` and `.agents/agents/`, with a native manifest retaining the repository as plugin root. The Python package and pinned third-party source share `software/`; release fragments live under `docs/changelog.d/`. The root shrinks from17 entries to14. Current published identities and installed destinations remain stable (#145, #111).

**Projects must change**
- Maintainer references to the kit's source assets use `.agents/skills/` and `.agents/agents/`; the old root directories are moved. Source imports use `software/cadagent/`, third-party tooling uses `software/vendor/`, and new release fragments use `docs/changelog.d/`; installed Python modules and CLI names stay the same. Follow the existing installer to repair its owned links; other authors' files remain protected (#145).
