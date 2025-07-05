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

# Кэш для результатов парсинга (хранит результаты 1 час)
cache = TTLCache(maxsize=100, ttl=3600)

# Семафор для ограничения одновременных запросов
semaphore = asyncio.Semaphore(5)

async def parse_product_info(url: str) -> Optional[dict]:
    """Определяет тип сайта и вызывает соответствующий парсер"""
    if url in cache:
        logger.info(f"Используем кэшированный результат для {url}")
        return cache[url]

    async with semaphore:
        domain = urlparse(url).netloc.lower()
        try:
            if 'ozon.ru' in domain:
                result = await parse_ozon(url)
            elif 'wildberries.ru' in domain:
                result = await parse_wildberries(url)
            elif 'market.yandex.ru' in domain:
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
            logger.error(f"Ошибка в parse_product_info: {e}")
            return {'error': 'Не удалось распознать товар. Проверьте ссылку.'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_ozon(url: str) -> dict:
    logger.info(f"Парсинг Ozon: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Проверка на блокировку
            if 'доступ ограничен' in response.text.lower() or 'captcha' in response.text.lower():
                logger.error("Обнаружена блокировка или CAPTCHA на Ozon")
                return {'error': 'Блокировка доступа или CAPTCHA'}

            # Поиск названия
            title = "Название не найдено"
            try:
                title_elem = soup.select_one('div[data-widget="webProductHeading"] h1, h1.tsHeadline550Medium, h1')
                if title_elem:
                    title = title_elem.text.strip()
            except Exception as e:
                logger.error(f"Ошибка поиска названия на Ozon: {e}")

            # Поиск цены
            price = "Цена не указана"
            try:
                price_elem = soup.select_one('span[data-auto="main-price"] span, span.mp7_28, span.tsHeadline500Medium, span.c-price__value')
                if price_elem:
                    price_text = price_elem.text.strip()
                    price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
            except Exception as e:
                logger.error(f"Ошибка поиска цены на Ozon: {e}")

            logger.info(f"Ozon: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'ozon.ru'}
        except Exception as e:
            logger.error(f"Ошибка парсинга Ozon: {e}")
            return {'error': 'Не удалось распознать товар на Ozon'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_wildberries(url: str) -> dict:
    logger.info(f"Парсинг Wildberries: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Проверка на блокировку
            if 'капча' in response.text.lower() or 'доступ ограничен' in response.text.lower():
                logger.error("Обнаружена блокировка или CAPTCHA на Wildberries")
                return {'error': 'Блокировка доступа или CAPTCHA'}

            # Поиск названия
            title = "Название не найдено"
            try:
                title_elem = soup.select_one('h1.product-page__header, h1[itemprop="name"], h1, span[data-link="text{:product^name}"]')
                if title_elem:
                    title = title_elem.text.strip()
            except Exception as e:
                logger.error(f"Ошибка поиска названия на Wildberries: {e}")

            # Поиск цены
            price = "Цена не указана"
            try:
                price_elem = soup.select_one('span.price-block__price, ins.price-block__price-final, span.current-price, span[data-testid="price-current"], span.price__current')
                if price_elem:
                    price_text = price_elem.text.strip()
                    price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
            except Exception as e:
                logger.error(f"Ошибка поиска цены на Wildberries: {e}")

            logger.info(f"Wildberries: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'wildberries.ru'}
        except Exception as e:
            logger.error(f"Ошибка парсинга Wildberries: {e}")
            return {'error': 'Не удалось распознать товар на Wildberries'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_yandex_market(url: str) -> dict:
    logger.info(f"Парсинг Яндекс.Маркет: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Проверка на блокировку
            if 'captcha' in response.text.lower() or 'доступ ограничен' in response.text.lower():
                logger.error("Обнаружена блокировка или CAPTCHA на Яндекс.Маркет")
                return {'error': 'Блокировка доступа или CAPTCHA'}

            # Поиск названия
            title = "Название не найдено"
            try:
                title_elem = soup.select_one('h1[data-zone-name="title"], h1, div[data-zone-name="title"] h1, h1._1TJjA')
                if title_elem:
                    title = title_elem.text.strip()
            except Exception as e:
                logger.error(f"Ошибка поиска названия на Яндекс.Маркет: {e}")

            # Поиск цены
            price = "Цена не указана"
            try:
                price_elem = soup.select_one('span[data-auto="main-price"], span[data-auto="snippet-price-current"], span.price-block__final-price, div[data-auto="offer-price"] span, span._1oBlN')
                if price_elem:
                    price_text = price_elem.text.strip()
                    price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
            except Exception as e:
                logger.error(f"Ошибка поиска цены на Яндекс.Маркет: {e}")

            logger.info(f"Яндекс.Маркет: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'market.yandex.ru'}
        except Exception as e:
            logger.error(f"Ошибка парсинга Яндекс.Маркет: {e}")
            return {'error': 'Не удалось распознать товар на Яндекс.Маркет'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_aliexpress(url: str) -> dict:
    logger.info(f"Парсинг AliExpress: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Поиск названия
            title = "Название не найдено"
            try:
                title_elem = soup.select_one('h1, div.product-title, span[itemprop="name"]')
                if title_elem:
                    title = title_elem.text.strip()
            except Exception as e:
                logger.error(f"Ошибка поиска названия на AliExpress: {e}")

            # Поиск цены
            price = "Цена не указана"
            try:
                price_elem = soup.select_one('div.current-price, span[itemprop="price"], div.price-block__price')
                if price_elem:
                    price_text = price_elem.text.strip()
                    price = re.sub(r'[^\d,.]', '', price_text).replace(',', '.').strip() + ' ₽'
            except Exception as e:
                logger.error(f"Ошибка поиска цены на AliExpress: {e}")

            logger.info(f"AliExpress: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'aliexpress.ru'}
        except Exception as e:
            logger.error(f"Ошибка парсинга AliExpress: {e}")
            return {'error': 'Не удалось распознать товар на AliExpress'}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def parse_avito(url: str) -> dict:
    logger.info(f"Парсинг Avito: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Проверка на блокировку
            if 'доступ ограничен' in response.text.lower() or 'captcha' in response.text.lower():
                logger.error("Обнаружена блокировка или CAPTCHA на Avito")
                return {'error': 'Блокировка доступа или CAPTCHA'}

            # Поиск названия
            title = "Название не найдено"
            try:
                title_elem = soup.select_one('h1.title-info-title, h1[itemprop="name"]')
                if title_elem:
                    title = title_elem.text.strip()
            except Exception as e:
                logger.error(f"Ошибка поиска названия на Avito: {e}")

            # Поиск цены
            price = "Цена не указана"
            try:
                price_elem = soup.select_one('span[itemprop="price"], div.price-value span')
                if price_elem:
                    price_text = price_elem.get('content') or price_elem.text.strip()
                    price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
            except Exception as e:
                logger.error(f"Ошибка поиска цены на Avito: {e}")

            logger.info(f"Avito: {title}, {price}")
            return {'title': title, 'price': price, 'domain': 'avito.ru'}
        except Exception as e:
            logger.error(f"Ошибка парсинга Avito: {e}")
            return {'error': 'Не удалось распознать товар на Avito'}

async def parse_generic(url: str) -> dict:
    logger.info(f"Парсинг общего сайта: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    domain = urlparse(url).netloc.lower()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Поиск названия
            title = "Название не найдено"
            try:
                title_elem = soup.select_one('h1, title, meta[name="title"], meta[property="og:title"]')
                if title_elem:
                    title = title_elem.text.strip() if title_elem.name != 'meta' else title_elem.get('content', '').strip()
            except Exception as e:
                logger.error(f"Ошибка поиска названия: {e}")

            # Поиск цены
            price = "Цена не указана"
            try:
                for elem in soup.find_all(string=re.compile(r'₽|руб|руб\.|RUB')):
                    price_text = elem.text.strip() if isinstance(elem, BeautifulSoup.NavigableString) else elem
                    if any(c.isdigit() for c in price_text):
                        price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
                        break
            except Exception as e:
                logger.error(f"Ошибка поиска цены: {e}")

            logger.info(f"Общий парсер: {title}, {price}, {domain}")
            return {'title': title, 'price': price, 'domain': domain}
        except Exception as e:
            logger.error(f"Ошибка парсинга общего сайта: {e}")
            return {'error': 'Не удалось распознать товар'}