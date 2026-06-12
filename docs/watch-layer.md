# Watch Layer — how standing watches fetch the open web

> Decision doc. All facts verified live on **2026-06-12** (hackathon day). Status codes below are from
> actual `curl` fetches run from this machine, same day.

## Decision

**PRIMARY: plain HTTP fetch (httpx, browser User-Agent) + LLM extraction** — implemented as the
existing `web_fetch(url)` tool in `backend/agent/tools.py`. Zero new dependencies, zero per-call cost
beyond tokens, works on every demo target below.

**FALLBACK: Anthropic server-side `web_search` tool** in the watch-runner's Messages call. When a
target blocks direct fetch (Zillow), Claude searches Anthropic's index instead — search results carry
Zillow/realtor listing snippets even though the sites 403 direct scrapers. GA, no beta header,
$10 / 1,000 searches + tokens ([docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool), pulled 2026-06-12).

**Reframe the demo line:** "watch Zillow for 77005" → the watch actually fetches **Redfin** (works) or
uses `web_search` (works). Same user intent, no on-camera 403.

## Live test results (2026-06-12, curl with Chrome UA)

| Target | Status | Verdict |
|---|---|---|
| zillow.com/houston-tx-77005/ | **403** (PerimeterX/HUMAN) | Blocked. Don't fight it in 4h. |
| redfin.com/zipcode/77005 | **200**, 654KB, real listings + prices | ✅ Use this for housing |
| redfin stingray API (`/stingray/api/gis?...region_id=29481`) | **200**, clean JSON (price, sqft, MLS#) | ✅ Even better — diffable JSON |
| realtor.com/...77005 | 429 rate-limited | Skip |
| news.ycombinator.com | **200**, full HTML | ✅ |
| hnrss.org/newest?q=... | **200**, RSS | ✅ |
| text.npr.org / lite.cnn.com | **200** | ✅ news targets |
| ebay.com/sch/... | 403 | Skip |
| houston.craigslist.org/search/apa | 200 but JS-rendered, **0 listings in HTML** | Skip |

Note: Redfin 302-redirects `python-httpx/0.27` UA — **always send a browser UA.**

## Primary: exact code (drop into `agent/tools.py` impl of `web_fetch`)

```python
import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

def web_fetch(url: str, max_chars: int = 40_000) -> str:
    """Fetch a URL; return text for the agent/LLM to parse. Never raises."""
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=15, follow_redirects=True)
        if r.status_code != 200:
            return f"FETCH_ERROR status={r.status_code} url={url}"
        return r.text[:max_chars]          # watch-runner prompt does the extraction
    except Exception as e:
        return f"FETCH_ERROR {type(e).__name__}: {e}"
```

Extraction is just the watch cycle's `run_turn` with `prompts.WATCH_RUNNER` ("here is the page text +
the user's preference vault — list matching items as JSON"). Changed-detection: store the previous
cycle's extracted item IDs/URLs in the watch's `last_result` (core/store.py) and report only new ones.

## Fallback: server-side web_search (exact request syntax, verified 2026-06-12)

```python
response = client.messages.create(
    model=os.environ.get("MODEL", "claude-sonnet-4-6"),
    max_tokens=2048,
    messages=[{"role": "user", "content": "New 3bd+ listings in Houston 77005 this week?"}],
    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
)
```

- GA on Claude API (admin must enable web search in Console settings → privacy). `$10/1k` searches.
- `web_search_20260209` adds dynamic filtering (needs code-execution tool) — skip for hackathon, `20250305` is simpler.
- Results come back with citations + `encrypted_content`; handle `stop_reason == "pause_turn"` by re-sending.
- Sister tool `web_fetch_20250910` is **free** (tokens only) but: no JS rendering, can only fetch URLs
  already present in conversation context, and still gets `url_not_accessible` on bot-blocked sites —
  it does **not** bypass Zillow. Use `web_search`, not `web_fetch`, as the blocked-site fallback.
  ([web fetch docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool), pulled 2026-06-12)

## Three demo-safe watch targets (all verified by my own fetches today)

1. **Redfin 77005** — `https://www.redfin.com/zipcode/77005` (HTML, prices/beds present) or the JSON API
   `https://www.redfin.com/stingray/api/gis?al=1&region_id=29481&region_type=2&num_homes=25&status=9&v=8`
   (strip the leading `{}&&`). Changed-detection: diff MLS IDs between cycles. **This is the hero demo
   watch** — same intent as "watch Zillow", visceral, and it actually works.
2. **Hacker News** — `https://hnrss.org/newest?q=agents` (RSS) or `https://news.ycombinator.com/`.
   Changed-detection: new item links since last cycle. Updates every few minutes → likely shows a real
   hit live on camera.
3. **NPR text news** — `https://text.npr.org/` (6KB, trivially parseable). Changed-detection: new
   headline links. Good "watch the news for X" steering demo.

## Demo determinism: self-hosted fixture (the can't-fail option)

Add to `backend/app.py` (serves from the same FastAPI process the demo already runs):

```python
@app.get("/demo/listings")            # the watch targets http://localhost:8000/demo/listings
def demo_listings():
    return json.loads(Path("data/demo_listings.json").read_text())

@app.post("/demo/listings/add")       # hit this mid-demo → next cycle finds a "new listing"
def demo_add():
    ...append a canned 3bd/1800sqft listing to data/demo_listings.json...
```

Spawn one watch on the fixture URL + manual `POST /watches/{id}/run` (already in the API) = a fully
scripted on-camera loop. Run Redfin/HN watches alongside for the "it's real" beat.

## Rejected (with reasons, current as of 2026-06-12)

- **browser-use** — v0.13.0 (PyPI, released 2026-06-08), requires Python ≥3.11, new Rust-core beta agent;
  it's an LLM-driven agent per page-visit: slow, nondeterministic, and its own browser install. Wrong
  tool for a timed demo. ([PyPI](https://pypi.org/project/browser-use/), [GitHub](https://github.com/browser-use/browser-use))
- **Playwright headless** — setup is fine (~2 min, `pip install playwright && playwright install chromium`),
  but Zillow runs PerimeterX/HUMAN which detects vanilla headless Playwright (403 / press-and-hold
  captcha); bypass needs Patchright/stealth + residential proxies. Not a 4h problem.
  ([ZenRows 2026](https://www.zenrows.com/blog/perimeterx-bypass), [ScrapeOps](https://scrapeops.io/playwright-web-scraping-playbook/nodejs-playwright-bypass-perimeterx/))
- **Composio browser/web toolkits** — v3 does ship FIRECRAWL, BROWSERBASE_TOOL, SCRAPE_DO toolkits
  ([docs.composio.dev/toolkits/firecrawl](https://docs.composio.dev/toolkits/firecrawl),
  [browserbase_tool](https://docs.composio.dev/toolkits/browserbase_tool)), but each needs a third-party
  account + API key + auth-config setup. Composio stays scoped to Gmail/Calendar garnish (docs/composio.md).

## Sources (all pulled 2026-06-12)

- Anthropic web search tool — https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- Anthropic web fetch tool — https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool
- browser-use — https://pypi.org/project/browser-use/ · https://github.com/browser-use/browser-use
- PerimeterX/Zillow blocking — https://www.zenrows.com/blog/perimeterx-bypass · https://scrapfly.io/blog/posts/how-to-bypass-perimeterx-human-anti-scraping
- Composio toolkits — https://docs.composio.dev/toolkits/firecrawl · https://docs.composio.dev/toolkits/browserbase_tool
- Status codes: live curl tests from this machine, 2026-06-12 (see table above)
