import logging

from anthropic import AsyncAnthropic

from src.config import settings
from src.news.base import NewsItem

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a futures market analyst specializing in ES (S&P 500 E-mini) and NQ (Nasdaq 100 E-mini) futures.

Analyze the following news item and assess its potential impact on ES and NQ futures trading.

Headline: {headline}
Summary: {summary}
Source: {source}
Symbols mentioned: {symbols}

Provide your analysis as a structured response."""

ANALYSIS_TOOL = {
    "name": "news_analysis",
    "description": "Structured analysis of a news item's impact on ES/NQ futures",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevance_score": {
                "type": "number",
                "description": "How relevant this news is to ES/NQ futures trading (0-10, where 0 is irrelevant and 10 is directly impactful)",
            },
            "sentiment": {
                "type": "string",
                "enum": ["BULLISH", "BEARISH", "NEUTRAL"],
                "description": "Expected market sentiment impact",
            },
            "impact_rating": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                "description": "Expected magnitude of market impact. CRITICAL = major market-moving event (Fed rate decision, economic crisis). HIGH = significant sector/market event. MEDIUM = notable but contained. LOW = minimal expected impact.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this news matters (or doesn't) for ES/NQ",
            },
            "affected_sectors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sectors most affected by this news",
            },
            "expected_direction": {
                "type": "string",
                "enum": ["UP", "DOWN", "SIDEWAYS", "VOLATILE"],
                "description": "Expected short-term price direction for ES/NQ",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this analysis (0.0-1.0)",
            },
        },
        "required": [
            "relevance_score",
            "sentiment",
            "impact_rating",
            "reasoning",
            "affected_sectors",
            "expected_direction",
            "confidence",
        ],
    },
}


class NewsAnalyzer:
    """Analyzes news items using Claude API for relevance, sentiment, and impact."""

    def __init__(self):
        self._client: AsyncAnthropic | None = None

    def initialize(self) -> None:
        if not settings.anthropic_api_key:
            logger.warning("Anthropic API key not set, news analyzer disabled")
            return
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        logger.info("News analyzer initialized with model %s", settings.news_analysis_model)

    async def analyze(self, item: NewsItem) -> dict | None:
        """Analyze a news item using Claude API.

        Returns a dict with: relevance_score, sentiment, impact_rating, reasoning,
        affected_sectors, expected_direction, confidence. Or None if analysis fails.
        """
        if not self._client:
            return None

        prompt = ANALYSIS_PROMPT.format(
            headline=item.headline,
            summary=item.summary,
            source=item.source,
            symbols=", ".join(item.symbols) if item.symbols else "none specified",
        )

        try:
            response = await self._client.messages.create(
                model=settings.news_analysis_model,
                max_tokens=1024,
                tools=[ANALYSIS_TOOL],
                tool_choice={"type": "tool", "name": "news_analysis"},
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract the tool use response
            for block in response.content:
                if block.type == "tool_use" and block.name == "news_analysis":
                    analysis = block.input
                    logger.info(
                        "News analyzed: '%s' → relevance=%.1f, impact=%s, sentiment=%s",
                        item.headline[:60],
                        analysis["relevance_score"],
                        analysis["impact_rating"],
                        analysis["sentiment"],
                    )
                    return analysis

            logger.warning("No tool_use block in Claude response for news analysis")
            return None

        except Exception:
            logger.exception("Error analyzing news item: %s", item.headline[:60])
            return None
