from src.news.base import BaseNewsProvider
from src.news.finnhub import FinnhubNewsProvider

# Registry of available news providers
_PROVIDERS: dict[str, type[BaseNewsProvider]] = {
    "finnhub": FinnhubNewsProvider,
}


def create_news_provider(provider_name: str = "finnhub") -> BaseNewsProvider:
    """Create a news provider instance by name.

    To add a new provider:
    1. Implement BaseNewsProvider in a new module
    2. Register it in _PROVIDERS above
    3. Set NEWS_PROVIDER env var to the provider name
    """
    provider_class = _PROVIDERS.get(provider_name.lower())
    if not provider_class:
        available = ", ".join(_PROVIDERS.keys())
        raise ValueError(f"Unknown news provider: {provider_name}. Available: {available}")
    return provider_class()
