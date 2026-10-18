# v1 -> v2
1. Set "version" to 2.
2. Move db_host and db_port into an object "database": {"host": ..., "port": ...}.
3. "debug" becomes a boolean: "yes" -> true, anything else -> false.
4. "features" becomes a list of strings (split on commas).
5. Remove the old top-level keys.
