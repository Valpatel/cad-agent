**Changed**
- The canonical agent-kit assets live under `.agents/skills/` and `.agents/agents/`, with a native manifest retaining the repository as plugin root. Current published identities and installed destinations remain stable (#145, #111).

**Projects must change**
- Maintainer references to the kit's source assets use `.agents/skills/` and `.agents/agents/`; the old root directories are removed. Follow the existing installer to repair its owned links; other authors' files remain protected (#145).
