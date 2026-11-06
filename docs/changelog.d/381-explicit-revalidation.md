**Fixed**
- Stable website vendor assets explicitly require revalidation even if a downstream policy raises their freshness lifetime. Already cached responses still require separate public verification (#381).
