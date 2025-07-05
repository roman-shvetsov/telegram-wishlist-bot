import re
import asyncio
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_fixed
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cache = TTLCache(maxsize=100, ttl=3600)
semaphore = asyncio.Semaphore(5)

async def parse_product_info(url: str) -> Optional[dict]:
    if url in cache:
        logger.info(f"Using cached result for {url}")
        return cache[url]

    async with semaphore:
        domain = urlparse(url).netloc.lower()
        try:
            if 'ozon.ru' in domain:
                result = await parse_ozon(url)
            elif 'wildberries.ru' in domain:
                result = await parse_wildberries(url)
            elif 'market.yandex.ru' in domain or 'ya.cc' in domain:
                result = await parse_yandex_market(url)
            elif 'aliexpress.ru' in domain or 'aliexpress.com' in domain:
                result = await parse_aliexpress(url)
            elif 'avito.ru' in domain:
                result = await parse_avito(url)
            else:
                result = await parse_generic(url)

            if result and not result.get('error'):
                cache[url] = result
            return result
        except Exception as e:
            logger.error(f"Error in parse_product_info: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': domain}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_ozon(url: str) -> dict:
    logger.info(f"Parsing Ozon: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.ozon.ru/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if 'доступ ограничен' in response.text.lower() or 'captcha' in response.text.lower():
                logger.error("Detected block or CAPTCHA on Ozon")
                return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'ozon.ru'}

            title = "Название не найдено"
            title_elem = soup.select_one('div[data-widget="webProductHeading"] h1, h1.tsHeadline550Medium, h1')
            if title_elem:
                title = title_elem.text.strip()

            price = "Цена не указана"
            price_elem = soup.select_one('span[data-auto="main-price"] span, span.mp7_28, span.tsHeadline500Medium, span.c-price__value')
            if price_elem:
                price_text = price_elem.text.strip()
                price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'

            logger.info(f"Ozon parsed: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'ozon.ru'}
        except Exception as e:
            logger.error(f"Ozon parsing error: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'ozon.ru'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_wildberries(url: str) -> dict:
    logger.info(f"Parsing Wildberries: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.wildberries.ru/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if 'капча' in response.text.lower() or 'доступ ограничен' in response.text.lower():
                logger.error("Detected block or CAPTCHA on Wildberries")
                return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'wildberries.ru'}

            title = "Название не найдено"
            title_elem = soup.select_one('h1.product-page__header, h1[itemprop="name"], h1, span[data-link="text{:product^name}"]')
            if title_elem:
                title = title_elem.text.strip()

            price = "Цена не указана"
            price_elem = soup.select_one('span.price-block__price, ins.price-block__price-final, span.current-price, span[data-testid="price-current"], span.price__current')
            if price_elem:
                price_text = price_elem.text.strip()
                price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'

            logger.info(f"Wildberries parsed: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'wildberries.ru'}
        except Exception as e:
            logger.error(f"Wildberries parsing error: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'wildberries.ru'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_yandex_market(url: str) -> dict:
    logger.info(f"Parsing Yandex Market: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://market.yandex.ru/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if 'captcha' in response.text.lower() or 'showcaptcha' in str(response.url).lower():
                logger.error("Detected CAPTCHA on Yandex Market")
                return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'market.yandex.ru'}

            title = "Название не найдено"
            title_elem = soup.select_one('h1[data-zone-name="title"], h1, div[data-zone-name="title"] h1, h1._1TJjA')
            if title_elem:
                title = title_elem.text.strip()

            price = "Цена не указана"
            price_elem = soup.select_one('span[data-auto="main-price"], span[data-auto="snippet-price-current"], span.price-block__final-price, div[data-auto="offer-price"] span, span._1oBlN')
            if price_elem:
                price_text = price_elem.text.strip()
                price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'

            logger.info(f"Yandex Market parsed: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'market.yandex.ru'}
        except Exception as e:
            logger.error(f"Yandex Market parsing error: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'market.yandex.ru'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_aliexpress(url: str) -> dict:
    logger.info(f"Parsing AliExpress: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.aliexpress.ru/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            title = "Название не найдено"
            title_elem = soup.select_one('h1, div.product-title, span[itemprop="name"]')
            if title_elem:
                title = title_elem.text.strip()

            price = "Цена не указана"
            price_elem = soup.select_one('div.current-price, span[itemprop="price"], div.price-block__price')
            if price_elem:
                price_text = price_elem.text.strip()
                price = re.sub(r'[^\d,.]', '', price_text).replace(',', '.').strip() + ' ₽'

            logger.info(f"AliExpress parsed: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'aliexpress.ru'}
        except Exception as e:
            logger.error(f"AliExpress parsing error: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'aliexpress.ru'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_avito(url: str) -> dict:
    logger.info(f"Parsing Avito: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.avito.ru/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if 'доступ ограничен' in response.text.lower() or 'captcha' in response.text.lower():
                logger.error("Detected block or CAPTCHA on Avito")
                return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'avito.ru'}

            title = "Название не найдено"
            title_elem = soup.select_one('h1.title-info-title, h1[itemprop="name"]')
            if title_elem:
                title = title_elem.text.strip()

            price = "Цена не указана"
            price_elem = soup.select_one('span[itemprop="price"], div.price-value span')
            if price_elem:
                price_text = price_elem.get('content') or price_elem.text.strip()
                price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'

            logger.info(f"Avito parsed: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'avito.ru'}
        except Exception as e:
            logger.error(f"Avito parsing error: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': 'avito.ru'}

async def parse_generic(url: str) -> dict:
    logger.info(f"Parsing generic site: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    domain = urlparse(url).netloc.lower()
    async with httpx.AsyncClient(http2=True) as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            title = "Название не найдено"
            title_elem = soup.select_one('h1, title, meta[name="title"], meta[property="og:title"]')
            if title_elem:
                title = title_elem.text.strip() if title_elem.name != 'meta' else title_elem.get('content', '').strip()

            price = "Цена не указана"
            for elem in soup.find_all(string=re.compile(r'₽|руб|руб\.|RUB')):
                price_text = elem.text.strip() if isinstance(elem, BeautifulSoup.NavigableString) else elem
                if any(c.isdigit() for c in price_text):
                    price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
                    break

            logger.info(f"Generic parsed: {title}, {price}, {domain}")
            return {'title': title, 'price': price, 'domain': domain}
        except Exception as e:
            logger.error(f"Generic parsing error: {e}")
            return {'title': 'Название не найдено', 'price': 'Цена не указана', 'domain': domain}