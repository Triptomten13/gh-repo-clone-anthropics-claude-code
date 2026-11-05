# Integrations

Live status is always available at **Systems & Integrations** in the dashboard (`GET /api/integrations`).
States: `configured` (implemented + credentials present) · `missing_credentials` (implemented, needs env vars) ·
`planned` (adapter not implemented yet).

## Implemented

| Connector | Env vars | Capability | Verified |
|---|---|---|---|
| Anthropic Claude (AI) | `ANTHROPIC_API_KEY` | Tiered models, adaptive thinking, structured JSON outputs, server-side refusal fallback, token/cost accounting | Unit-tested with a fake provider; SDK parameters checked against the installed `anthropic` package; **no live call made** (no key in the dev environment) |
| YouTube Data API v3 | `YOUTUBE_API_KEY` | Recent videos, views and comments per keyword (region SE) | Mocked HTTP test |
| Reddit API | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | Weekly post volume & engagement; complaint-title mining | Implemented; not live-tested |
| eBay Browse API | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` (`EBAY_MARKETPLACE`) | Product candidates with prices; active listing counts | Implemented; not live-tested |
| Etsy Open API v3 | `ETSY_API_KEY` | Product candidates; listing counts & favourites | Implemented; not live-tested |
| Shopify Admin GraphQL | `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_TOKEN` | Create **draft** products; publish is approval-gated | Implemented; not live-tested |
| Manual / licensed import | — | CSV/JSON import of products, trend observations, ledger entries (`/api/import/*`, Lab → Import) | Tested |

To verify a connector after adding credentials: put a keyword on the Market Radar watchlist and press
**Run market scan**; the research task result (Agent Control Room) shows the signal count or the API error.

## Planned (registered, not implemented)

TikTok Research / Shop Partner API · Instagram Graph API · Amazon PA-API 5 / SP-API · Google Trends API (alpha) ·
Pinterest API v5 · AliExpress Open Platform · Alibaba.com Open API · CJdropshipping · Temu (no public API — import only) ·
Walmart Marketplace · Mercado Libre · Kickstarter (no API — import only) · Product Hunt API v2 · Faire ·
WooCommerce · Stripe · PayPal · Klarna · Printful · Printify · Meta Marketing API · Google Ads API · Klaviyo.

Each is listed in `backend/app/integrations/connectors.py` with its required credentials, docs link and access notes
(e.g. approval programmes). Not yet covered by any adapter: Global Sources, Indiegogo, AppSumo, Google Shopping,
Facebook groups, patent/trademark databases (EUIPO/PRV) — use manual import meanwhile.

## Adding a connector

```python
class MyConnector(Connector):
    id, name = "my_platform", "My Platform API"
    required_env = ("MY_PLATFORM_KEY",)
    capabilities = ("signals",)            # and/or "products"
    rate_per_second = 1.0

    def search_signals(self, keyword):
        self.require()                     # raises NotConfigured -> task "blocked"
        data = self.get("https://api.example.com/search", params={"q": keyword}).json()
        return [Signal(keyword, self.id, "mentions", float(data["count"]))]
```

Register it in `integrations/registry.py`. The Chief Intelligence Agent automatically includes every configured
research connector in market scans. Test with `httpx.MockTransport` (see `tests/test_orchestration.py`).
