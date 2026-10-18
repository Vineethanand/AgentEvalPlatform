# Postmortem: API outage
## Summary
The API returned 503s from 02:10 to 02:45 UTC because the nightly export used up the DB connection pool.
## Timeline
- 02:09:58 export starts, opens 40 connections
- 02:10:07 pool exhausted, API returns 503
- 02:31 on-call paged
- 02:42 export killed; 02:45 recovered
## Root cause
The export job and the API share a 50-connection pool; the export took 40 of them.
## Actions
- Give the export its own capped pool (max 10).
- Alert when the pool passes 80%.
