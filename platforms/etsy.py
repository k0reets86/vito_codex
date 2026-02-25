"""EtsyPlatform — Etsy API v3 integration.

Etsy API v3 docs: https://developers.etsy.com/documentation/
Auth: x-api-key header with ETSY_KEYSTRING for read-only.
Write operations require OAuth2 PKCE flow (not yet implemented).
"""

from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("etsy", agent="etsy")
API_BASE = "https://openapi.etsy.com/v3"


class EtsyPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="etsy", **kwargs)
        self._keystring = settings.ETSY_KEYSTRING
        self._shared_secret = settings.ETSY_SHARED_SECRET
        self._oauth_token: str = ""  # Will be set after OAuth2 PKCE flow
        self._shop_id: str = ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self, write: bool = False) -> dict[str, str]:
        """Headers for API requests.

        Etsy API v3 requires x-api-key = keystring:shared_secret.
        write=True requires OAuth token.
        """
        api_key = self._keystring
        if self._shared_secret:
            api_key = f"{self._keystring}:{self._shared_secret}"
        headers = {"x-api-key": api_key}
        if write and self._oauth_token:
            headers["Authorization"] = f"Bearer {self._oauth_token}"
        return headers

    async def authenticate(self) -> bool:
        """Verify API key via ping endpoint."""
        if not self._keystring:
            self._authenticated = False
            return False

        try:
            session = await self._get_session()
            # Use openapi-ping to verify key
            async with session.get(
                f"{API_BASE}/application/openapi-ping",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                self._authenticated = resp.status == 200
                if self._authenticated:
                    logger.info("Etsy API key verified", extra={"event": "etsy_auth_ok"})
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Etsy auth failed: {resp.status} {body[:200]}",
                        extra={"event": "etsy_auth_fail"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Etsy auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def get_shop(self, shop_id: str = "") -> dict:
        """GET /v3/application/shops/{shop_id} — get shop info."""
        if not self._authenticated:
            await self.authenticate()
        if not self._authenticated:
            return {}

        sid = shop_id or self._shop_id
        if not sid:
            return {"error": "No shop_id configured"}

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/shops/{sid}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def search_listings(self, keywords: str, limit: int = 25) -> list[dict]:
        """GET /v3/application/listings/active — search active listings."""
        if not self._authenticated:
            await self.authenticate()
        if not self._authenticated:
            return []

        try:
            session = await self._get_session()
            params = {"keywords": keywords, "limit": min(limit, 100)}
            async with session.get(
                f"{API_BASE}/application/listings/active",
                headers=self._headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    logger.info(
                        f"Etsy search '{keywords}': {len(results)} results",
                        extra={"event": "etsy_search_ok", "context": {"count": len(results)}},
                    )
                    return results
                return []
        except Exception as e:
            logger.error(f"Etsy search error: {e}", exc_info=True)
            return []

    async def get_listing(self, listing_id: int) -> dict:
        """GET /v3/application/listings/{listing_id}."""
        if not self._authenticated:
            await self.authenticate()

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/listings/{listing_id}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_trending_keywords(self) -> list[dict]:
        """GET /v3/application/buyer-taxonomy/nodes — browse categories."""
        if not self._authenticated:
            await self.authenticate()

        try:
            session = await self._get_session()
            async with session.get(
                f"{API_BASE}/application/buyer-taxonomy/nodes",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("results", [])
                return []
        except Exception as e:
            logger.error(f"Etsy taxonomy error: {e}", exc_info=True)
            return []

    async def publish(self, content: dict) -> dict:
        """Create a draft listing (requires OAuth2 token).

        content: {title, description, price, quantity, taxonomy_id, tags[], who_made, when_made, is_supply}
        """
        if content.get("dry_run"):
            title = content.get("title", "")
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"etsy dry_run title={str(title)[:80]}",
                    evidence="dryrun:etsy",
                    source="etsy.publish",
                    evidence_dict={"platform": "etsy", "dry_run": True, "title": title},
                )
            except Exception:
                pass
            return {
                "platform": "etsy",
                "status": "prepared",
                "dry_run": True,
                "title": title,
            }

        if not self._oauth_token:
            logger.warning(
                "Etsy publish requires OAuth2 token (not yet configured)",
                extra={"event": "etsy_publish_no_oauth"},
            )
            return {
                "platform": "etsy",
                "status": "needs_oauth",
                "error": "OAuth2 PKCE token required for write operations. "
                         "Read-only mode active with API keystring.",
            }

        if not self._shop_id:
            return {"platform": "etsy", "status": "error", "error": "No shop_id configured"}

        try:
            session = await self._get_session()
            listing_data = {
                "title": content.get("title", ""),
                "description": content.get("description", ""),
                "price": content.get("price", 0),
                "quantity": content.get("quantity", 1),
                "taxonomy_id": content.get("taxonomy_id", 0),
                "tags": content.get("tags", []),
                "who_made": content.get("who_made", "i_did"),
                "when_made": content.get("when_made", "2020_2025"),
                "is_supply": content.get("is_supply", False),
                "type": "download",  # digital product
                "state": "draft",
            }

            async with session.post(
                f"{API_BASE}/application/shops/{self._shop_id}/listings",
                headers={**self._headers(write=True), "Content-Type": "application/json"},
                json=listing_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status in (200, 201):
                    listing_id = data.get("listing_id", "")
                    listing_url = f"https://www.etsy.com/listing/{listing_id}" if listing_id else ""
                    logger.info(
                        f"Etsy listing created: {listing_id}",
                        extra={"event": "etsy_publish_ok", "context": {"listing_id": listing_id}},
                    )
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="created",
                            detail=f"etsy listing_id={listing_id}",
                            evidence=listing_url,
                            source="etsy.publish",
                            evidence_dict={"platform": "etsy", "listing_id": listing_id, "url": listing_url},
                        )
                    except Exception:
                        pass
                    return {
                        "platform": "etsy",
                        "status": "created",
                        "listing_id": listing_id,
                        "url": listing_url,
                        "state": "draft",
                        "data": data,
                    }
                error = data.get("error", str(resp.status))
                logger.warning(f"Etsy publish failed: {error}", extra={"event": "etsy_publish_fail"})
                return {"platform": "etsy", "status": "error", "error": error}

        except Exception as e:
            logger.error(f"Etsy publish error: {e}", exc_info=True)
            return {"platform": "etsy", "status": "error", "error": str(e)}

    async def start_oauth2_pkce(self) -> dict:
        """Start OAuth2 PKCE flow. Returns auth_url for owner to visit.

        Etsy requires PKCE for all write operations (create listings, upload images).
        Flow: 1) start_oauth2_pkce() → auth_url  2) owner visits URL  3) complete_oauth2(code)
        """
        import secrets
        import hashlib
        import base64

        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()

        self._code_verifier = code_verifier

        redirect_uri = "https://localhost:3000/oauth/callback"
        scopes = "listings_w%20listings_r%20transactions_r%20shops_r"

        auth_url = (
            f"https://www.etsy.com/oauth/connect"
            f"?response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
            f"&client_id={self._keystring}"
            f"&state=vito_etsy_auth"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

        logger.info("Etsy OAuth2 PKCE flow started", extra={"event": "etsy_oauth_start"})
        return {
            "auth_url": auth_url,
            "code_verifier": code_verifier,
            "note": "Owner must visit auth_url, authorize, and provide the code from callback URL",
        }

    async def complete_oauth2(self, auth_code: str, code_verifier: str = "") -> bool:
        """Exchange auth code for access token (step 2 of PKCE flow)."""
        verifier = code_verifier or getattr(self, "_code_verifier", "")
        if not verifier:
            logger.warning("No code_verifier for Etsy OAuth2", extra={"event": "etsy_oauth_no_verifier"})
            return False

        try:
            session = await self._get_session()
            async with session.post(
                "https://api.etsy.com/v3/public/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": self._keystring,
                    "redirect_uri": "https://localhost:3000/oauth/callback",
                    "code": auth_code,
                    "code_verifier": verifier,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._oauth_token = data.get("access_token", "")
                    self._refresh_token = data.get("refresh_token", "")
                    logger.info(
                        "Etsy OAuth2 completed successfully",
                        extra={"event": "etsy_oauth_ok"},
                    )
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Etsy OAuth2 failed: {resp.status} {body[:200]}",
                        extra={"event": "etsy_oauth_fail"},
                    )
                    return False
        except Exception as e:
            logger.error(f"Etsy OAuth2 error: {e}", exc_info=True)
            return False

    async def refresh_oauth_token(self) -> bool:
        """Refresh expired OAuth2 token."""
        refresh_token = getattr(self, "_refresh_token", "")
        if not refresh_token:
            return False

        try:
            session = await self._get_session()
            async with session.post(
                "https://api.etsy.com/v3/public/oauth/token",
                json={
                    "grant_type": "refresh_token",
                    "client_id": self._keystring,
                    "refresh_token": refresh_token,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._oauth_token = data.get("access_token", "")
                    self._refresh_token = data.get("refresh_token", self._refresh_token)
                    logger.info("Etsy OAuth2 refreshed", extra={"event": "etsy_oauth_refreshed"})
                    return True
                return False
        except Exception as e:
            logger.error(f"Etsy token refresh error: {e}", exc_info=True)
            return False

    async def get_analytics(self) -> dict:
        """Get shop analytics (requires shop_id and OAuth)."""
        if not self._shop_id:
            return {"platform": "etsy", "views": 0, "sales": 0, "revenue": 0.0}

        try:
            session = await self._get_session()
            # Get shop listings to count stats
            async with session.get(
                f"{API_BASE}/application/shops/{self._shop_id}/listings/active",
                headers=self._headers(),
                params={"limit": 100},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    listings = data.get("results", [])
                    total_views = sum(l.get("views", 0) for l in listings)
                    total_favorites = sum(l.get("num_favorers", 0) for l in listings)
                    return {
                        "platform": "etsy",
                        "listings": len(listings),
                        "views": total_views,
                        "favorites": total_favorites,
                        "sales": 0,  # requires transactions endpoint + OAuth
                        "revenue": 0.0,
                    }
        except Exception as e:
            logger.error(f"Etsy analytics error: {e}", exc_info=True)

        return {"platform": "etsy", "views": 0, "sales": 0, "revenue": 0.0}

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
