"""TwitterPlatform — интеграция с X.com (Twitter) API v2.

OAuth 1.0a для постинга. Все ключи уже в .env.
"""

import hashlib
import hmac
import time
import urllib.parse
import uuid
from typing import Any

import aiohttp

from config.logger import get_logger
from config.settings import settings
from platforms.base_platform import BasePlatform
from modules.execution_facts import ExecutionFacts

logger = get_logger("twitter", agent="twitter")

API_V2 = "https://api.twitter.com/2"


class TwitterPlatform(BasePlatform):
    def __init__(self, **kwargs):
        super().__init__(name="twitter", **kwargs)
        self._consumer_key = settings.TWITTER_CONSUMER_KEY
        self._consumer_secret = settings.TWITTER_CONSUMER_SECRET
        self._access_token = settings.TWITTER_ACCESS_TOKEN
        self._access_secret = settings.TWITTER_ACCESS_SECRET
        self._bearer_token = settings.TWITTER_BEARER_TOKEN
        self._session: aiohttp.ClientSession | None = None
        self._user_id: str = ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _oauth1_header(self, method: str, url: str, params: dict | None = None) -> str:
        """Generate OAuth 1.0a Authorization header."""
        oauth_params = {
            "oauth_consumer_key": self._consumer_key,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self._access_token,
            "oauth_version": "1.0",
        }

        all_params = {**oauth_params}
        if params:
            all_params.update(params)

        # Create signature base string
        sorted_params = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(sorted_params, safe='')}"

        # Create signing key
        signing_key = f"{urllib.parse.quote(self._consumer_secret, safe='')}&{urllib.parse.quote(self._access_secret, safe='')}"

        # Generate signature
        signature = hmac.new(
            signing_key.encode(), base_string.encode(), hashlib.sha1
        ).digest()
        oauth_params["oauth_signature"] = urllib.parse.quote(
            __import__("base64").b64encode(signature).decode(), safe=""
        )

        # Build header
        auth_header = "OAuth " + ", ".join(
            f'{k}="{v}"' for k, v in sorted(oauth_params.items())
        )
        return auth_header

    async def authenticate(self) -> bool:
        """Verify credentials via GET /2/users/me."""
        if not all([self._consumer_key, self._consumer_secret, self._access_token, self._access_secret]):
            self._authenticated = False
            return False

        try:
            session = await self._get_session()
            url = f"{API_V2}/users/me"
            headers = {
                "Authorization": self._oauth1_header("GET", url),
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("data", {})
                    self._user_id = user.get("id", "")
                    self._authenticated = True
                    logger.info(
                        f"Twitter auth OK: @{user.get('username', '?')}",
                        extra={"event": "twitter_auth_ok", "context": {"username": user.get("username")}},
                    )
                else:
                    body = await resp.text()
                    self._authenticated = False
                    logger.warning(
                        f"Twitter auth failed: {resp.status} {body[:200]}",
                        extra={"event": "twitter_auth_fail"},
                    )
                return self._authenticated
        except Exception as e:
            logger.error(f"Twitter auth error: {e}", exc_info=True)
            self._authenticated = False
            return False

    async def publish(self, content: dict) -> dict:
        """POST /2/tweets — create a tweet.

        content: {text: str, reply_to: str (optional), media_ids: list (optional)}
        """
        if content.get("dry_run"):
            preview = (content.get("text", "") or "")[:280]
            try:
                ExecutionFacts().record(
                    action="platform:publish",
                    status="prepared",
                    detail=f"twitter dry_run preview_len={len(preview)}",
                    evidence="dryrun:twitter",
                    source="twitter.publish",
                    evidence_dict={"platform": "twitter", "dry_run": True, "text_preview": preview},
                )
            except Exception:
                pass
            return {
                "platform": "twitter",
                "status": "prepared",
                "dry_run": True,
                "text_preview": preview,
            }

        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "twitter", "status": "not_authenticated"}

        text = content.get("text", "")
        if not text:
            return {"platform": "twitter", "status": "error", "error": "No text provided"}

        # Twitter limit: 280 chars
        if len(text) > 280:
            text = text[:277] + "..."

        try:
            session = await self._get_session()
            url = f"{API_V2}/tweets"
            payload: dict[str, Any] = {"text": text}

            if content.get("reply_to"):
                payload["reply"] = {"in_reply_to_tweet_id": content["reply_to"]}
            if content.get("media_ids"):
                payload["media"] = {"media_ids": content["media_ids"]}

            headers = {
                "Authorization": self._oauth1_header("POST", url),
                "Content-Type": "application/json",
            }

            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if resp.status in (200, 201):
                    tweet = data.get("data", {})
                    tweet_id = tweet.get("id", "")
                    tweet_url = f"https://x.com/i/status/{tweet_id}" if tweet_id else ""
                    logger.info(
                        f"Tweet posted: {tweet_id}",
                        extra={"event": "twitter_publish_ok", "context": {"tweet_id": tweet_id}},
                    )
                    try:
                        ExecutionFacts().record(
                            action="platform:publish",
                            status="published",
                            detail=f"twitter tweet_id={tweet_id}",
                            evidence=tweet_url,
                            source="twitter.publish",
                            evidence_dict={"platform": "twitter", "tweet_id": tweet_id, "url": tweet_url},
                        )
                    except Exception:
                        pass
                    return {
                        "platform": "twitter",
                        "status": "published",
                        "tweet_id": tweet_id,
                        "url": tweet_url,
                        "text": text,
                    }
                else:
                    error = data.get("detail", data.get("title", str(resp.status)))
                    logger.warning(f"Tweet failed: {error}", extra={"event": "twitter_publish_fail"})

                    # Save to file if permissions/billing issue — don't claim published
                    if "permission" in error.lower() or "oauth1" in error.lower() or "credit" in error.lower() or resp.status == 403:
                        return await self._save_draft_tweet(text, error)

                    return {"platform": "twitter", "status": "error", "error": error}

        except Exception as e:
            logger.error(f"Twitter publish error: {e}", exc_info=True)
            return {"platform": "twitter", "status": "error", "error": str(e)}

    async def delete_tweet(self, tweet_id: str) -> dict:
        """DELETE /2/tweets/{id} — cleanup helper for live probes/tests."""
        if not tweet_id:
            return {"platform": "twitter", "status": "error", "error": "tweet_id required"}
        if not self._authenticated:
            auth_ok = await self.authenticate()
            if not auth_ok:
                return {"platform": "twitter", "status": "not_authenticated"}
        try:
            session = await self._get_session()
            url = f"{API_V2}/tweets/{tweet_id}"
            headers = {"Authorization": self._oauth1_header("DELETE", url)}
            async with session.delete(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if resp.status in (200, 202):
                    try:
                        ExecutionFacts().record(
                            action="platform:cleanup",
                            status="success",
                            detail=f"twitter delete tweet_id={tweet_id}",
                            evidence=f"https://x.com/i/status/{tweet_id}",
                            source="twitter.delete",
                            evidence_dict={"platform": "twitter", "tweet_id": tweet_id},
                        )
                    except Exception:
                        pass
                    return {"platform": "twitter", "status": "deleted", "tweet_id": tweet_id, "data": data}
                return {"platform": "twitter", "status": "error", "error": str(data)[:300]}
        except Exception as e:
            return {"platform": "twitter", "status": "error", "error": str(e)}

    async def _save_draft_tweet(self, text: str, error: str) -> dict:
        """Save tweet to file when write permissions are not available."""
        from pathlib import Path
        import time as _time

        out = Path("/home/vito/vito-agent/output/tweets")
        out.mkdir(parents=True, exist_ok=True)
        fp = out / f"tweet_{int(_time.time())}.txt"
        fp.write_text(text, encoding="utf-8")
        logger.info(
            f"Tweet saved to file (no write perms): {fp}",
            extra={"event": "twitter_draft_saved", "context": {"path": str(fp)}},
        )
        try:
            ExecutionFacts().record(
                action="platform:publish",
                status="prepared",
                detail="twitter draft saved",
                evidence=str(fp),
                source="twitter.publish",
                evidence_dict={"platform": "twitter", "draft_path": str(fp)},
            )
        except Exception:
            pass
        return {
            "platform": "twitter",
            "status": "draft_saved",
            "file_path": str(fp),
            "text": text,
            "note": f"Готово к публикации, жду разрешения. Ошибка: {error}",
        }

    async def get_analytics(self) -> dict:
        """Get basic account metrics."""
        if not self._authenticated:
            await self.authenticate()
        if not self._user_id:
            return {"platform": "twitter", "followers": 0, "tweets": 0}

        try:
            session = await self._get_session()
            url = f"{API_V2}/users/{self._user_id}?user.fields=public_metrics"
            headers = {"Authorization": f"Bearer {self._bearer_token}"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    metrics = data.get("data", {}).get("public_metrics", {})
                    return {
                        "platform": "twitter",
                        "followers": metrics.get("followers_count", 0),
                        "following": metrics.get("following_count", 0),
                        "tweets": metrics.get("tweet_count", 0),
                        "listed": metrics.get("listed_count", 0),
                    }
        except Exception as e:
            logger.error(f"Twitter analytics error: {e}", exc_info=True)
        return {"platform": "twitter", "followers": 0, "tweets": 0}

    async def health_check(self) -> bool:
        return await self.authenticate()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
