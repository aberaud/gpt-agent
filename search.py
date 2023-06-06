import os
import pprint
import aiohttp
import asyncio
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv()


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ID = os.getenv("GOOGLE_SEARCH_ID")

async def get(url, headers = {'Accept': 'application/json'}):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                print("Error:", response.status)
                return None

async def get_kg_data(query):
    query = quote(query)
    json_data = await get(f'https://kgsearch.googleapis.com/v1/entities:search?query={query}&key={GOOGLE_API_KEY}')
    items = json_data['itemListElement']
    items = [item['result'] for item in items]
    pprint.pprint(items)
    return items


async def get_search_data(query):
    query = quote(query)
    json_data = await get(f'https://customsearch.googleapis.com/customsearch/v1?cx={GOOGLE_SEARCH_ID}&q={query}&key={GOOGLE_API_KEY}')
    items = json_data['items']
    items = [{
        'title': item['title'],
        'link': item['link'],
        'snippet': item['snippet'],
    } for item in items]
    pprint.pprint(items, width=200)
    return items

def search(query, source='google'):
    if source == 'google':
        return get_search_data(query)
    elif source == 'knowledge-graph':
        return get_kg_data(query)
    else:
        print(f"Unknown source: {source}")
        return get_search_data(f"{query} {source}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Search the web using Google.")
    parser.add_argument("query", help="The query to search for.")
    parser.add_argument("-s", "--source", default="google", help="The source to search from (default: google).")
    args = parser.parse_args()
    asyncio.run(search(args.query, source=args.source))