# probe_test.py
import asyncio
from tools.httpx import HttpxTool

async def main():
    prober = HttpxTool()
    results = await prober.run(["hackerone.com"])
    print(f"Got {len(results)} results")
    for r in results:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())