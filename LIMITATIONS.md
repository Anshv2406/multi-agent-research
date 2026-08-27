# Limitations & Known Failure Modes

This document outlines where the ResearchAgent pipeline is likely to fail in real-world
use, and what mitigations are (or aren't yet) in place. Written as part of evaluating
production-readiness beyond "it works on the happy path."

## Architecture recap

5-stage sequential pipeline: **Search → Reader → Writer → Fact-Checker → Critic**,
each stage backed by an LLM call (Gemini primary, Grok fallback) and two of the
five stages (Search, Reader) also depend on external tool calls (Tavily search API,
raw web scraping).

---

## 1. LLM provider reliability

- **Model deprecation without notice.** During development, `gemini-1.5-flash` and
  then `gemini-2.5-flash` both returned `404 NOT_FOUND` mid-project as Google retired
  them, and were replaced with `gemini-3.6-flash`. Hardcoding a model string is
  itself a failure mode — provider model lifecycles are outside our control and can
  break the app with no code change on our end.
- **Rate limits / quota exhaustion.** Free-tier API keys throttle aggressively. A
  single pipeline run makes 5+ sequential LLM calls; concurrent users multiply this
  fast and will hit 429s.
- **✅ Fixed:** `llm = primary_llm.with_fallbacks([fallback_llm])` — Gemini calls that
  fail (429, 404, timeout) automatically retry on Grok (`grok-4-fast` via xAI's
  OpenAI-compatible endpoint). Verified working locally. Not yet load-tested under
  real concurrency.
- **Not yet handled:** no retry/backoff *within* a single provider (a transient
  Gemini blip goes straight to fallback rather than retrying Gemini once first), and
  no circuit breaker if Grok is also down.

## 2. Latency & timeouts

- No timeout is set on the LLM calls themselves (only `scrape_url`'s `requests.get`
  has a 15s timeout). A hung provider request can stall the entire run indefinitely.
- 5 sequential LLM calls plus a web search and a scrape make each run inherently
  slow (typically 30–90s). This is a poor fit for a synchronous single-threaded
  Streamlit request cycle — there's no progress persistence if the browser tab closes
  mid-run.

## 3. Data & content quality

- **Scraping will get blocked.** Sites behind Cloudflare, paywalls, or bot-detection
  (LinkedIn, many news sites) will return 403s or garbage HTML despite the
  trafilatura → readability → raw-BeautifulSoup fallback chain in `scrape_url`.
- **URL selection is non-deterministic.** The reader agent picks which URL to scrape
  from search snippets via LLM judgment — it can pick an irrelevant, dead, paywalled,
  or non-English result with no fallback if that pick fails.
- **✅ Fixed:** `research_combined` (search + scraped content passed to the writer)
  is now capped at ~12,000 characters before being sent to the model, to avoid
  exceeding the context window on broad topics. This is a rough character-based
  heuristic, not real token counting — very token-dense content could still slip
  past the intended budget.

## 4. Correctness & hallucination

- **Hallucination can compound across agents.** If the writer invents a claim, only
  the fact-checker stage catches it — and LLM-as-judge fact-checking is itself
  unreliable; it can confidently rubber-stamp an unsupported claim as verified.
- **No structured/schema-validated output.** All chain outputs are free-text via
  `StrOutputParser()`. If a model ignores the requested response format (e.g. skips
  the `Score: X/10` line), Streamlit rendering degrades silently rather than failing
  loudly — a malformed response looks like a normal, if oddly-worded, result.

## 5. Deployment (Render specifically)

- **Free-tier cold starts.** Render's free tier spins down on inactivity; the first
  request after idle takes 30–60s to wake, on top of the pipeline's own 30–90s run
  time — a first-time user's experience can look broken/hung.
- **✅ Partially mitigated:** the "Run Research Pipeline" button is now disabled
  while a run is in progress (`disabled=st.session_state.running`), preventing a
  user from spamming it and triggering overlapping pipeline runs against the same
  API keys. This does not limit total runs per session/day.
- **Secrets handling.** `GOOGLE_API_KEY`, `XAI_API_KEY`, and `TAVILY_API_KEY` are
  set as Render environment variables, never committed to the repo. `.env` and
  `.venv/` are excluded via `.gitignore` and confirmed absent from the GitHub repo.

## 6. What's *not* covered by the fact-checker

The fact-checker chain (`fact_checker_chain`) compares the report against the single
scraped source and the search snippets — it cannot verify claims against the broader
internet, so a claim that's internally consistent with our limited source set but
factually wrong in the real world will still pass.

---

## Suggested next steps (not yet implemented)

- Add per-provider retry-with-backoff before falling back to a second provider
- Replace the character-based truncation heuristic with real token counting
- Add an explicit timeout + user-facing error state for hung LLM calls
- Add lightweight output validation (e.g. regex/schema check on critic's `Score: X/10`)
- Add a true per-session/per-day rate limit, not just a button lock during a run
