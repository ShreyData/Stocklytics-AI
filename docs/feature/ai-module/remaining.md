# AI Module - Remaining Tasks

- [ ] Add query length validation (min/max character limits on `query` field in `ChatRequest`).
- [ ] Implement session scoping — validate that the `chat_session_id` belongs to the authenticated `store_id`.
- [ ] Migrate Gemini client from deprecated `google-generativeai` to `google-genai` SDK when `requirements.txt` is updated.
- [ ] Add analytics summary from BigQuery mart tables into the AI context (currently only Firestore metadata is used).
