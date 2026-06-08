
import asyncio
from plugins.bgp_enum import BgpPlugin

async def main():
    plugin = BgpPlugin({})
    results = await plugin.run('telekom.de')
    print(f"Total: {len(results)}")
    for sub in results:
        print(sub)


asyncio.run(main())