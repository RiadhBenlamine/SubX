# probe_test.py
import asyncio
from tools.httpx import (Httpx)

async def main():
    prober = Httpx("hackerone.com")
    results = await prober.run_httpx()
    print(f"Got {len(results)} results")
    for r in results:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())