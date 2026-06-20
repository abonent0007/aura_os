# web_search_skill/skill.py — DuckDuckGo search via web_search module
import asyncio, threading
from autogen.beta import tools

from web_search import WebSearchConfig, DuckDuckGoSearch


def _run_async(coro):
    result = []
    def _t():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result.append(loop.run_until_complete(coro))
        except Exception as e:
            result.append(f"Error: {e}")
        finally:
            loop.close()
    t = threading.Thread(target=_t)
    t.start()
    t.join(timeout=15)
    return result[0] if result else "Timeout"


def _get_searcher(max_results=5):
    return DuckDuckGoSearch(WebSearchConfig(default_results=max_results))


@tools.tool
def search_web_ddgs(query: str, max_results: int = 5) -> str:
    """Поиск в интернете через DuckDuckGo. Используй для фактов, цен, рецептов."""
    s = _get_searcher(max_results)
    results = _run_async(s.search(query, max_results))
    if not isinstance(results, list):
        return f"Search error: {results}"
    if not results:
        return f"No results for: {query}"
    lines = [f"Search results for '{query}':"]
    for i, r in enumerate(results[:max_results], 1):
        lines.append(f"\n{i}. {r.get('title','?')}")
        lines.append(f"   {r.get('snippet','')[:150]}")
        if r.get('url'):
            lines.append(f"   {r['url']}")
    return "\n".join(lines)


@tools.tool
def search_news_ddgs(query: str, max_results: int = 5) -> str:
    """Поиск новостей через DuckDuckGo. Используй для новостей, событий в мире."""
    s = _get_searcher(max_results)
    results = _run_async(s.search_news(query, max_results))
    if not isinstance(results, list):
        return f"News search error: {results}"
    if not results:
        return f"No news for: {query}"
    lines = [f"News for '{query}':"]
    for i, r in enumerate(results[:max_results], 1):
        lines.append(f"\n{i}. {r.get('title','?')}")
        lines.append(f"   {r.get('snippet','')[:150]}")
        if r.get('url'):
            lines.append(f"   {r['url']}")
    return "\n".join(lines)
