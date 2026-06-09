import asyncio
from plugins.crtsh_enum import CrtshPlugin

async def main():
    plugin = CrtshPlugin({})
    results = await plugin.run("telekom.de")
    for sub in results:
        print(sub)
    print(f"Total: {len(results)}")


if __name__ == "__main__":
    asyncio.run(main())