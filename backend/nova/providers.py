import asyncio
import boto3
import httpx
import logging
import re
from html.parser import HTMLParser
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from urllib.parse import parse_qs, urlparse, urlunparse
from .config import settings

logger = logging.getLogger("uvicorn.error")

class ProviderError(Exception): pass

class BedrockProvider:
    async def complete(self, system, messages, max_tokens=1200):
        if not settings.bedrock_model_id:
            raise ProviderError("Bedrock is not configured. Set BEDROCK_MODEL_ID and configure AWS credentials and model access.")
        def invoke():
            client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
            return client.converse(modelId=settings.bedrock_model_id, system=[{"text": system}], messages=messages, inferenceConfig={"maxTokens": max_tokens, "temperature": 0.35})
        try:
            response = await asyncio.wait_for(asyncio.to_thread(invoke), timeout=75)
            return response["output"]["message"]["content"][0]["text"]
        except asyncio.TimeoutError as exc: raise ProviderError("Amazon Bedrock did not respond before the 75 second limit.") from exc
        except NoCredentialsError as exc: raise ProviderError("AWS credentials were not found. Configure the standard AWS credential chain.") from exc
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "BedrockError")
            messages = {"AccessDeniedException": "AWS denied Bedrock access. Check IAM permissions and model access.", "ResourceNotFoundException": "The configured Bedrock model is unavailable in this region.", "ThrottlingException": "Bedrock is rate limiting requests. Try again shortly."}
            raise ProviderError(messages.get(code, "Amazon Bedrock could not complete the request. Check region, model access, and AWS configuration.")) from exc
        except BotoCoreError as exc: raise ProviderError("AWS could not connect to Amazon Bedrock. Check network and AWS configuration.") from exc

class GroqProvider:
    async def complete(self, system, messages, max_tokens=1200):
        if not settings.groq_api_key.strip():
            raise ProviderError("Groq is not configured. Set GROQ_API_KEY in the repository .env file.")
        if not settings.groq_model.strip():
            raise ProviderError("Groq is not configured. Set GROQ_MODEL to a model available to your Groq account.")
        try:
            from groq import AsyncGroq, APIConnectionError, APIError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError
        except ImportError as exc:
            raise ProviderError("The Groq SDK is missing from the backend environment. Install backend/requirements.txt and restart NOVA.") from exc
        converted = [{"role": "system", "content": system}]
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
            converted.append({"role": message.get("role", "user"), "content": content})
        client = AsyncGroq(api_key=settings.groq_api_key.strip(), max_retries=0, timeout=75)
        try:
            response = await client.chat.completions.create(model=settings.groq_model.strip(), messages=converted, max_tokens=max_tokens, temperature=0.35)
            content = response.choices[0].message.content if response.choices else None
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("Groq returned an empty response. Try again or choose another available model.")
            return content
        except AuthenticationError as exc:
            raise ProviderError("Groq rejected the API key. Check GROQ_API_KEY.") from exc
        except RateLimitError as exc:
            raise ProviderError("Groq rate limit or quota was reached. Wait and try again, or check your Groq account limits.") from exc
        except APIStatusError as exc:
            error_detail = str(getattr(exc, "body", "")).lower()
            if exc.status_code == 404 or (exc.status_code == 400 and "model" in error_detail and any(term in error_detail for term in ("not found", "unsupported", "decommission", "unavailable", "does not exist"))):
                raise ProviderError("The configured Groq model is unavailable. Check GROQ_MODEL and your account's model access.") from exc
            raise ProviderError("Groq could not complete the request. Check model access and Groq service status.") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise ProviderError("Groq could not be reached before the 75 second limit. Check the network and try again.") from exc
        except APIError as exc:
            raise ProviderError("Groq returned an API error. Check the configured model and Groq account access.") from exc

class AIProvider:
    @property
    def name(self):
        provider = settings.ai_provider.strip().lower()
        return "Groq" if provider == "groq" else "Amazon Bedrock" if provider == "bedrock" else provider

    @property
    def configured(self):
        provider = settings.ai_provider.strip().lower()
        if provider == "groq": return bool(settings.groq_api_key and settings.groq_model)
        if provider == "bedrock": return bool(settings.bedrock_model_id)
        return False

    def configuration_error(self):
        provider = settings.ai_provider.strip().lower()
        if provider == "groq":
            return "Groq is not configured. Set GROQ_API_KEY and GROQ_MODEL in the repository .env file."
        if provider == "bedrock":
            return "Bedrock is not configured. Set BEDROCK_MODEL_ID and configure AWS credentials and model access."
        return "AI_PROVIDER must be either groq or bedrock."

    async def complete(self, system, messages, max_tokens=1200):
        provider = settings.ai_provider.strip().lower()
        if provider == "groq":
            logger.info("Routing AI request to Groq")
            return await groq_provider.complete(system, messages, max_tokens)
        if provider == "bedrock":
            logger.info("Routing AI request to Amazon Bedrock")
            return await bedrock_provider.complete(system, messages, max_tokens)
        raise ProviderError(self.configuration_error())

class SearchProvider:
    async def search(self, query, limit=6):
        limit = max(1, min(limit, 10))
        query = self._prepare_query(query)
        source = "Tavily" if settings.tavily_api_key.strip() else "DuckDuckGo HTML"
        logger.info("Starting web search with %s", source)
        if settings.tavily_api_key.strip():
            raw = await self._tavily(query, limit)
        else:
            raw = await self._duckduckgo(query)
        results = self._normalize_results(raw, source, limit)
        if not results:
            if source == "Tavily":
                raise ProviderError("Tavily returned no results with usable source URLs for this query. Try different search terms or check Tavily search availability.")
            raise ProviderError("DuckDuckGo returned no parseable results with usable source URLs. Its HTML may have changed or the request may be blocked; configure TAVILY_API_KEY for the Tavily search API.")
        return results

    def _prepare_query(self, query):
        text = " ".join(str(query).split())
        lowered = text.lower()
        laptop_budget = "laptop" in lowered and re.search(r"\b(?:under|below|less than|within|budget|max(?:imum)?)\b.{0,24}(?:₹|rs\.?|inr\s*)?\s*10(?:[,.]?000)\b|(?:₹|rs\.?|inr\s*)\s*10(?:[,.]?000)\b|\b10k\b", lowered)
        if laptop_budget:
            return f"{text} India INR ₹10,000 new laptop under 10000 refurbished used current price listings"
        return text

    async def _tavily(self, query, limit):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20), follow_redirects=True) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {settings.tavily_api_key.strip()}", "Content-Type": "application/json"},
                    json={"query": query, "max_results": limit, "search_depth": "basic", "topic": "general", "include_answer": False},
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    status = response.status_code
                    if status == 401:
                        message = "Tavily rejected TAVILY_API_KEY. Check that the key is valid and active."
                    elif status == 403:
                        message = "Tavily denied this search request. Check your account access and plan."
                    elif status == 429:
                        message = "Tavily rate limit was reached. Wait before retrying or check your API usage."
                    elif status in (432, 433):
                        message = "Tavily usage limit was reached. Check your Tavily plan and usage limits."
                    elif status >= 500:
                        message = "Tavily search service is currently unavailable. Try again later."
                    else:
                        message = f"Tavily rejected the search request (HTTP {status}). Check the query and Tavily API configuration."
                    raise ProviderError(message) from exc
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProviderError("Tavily returned an invalid response. Try again later.") from exc
                if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                    raise ProviderError("Tavily returned an unexpected response format. Try again later.")
                return payload["results"]
        except httpx.TimeoutException as exc:
            raise ProviderError("Tavily search timed out. Check the network and try again.") from exc
        except httpx.RequestError as exc:
            raise ProviderError("Could not connect to Tavily. Check the network and try again.") from exc

    async def _duckduckgo(self, query):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(18), follow_redirects=True) as client:
                response = await client.get("https://html.duckduckgo.com/html/", params={"q": query}, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36", "Accept":"text/html,application/xhtml+xml"})
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if response.status_code in (403, 429):
                        raise ProviderError(f"DuckDuckGo blocked or rate limited the search request (HTTP {response.status_code}). Configure TAVILY_API_KEY or try again later.") from exc
                    raise ProviderError(f"DuckDuckGo search failed (HTTP {response.status_code}). Configure TAVILY_API_KEY or try again later.") from exc
                body = response.text
                lower_body = body.lower()
                if any(marker in lower_body for marker in ("anomaly-modal", "automated requests", "unusual traffic", "name=\"challenge-form\"")):
                    raise ProviderError("DuckDuckGo blocked this search request. Configure TAVILY_API_KEY or try again later.")
                parser = DuckDuckGoResults()
                parser.feed(body)
                return parser.results
        except httpx.TimeoutException as exc:
            raise ProviderError("DuckDuckGo search timed out. Configure TAVILY_API_KEY or try again later.") from exc
        except httpx.RequestError as exc:
            raise ProviderError("Could not connect to DuckDuckGo. Check the network or configure TAVILY_API_KEY.") from exc

    def _normalize_results(self, records, source, limit):
        results, seen = [], set()
        if not isinstance(records, list):
            return results
        for item in records:
            if not isinstance(item, dict):
                continue
            raw_url = item.get("url")
            if not isinstance(raw_url, str):
                continue
            raw_url = raw_url.strip()
            if raw_url.startswith("//"):
                raw_url = "https:" + raw_url
            try:
                parsed = urlparse(raw_url)
                if parsed.hostname and parsed.hostname.lower().endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
                    raw_url = parse_qs(parsed.query).get("uddg", [""])[0].strip()
                    parsed = urlparse(raw_url)
                hostname = parsed.hostname
            except ValueError:
                continue
            if parsed.scheme.lower() not in ("http", "https") or not hostname or parsed.username or parsed.password:
                continue
            url = urlunparse(parsed._replace(fragment=""))
            key = urlunparse(parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), fragment=""))
            if key in seen:
                continue
            title = item.get("title")
            snippet = item.get("snippet") or item.get("content")
            results.append({
                "title": title.strip() if isinstance(title, str) else "",
                "url": url,
                "snippet": snippet.strip() if isinstance(snippet, str) else "",
                "source": item.get("source") if isinstance(item.get("source"), str) and item.get("source").strip() else source,
            })
            seen.add(key)
            if len(results) >= limit:
                break
        return results


class DuckDuckGoResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.capture = None
        self.capture_tag = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        test_id = attrs.get("data-testid", "")
        is_title = tag == "a" and ("result__a" in classes or "result__title" in classes or test_id in ("result-title-a", "result-title"))
        is_snippet = self.current is not None and ("result__snippet" in classes or test_id in ("result-snippet", "result-snippet-text"))
        if is_title:
            self.current = {"title": "", "url": attrs.get("href", ""), "snippet": "", "source": "DuckDuckGo HTML"}
            self.results.append(self.current)
            self.capture, self.capture_tag = "title", tag
        elif is_snippet:
            self.capture, self.capture_tag = "snippet", tag

    def handle_data(self, data):
        if self.current is not None and self.capture:
            self.current[self.capture] += data

    def handle_endtag(self, tag):
        if self.capture and tag == self.capture_tag:
            self.capture, self.capture_tag = None, None

bedrock_provider = BedrockProvider()
groq_provider = GroqProvider()
ai_provider = AIProvider()
search_provider = SearchProvider()
