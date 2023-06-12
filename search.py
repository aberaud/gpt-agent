import os
import pprint
import aiohttp
import asyncio
from urllib.parse import urlencode
from dotenv import load_dotenv
load_dotenv()


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_SEARCH_ID = os.getenv("GOOGLE_SEARCH_ID")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")


async def get(url, params={}, headers = {'Accept': 'application/json'}):
    async with aiohttp.ClientSession() as session:
        url = f'{url}?{urlencode(params)}'
        print(url)
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                print("Error:", response.status)
                return None

def filer_organic_result(result):
    return {
        'title': result['title'],
        'link': result['link'],
        'snippet': result['snippet'],
    }

def filter_knowledge_graph(result):
    pass

async def get_serp_data(query):
    json_data = await get('https://serpapi.com/search.json', {
        'engine': 'google',
        'q': query,
        'api_key': SERPAPI_KEY,
    })
    #data = {
    #    'organic_results': [filer_organic_result(r) for r in json_data['organic_results']],
    #    'knowledge_graph': json_data['knowledge_graph'],
    #}
    data = [filer_organic_result(r) for r in json_data['organic_results']]
    pprint.pprint(data)
    return json_data
    

async def get_kg_data(query):
    json_data = await get('https://kgsearch.googleapis.com/v1/entities:search', {
        query: query,
        'key': GOOGLE_API_KEY,
    })
    items = json_data['itemListElement']
    items = [item['result'] for item in items]
    pprint.pprint(items)
    return items


async def get_search_data(query):
    json_data = await get('https://customsearch.googleapis.com/customsearch/v1', {
        'q': query,
        'key': GOOGLE_API_KEY,
        'cx': GOOGLE_SEARCH_ID,
    })
    items = json_data['items']
    items = [{
        'title': item['title'],
        'link': item['link'],
        'snippet': item['snippet'],
    } for item in items]
    pprint.pprint(items, width=200)
    return items

async def get_wiki_data(query):
    page_py = wiki_wiki.page(query, unquote=True)
    print(page_py.text)
    return page_py.text


async def search(query, source='google'):
    if source == 'google':
        return await get_search_data(query)
    if source == 'serp':
        return await get_serp_data(query)
    elif source == 'knowledge-graph':
        return await get_kg_data(query)
    else:
        print(f"Unknown source: {source}")
        return await get_search_data(f"{query} {source}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Search the web using Google.")
    parser.add_argument("query", help="The query to search for.")
    parser.add_argument("-s", "--source", default="google", help="The source to search from (default: google).")
    args = parser.parse_args()
    asyncio.run(search(args.query, source=args.source))
