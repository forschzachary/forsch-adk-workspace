# Writing evals

Build a quality flywheel for an agent: eval sets graded by an LLM judge on your gateway (no Vertex).

## Steps

1. **Scaffold a set** — `forsch eval <id> --new` writes `eval_sets/<id>.evalset.json` with one example
   case. Eval sets are versioned, so agent quality is tracked over time.
2. **Author cases** — each case is a `conversation` with a `user_content` (what the user says) and a
   `final_response` (the kind of answer you want). The judge grades the agent's actual reply against
   that expected `final_response`.
3. **Run** — `forsch eval <id>`. The agent runs through the gateway, the `final_response_match_v2`
   judge (`gpt-5.5`) scores each case, and you get a scorecard: case / metric / score / threshold / ✓.
4. **Tune the bar** — `forsch eval <id> --threshold 0.8` to demand a closer match.

## What makes a good case

- One clear intent per case; write the `final_response` as the *behaviour* you want, not verbatim text
  (the judge scores semantic match).
- Cover the agent's core jobs and its guardrails (a case where it should refuse or defer).
- Add cases as you find failures — that's the flywheel turning.

## Notes

- Needs the gateway creds in `.adk-local.env` (`LITELLM_BASE_URL` + a key). Fully local otherwise.
- The judge and the agent both run on your gateway; nothing touches cloud eval services.
