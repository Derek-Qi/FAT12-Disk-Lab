# Sources and notices

The FAT12 implementation and demo images in this repository are authored for this educational project. Runtime FAT operations do not use a third-party FAT engine.

- Format reference: Microsoft FAT Specification 1.03, available from the [PCjs document archive](https://www.pcjs.org/documents/papers/microsoft/MS_FAT_OVERVIEW_103-2000-12-06.pdf). The specification itself is not redistributed here.
- React, react-dom and scheduler are bundled in the compiled interface. Their original MIT licence notices are retained in `fat12lab/static/THIRD_PARTY_NOTICES.txt` and included in the wheel.
- Vite/TypeScript and browser tooling are development dependencies. `web/package-lock.json` records the exact frontend dependency resolution.
- PyFatFS is used only for optional independent interoperability checks, not for runtime filesystem operations. Its package is installed separately, not vendored into the public source.

AI tools assisted design, implementation, testing and documentation. Historical course materials and private working images are excluded from this public repository and its history.

No project-wide open-source licence has been selected. Public availability for technical review should not be described as a separate licence grant. Third-party components retain their own licences.
