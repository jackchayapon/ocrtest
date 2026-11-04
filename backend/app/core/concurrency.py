"""Fixed worker count with stable output order and no task-per-item queue."""
import asyncio


async def ordered_map(items, function, limit):
    items = list(items)
    results = [None] * len(items)
    pending = iter(enumerate(items))

    async def worker():
        for index, item in pending:
            results[index] = await function(item)

    await asyncio.gather(*(worker() for _ in range(min(limit, len(items)))))
    return results
