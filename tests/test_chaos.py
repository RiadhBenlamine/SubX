
import asyncio
from plugins.chaos_enum import ChaosPlugin

async def main():
    plugin = ChaosPlugin({"CHAOS_API": ""})
    results = await plugin.run("telekom.de")
    print(f"Total: {len(results)}")
    for sub in results:
        print(sub)

asyncio.run(main())