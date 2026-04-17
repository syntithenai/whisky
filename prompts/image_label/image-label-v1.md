# Image Label Prompt v1

Classify each image into exactly one label from this fixed set:
- bottle
- logo
- award
- lifestyle
- equipment
- junk

Return strict JSON array only.
Do not invent labels.
Reasons must be concise and visual.

## Input Payload Keys Per Image

- image_id
- source_url
- page_url
- local_path
- alt_text
- context_excerpt

## Output Item Constraints

1. label must be exactly one of the allowed labels.
2. confidence must be numeric in range 0 to 1.
3. reason must be 8 to 280 characters.
4. Include image_id in each output item.
5. Return JSON only. No markdown wrappers.
