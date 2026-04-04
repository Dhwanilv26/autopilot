from autopilot.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup


class WebFetchParams(BaseModel):
    url: str = Field(..., description="URL to fetch (must be http:// or https://)")
    timeout: int = Field(30, ge=5, le=120)


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch and extract clean text content from a URL."
    kind = ToolKind.NETWORK

    @property
    def schema(self):
        return WebFetchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)

        
        parsed = urlparse(params.url)
        if parsed.scheme not in ["http", "https"]:
            return ToolResult.error_result("URL must start with http:// or https://")

        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(params.timeout),
                follow_redirects=True,
                headers=headers
            ) as client:

                response = await client.get(params.url)
                response.raise_for_status()
                html = response.text

        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
            )

        except Exception as e:
            return ToolResult.error_result(f"Request failed: {e}")

        if "window." in html or "javascript" in html[:2000]:
            # heuristic: JS-heavy page
            dynamic_flag = True
        else:
            dynamic_flag = False

        soup = BeautifulSoup(html, "html.parser")

        # remove noise
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        text = soup.get_text(separator="\n")

        lines = [line.strip() for line in text.splitlines()]
        clean_text = "\n".join(line for line in lines if line)

        MAX_CHARS = 5000
        if len(clean_text) > MAX_CHARS:
            clean_text = clean_text[:MAX_CHARS] + "\n... [truncated]"

        if len(clean_text) < 200:
            return ToolResult.error_result(
                "Page has little or no extractable content (possibly dynamic site)."
            )

        result = f"Title: {title}\n\n{clean_text}"

        if dynamic_flag:
            result = "[Note: Page appears dynamic / JS-heavy]\n\n" + result

        return ToolResult.success_result(
            result,
            metadata={
                "status_code": response.status_code,
                "content_length": len(response.content),
                "dynamic_detected": dynamic_flag
            }
        )
