# Review Prompt v1

You are reviewing a whisky knowledge crawl run.
Use only the supplied run data.
Return strict JSON with keys: summary, priorities_next_run, action_items.
Keep recommendations specific and actionable.

## Input Payload Keys

- run_summary
- per_site_stats
- failure_stats
- relevance_distribution
- triage_snapshot
- extraction_completeness
- image_label_distribution

## Output Constraints

1. summary.overall_quality must be one of: high, medium, low.
2. summary.coverage_assessment must be one of: high, medium, low.
3. summary.notable_gaps must be an array of concise strings.
4. priorities_next_run must be an array.
5. Each priorities_next_run item must include:
   - type
   - name
   - reason
   - priority_score (0 to 1)
6. action_items must be an array.
7. Each action_items item must include:
   - id
   - severity (high, medium, low)
   - category
   - title
   - details
   - owner
   - suggested_fix
8. Return JSON only. No markdown wrappers.
