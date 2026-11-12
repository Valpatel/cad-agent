**Fixed**
- Reader-boundary browser navigation failures now retain bounded partial state and a viewport screenshot before page close; the original wait, timeout, thrown error and acceptance predicates remain unchanged. This improves diagnosis, not the unresolved navigation failure's cause (#625).
