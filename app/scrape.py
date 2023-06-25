import asyncio
import aiohttp
from urllib.parse import urlencode
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5.1 Safari/605.1.15"

async def get(url, params={}):
    # Use UA
    headers = {'User-Agent': UA}
    async with aiohttp.ClientSession(headers=headers) as session:
        url = f'{url}?{urlencode(params)}' if params else url
        print(url)
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
            else:
                print("Error:", response.status)#, await response.text())
                return None

async def parseHtml(html: str|bytes):
    soup = BeautifulSoup(html, 'html.parser')
    amphtml = soup.find('link', {'rel': 'amphtml'})
    if amphtml:
        return await parseHtml(await get(amphtml['href']))
    article = soup.find('article')
    if article:
        return article
    return soup

async def scrape(url: str|bytes):
    content = await get(url)
    return await parseHtml(content) if content else None

def cleanText(text: str|bytes):
    return '\n'.join([p.strip() for p in text.strip().split('\n\n') if p.strip()])

async def scrapeText(url: str|bytes):
    content = await scrape(url)
    #print(content)
    return cleanText(content.text) if content else None

async def main(url: str|bytes):
    content = await scrapeText(url)
    print(content)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('url', help='URL to scrape')
    args = parser.parse_args()
    asyncio.run(main(args.url))
