"""Platform adapters built on official APIs.

Implemented (work as soon as credentials are provided): YouTube Data API v3,
Reddit API (OAuth app-only), eBay Browse API, Etsy Open API v3, Shopify Admin
GraphQL API (draft products only; publishing is approval-gated).

The remaining platforms are registered as *planned* adapters with their access
requirements documented, so they show up honestly in the dashboard.
"""
from __future__ import annotations

import base64
import time
from typing import Any

from .base import Connector, ProductCandidate, Signal


class YouTubeConnector(Connector):
    id = "youtube"
    name = "YouTube Data API v3"
    required_env = ("YOUTUBE_API_KEY",)
    docs_url = "https://developers.google.com/youtube/v3"
    access_notes = "API key from Google Cloud console. Quota: 10,000 units/day by default; search costs 100 units."
    rate_per_second = 2.0
    capabilities = ("signals",)
    BASE = "https://www.googleapis.com/youtube/v3"

    def search_signals(self, keyword: str) -> list[Signal]:
        self.require()
        key = self.env("YOUTUBE_API_KEY")
        s = self.get(f"{self.BASE}/search", params={"part": "id", "q": keyword, "type": "video", "order": "date",
                                                     "maxResults": 25, "regionCode": "SE", "key": key}).json()
        ids = [it["id"]["videoId"] for it in s.get("items", []) if it.get("id", {}).get("videoId")]
        if not ids:
            return [Signal(keyword, "youtube", "recent_videos", 0.0, source_ref="search")]
        v = self.get(f"{self.BASE}/videos", params={"part": "statistics", "id": ",".join(ids), "key": key}).json()
        views = sum(int(i.get("statistics", {}).get("viewCount", 0)) for i in v.get("items", []))
        comments = sum(int(i.get("statistics", {}).get("commentCount", 0)) for i in v.get("items", []))
        return [
            Signal(keyword, "youtube", "recent_videos", float(len(ids)), source_ref="youtube:search"),
            Signal(keyword, "youtube", "recent_video_views", float(views), source_ref="youtube:videos"),
            Signal(keyword, "youtube", "recent_video_comments", float(comments), source_ref="youtube:videos"),
        ]


class RedditConnector(Connector):
    id = "reddit"
    name = "Reddit API"
    required_env = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
    docs_url = "https://www.reddit.com/dev/api"
    access_notes = "Register a 'script' or 'web' app; respect Reddit Data API terms (no resale of data, rate limits ~100 QPM)."
    rate_per_second = 1.0
    capabilities = ("signals", "complaints")
    _token: tuple[str, float] | None = None

    def _auth(self) -> dict[str, str]:
        if self._token and self._token[1] > time.time() + 60:
            return {"Authorization": f"Bearer {self._token[0]}", "User-Agent": self.env("REDDIT_USER_AGENT")}
        basic = base64.b64encode(f"{self.env('REDDIT_CLIENT_ID')}:{self.env('REDDIT_CLIENT_SECRET')}".encode()).decode()
        r = self.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                      headers={"Authorization": f"Basic {basic}", "User-Agent": self.env("REDDIT_USER_AGENT")}).json()
        self._token = (r["access_token"], time.time() + float(r.get("expires_in", 3600)))
        return {"Authorization": f"Bearer {self._token[0]}", "User-Agent": self.env("REDDIT_USER_AGENT")}

    def _search(self, q: str, limit: int = 50) -> list[dict[str, Any]]:
        r = self.get("https://oauth.reddit.com/search", params={"q": q, "sort": "new", "t": "week", "limit": limit},
                     headers=self._auth()).json()
        return [c["data"] for c in r.get("data", {}).get("children", [])]

    def search_signals(self, keyword: str) -> list[Signal]:
        self.require()
        posts = self._search(keyword)
        engagement = sum(p.get("score", 0) + p.get("num_comments", 0) for p in posts)
        return [
            Signal(keyword, "reddit", "weekly_posts", float(len(posts)), source_ref="reddit:search"),
            Signal(keyword, "reddit", "weekly_engagement", float(engagement), source_ref="reddit:search"),
        ]

    def complaints(self, keyword: str) -> list[str]:
        """Post titles that express problems with a product (aggregated, no personal data kept)."""
        self.require()
        markers = ("broke", "broken", "disappoint", "returned", "doesn't work", "stopped working", "waste", "problem", "issue", "cheap")
        titles = [p.get("title", "") for p in self._search(f"{keyword} (problem OR broke OR returned OR disappointed)")]
        return [t for t in titles if any(m in t.lower() for m in markers)][:20]


class EbayConnector(Connector):
    id = "ebay"
    name = "eBay Browse API"
    required_env = ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET")
    docs_url = "https://developer.ebay.com/api-docs/buy/browse/overview.html"
    access_notes = "Production keyset from the eBay developer program; application access token (client credentials)."
    capabilities = ("products", "signals")
    _token: tuple[str, float] | None = None

    def _auth(self) -> dict[str, str]:
        if not (self._token and self._token[1] > time.time() + 60):
            basic = base64.b64encode(f"{self.env('EBAY_CLIENT_ID')}:{self.env('EBAY_CLIENT_SECRET')}".encode()).decode()
            r = self.post("https://api.ebay.com/identity/v1/oauth2/token",
                          data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
                          headers={"Authorization": f"Basic {basic}"}).json()
            self._token = (r["access_token"], time.time() + float(r.get("expires_in", 7200)))
        return {"Authorization": f"Bearer {self._token[0]}", "X-EBAY-C-MARKETPLACE-ID": self.env("EBAY_MARKETPLACE") or "EBAY_DE"}

    def _search(self, keyword: str, limit: int) -> dict[str, Any]:
        return self.get("https://api.ebay.com/buy/browse/v1/item_summary/search",
                        params={"q": keyword, "limit": min(limit, 200)}, headers=self._auth()).json()

    def search_products(self, keyword: str, limit: int = 20) -> list[ProductCandidate]:
        self.require()
        out = []
        for it in self._search(keyword, limit).get("itemSummaries", []):
            price = it.get("price", {})
            out.append(ProductCandidate(name=it.get("title", ""), platform="ebay", source_url=it.get("itemWebUrl", ""),
                                        price=float(price["value"]) if price.get("value") else None,
                                        currency=price.get("currency", ""),
                                        category=(it.get("categories") or [{}])[0].get("categoryName", ""),
                                        raw={"itemId": it.get("itemId"), "condition": it.get("condition")}))
        return out

    def search_signals(self, keyword: str) -> list[Signal]:
        self.require()
        total = self._search(keyword, 1).get("total", 0)
        return [Signal(keyword, "ebay", "active_listings", float(total), source_ref="ebay:browse")]


class EtsyConnector(Connector):
    id = "etsy"
    name = "Etsy Open API v3"
    required_env = ("ETSY_API_KEY",)
    docs_url = "https://developers.etsy.com/documentation"
    access_notes = "Personal app keystring as x-api-key. Public listing search only; follow Etsy API terms."
    rate_per_second = 5.0
    capabilities = ("products", "signals")

    def _search(self, keyword: str, limit: int) -> dict[str, Any]:
        return self.get("https://openapi.etsy.com/v3/application/listings/active",
                        params={"keywords": keyword, "limit": min(limit, 100), "sort_on": "created"},
                        headers={"x-api-key": self.env("ETSY_API_KEY")}).json()

    def search_products(self, keyword: str, limit: int = 20) -> list[ProductCandidate]:
        self.require()
        out = []
        for it in self._search(keyword, limit).get("results", []):
            p = it.get("price") or {}
            price = p.get("amount") / p.get("divisor", 100) if p.get("amount") is not None else None
            out.append(ProductCandidate(name=it.get("title", ""), platform="etsy", source_url=it.get("url", ""), price=price,
                                        currency=p.get("currency_code", ""), description=(it.get("description") or "")[:500],
                                        raw={"listing_id": it.get("listing_id"), "num_favorers": it.get("num_favorers"),
                                             "is_customizable": it.get("is_customizable")}))
        return out

    def search_signals(self, keyword: str) -> list[Signal]:
        self.require()
        data = self._search(keyword, 100)
        favs = sum((r.get("num_favorers") or 0) for r in data.get("results", []))
        return [Signal(keyword, "etsy", "active_listings", float(data.get("count", 0)), source_ref="etsy:listings"),
                Signal(keyword, "etsy", "favorites_top100", float(favs), source_ref="etsy:listings")]


class ShopifyConnector(Connector):
    id = "shopify"
    name = "Shopify Admin API"
    kind = "commerce"
    required_env = ("SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_TOKEN")
    docs_url = "https://shopify.dev/docs/api/admin-graphql"
    access_notes = "Custom app with write_products scope. Products are created as DRAFT; publishing needs an approved LEVEL 4 request."
    capabilities = ("create_draft_product",)
    API_VERSION = "2025-07"

    def _gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        url = f"https://{self.env('SHOPIFY_STORE_DOMAIN')}/admin/api/{self.API_VERSION}/graphql.json"
        r = self.post(url, json={"query": query, "variables": variables},
                      headers={"X-Shopify-Access-Token": self.env("SHOPIFY_ADMIN_TOKEN")}).json()
        if r.get("errors"):
            raise RuntimeError(f"Shopify error: {r['errors']}")
        return r["data"]

    def create_draft_product(self, title: str, description_html: str, tags: list[str] | None = None) -> dict[str, Any]:
        self.require()
        q = """mutation($product: ProductCreateInput!) {
          productCreate(product: $product) { product { id title status } userErrors { field message } }
        }"""
        d = self._gql(q, {"product": {"title": title, "descriptionHtml": description_html, "status": "DRAFT", "tags": tags or []}})
        res = d["productCreate"]
        if res["userErrors"]:
            raise RuntimeError(f"Shopify userErrors: {res['userErrors']}")
        return res["product"]


def _planned(cid: str, name: str, env: tuple[str, ...], docs: str, notes: str, kind: str = "research") -> type[Connector]:
    return type(f"{cid.title().replace('_', '')}Connector", (Connector,), {
        "id": cid, "name": name, "required_env": env, "docs_url": docs, "access_notes": notes,
        "implemented": False, "kind": kind,
    })


PLANNED = [
    _planned("tiktok", "TikTok Research API / TikTok Shop Partner API", ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"),
             "https://developers.tiktok.com/products/research-api/",
             "Research API access is application-based (academic/eligible orgs). Shop Partner API requires seller authorisation."),
    _planned("instagram", "Instagram Graph API", ("META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN"),
             "https://developers.facebook.com/docs/instagram-platform",
             "Hashtag search and business discovery require an Instagram professional account and app review."),
    _planned("amazon", "Amazon Product Advertising API 5 / SP-API", ("AMAZON_PAAPI_ACCESS_KEY", "AMAZON_PAAPI_SECRET_KEY", "AMAZON_PARTNER_TAG"),
             "https://webservices.amazon.com/paapi5/documentation/",
             "PA-API needs an approved Associates account with qualifying sales. Reviews are not available via API."),
    _planned("google_trends", "Google Trends API", ("GOOGLE_TRENDS_API_KEY",), "https://developers.google.com/search/apis/trends",
             "Official API is in limited alpha; alternatively import licensed Trends exports via the manual import endpoint."),
    _planned("pinterest", "Pinterest API v5", ("PINTEREST_ACCESS_TOKEN",), "https://developers.pinterest.com/docs/api/v5/",
             "Trends endpoint requires approved app access."),
    _planned("aliexpress", "AliExpress Open Platform (affiliate/dropship)", ("ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET"),
             "https://openservice.aliexpress.com/", "Requires approved developer account."),
    _planned("alibaba", "Alibaba.com Open API", ("ALIBABA_APP_KEY", "ALIBABA_APP_SECRET"), "https://openapi.alibaba.com/",
             "Supplier/product data via approved ISV access."),
    _planned("cjdropshipping", "CJdropshipping API", ("CJ_API_KEY",), "https://developers.cjdropshipping.com/",
             "Account API key; product, inventory and order endpoints.", kind="fulfillment"),
    _planned("temu", "Temu", (), "", "No public research API. Use licensed datasets or manual import only."),
    _planned("walmart", "Walmart Marketplace API", ("WALMART_CLIENT_ID", "WALMART_CLIENT_SECRET"),
             "https://developer.walmart.com/", "Seller account required."),
    _planned("mercadolibre", "Mercado Libre API", ("MELI_APP_ID", "MELI_SECRET"), "https://developers.mercadolibre.com/", "OAuth app."),
    _planned("kickstarter", "Kickstarter", (), "", "No public API; manual import of permitted public data only."),
    _planned("producthunt", "Product Hunt API v2", ("PRODUCTHUNT_TOKEN",), "https://api.producthunt.com/v2/docs", "Developer token; non-commercial terms apply."),
    _planned("faire", "Faire (wholesale)", ("FAIRE_API_TOKEN",), "https://faire.github.io/external-api-v2-docs/", "Brand/retailer API access."),
    _planned("woocommerce", "WooCommerce REST API", ("WOO_URL", "WOO_CONSUMER_KEY", "WOO_CONSUMER_SECRET"),
             "https://woocommerce.github.io/woocommerce-rest-api-docs/", "Store REST keys.", kind="commerce"),
    _planned("stripe", "Stripe", ("STRIPE_SECRET_KEY",), "https://docs.stripe.com/api", "Restricted key with read access to charges/payouts for ledger sync.", kind="payments"),
    _planned("paypal", "PayPal", ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"), "https://developer.paypal.com/api/rest/", "REST app.", kind="payments"),
    _planned("klarna", "Klarna Payments", ("KLARNA_USERNAME", "KLARNA_PASSWORD"), "https://docs.klarna.com/", "Merchant credentials.", kind="payments"),
    _planned("printful", "Printful API", ("PRINTFUL_TOKEN",), "https://developers.printful.com/docs/", "Private token.", kind="fulfillment"),
    _planned("printify", "Printify API", ("PRINTIFY_TOKEN",), "https://developers.printify.com/", "Personal access token.", kind="fulfillment"),
    _planned("meta_ads", "Meta Marketing API", ("META_ADS_TOKEN", "META_AD_ACCOUNT_ID"), "https://developers.facebook.com/docs/marketing-apis",
             "Read-only insights by default; campaign creation is LEVEL 5 and approval-gated.", kind="marketing"),
    _planned("google_ads", "Google Ads API", ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CUSTOMER_ID"), "https://developers.google.com/google-ads/api",
             "Developer token approval required.", kind="marketing"),
    _planned("klaviyo", "Klaviyo", ("KLAVIYO_API_KEY",), "https://developers.klaviyo.com/", "Consent-based email flows only.", kind="marketing"),
]
