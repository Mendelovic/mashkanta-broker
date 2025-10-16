import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


def run_async(awaitable: Awaitable[T]) -> T:
    async def _runner() -> T:
        return await awaitable

    return asyncio.run(_runner())
