**Fixed**
- Bambu slice rows preserve both process/result codes and explicit `ok`; grams cannot turn a failed command into a passing slice. Successful Bambu `Success.` text is retained without being treated as an error. Older report rows without `ok` keep their grams fallback (#534).
- A persisted stale, incomplete or unreadable slice report fails `check`, `report` and `all` with a reason and a request to slice again, instead of appearing as "slicer not run". A project with no report still passes the optional slicing check (#535).

**Projects must change**
- Projects retaining a slice report must slice again after changes to the sliced 3MFs or slicer settings before verification passes. `slicer_run` still means a current report; failed stale reports keep it false (#535).
