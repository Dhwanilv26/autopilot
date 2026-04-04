from autopilot.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from ddgs import DDGS


class WebSearchParams(BaseModel):
    query: str = Field(
        ...,
        description="Search query."
    )

    max_results: int = Field(
        10,
        ge=1,
        le=20,
        description="Maximum results to return (default: 10)."
    )


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information. Returns search results with titles, URLs and snippets."
    kind = ToolKind.NETWORK

    @property
    def schema(self):
        return WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)

        try:
            results = DDGS().text(
                params.query,
                region="in-en",
                safesearch="off",
                timelimit="y",  # recency filter, y=year
                page=1,
                # auto choose b/w html,cached results, 3rd party APIs (e.g, Wikipedia)
                backend="auto"
            )

            results = list(results)[:params.max_results]
        except Exception as e:
            return ToolResult.error_result(f"web search failed : {e}")

        if not results:
            return ToolResult.error_result(
                f"no results found for : {params.query}",
                metadata={
                    "results": 0
                }
            )

        output_lines = [f"Search results for: {params.query}"]

        for i, result in enumerate(results, start=1):
            output_lines.append(f"{i}, Title: {result['title']}")
            output_lines.append(f" URL: {result['href']}")

            if result.get('body'):
                output_lines.append(f" Snippet: {result['body']}")

            output_lines.append("")

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "results": len(results)
            }
        )
