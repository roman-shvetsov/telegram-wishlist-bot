import re
import asyncio
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from cachetools import TTLCache
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Кэш для результатов парсинга (хранит результаты 1 час)
cache = TTLCache(maxsize=100, ttl=3600)

# Семафор для ограничения одновременных парсингов
semaphore = asyncio.Semaphore(2)

async def parse_product_info(url: str) -> Optional[Tuple[str, str, str]]:
    """Определяет тип сайта и вызывает соответствующий парсер"""
    if url in cache:
        logger.info(f"Используем кэшированный результат для {url}")
        return cache[url]

    async with semaphore:
        domain = urlparse(url).netloc.lower()
        try:
            if 'megamarket.ru' in domain:
                result = await parse_megamarket(url)
            elif 'avito.ru' in domain:
                result = await parse_avito(url)
            elif 'ozon.ru' in domain:
                result = await parse_ozon(url)
            elif 'wildberries.ru' in domain:
                result = await parse_wildberries(url)
            elif 'market.yandex.ru' in domain:
                result = await parse_yandex_market(url)
            else:
                result = await parse_generic(url)

            if result:
                cache[url] = result
            return result
        except Exception as e:
            logger.error(f"Ошибка в parse_product_info: {e}")
            return None

async def parse_ozon(url: str) -> Tuple[str, str, str]:
    logger.info(f"Парсинг Ozon: {url}")
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")
    options.add_argument("--proxy-server=http://161.35.98.111:8080")  # Замени на свой прокси

    driver = None
    try:
        driver = uc.Chrome(options=options)
        logger.info(f"Driver initialized for Ozon: {url}")
        driver.get(url)
        await asyncio.sleep(10)  # Увеличено для прокси
        WebDriverWait(driver, 90).until(  # Увеличен таймаут
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Прокрутка
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(3)

        # Логируем HTML
        html_snippet = driver.page_source[:1000]
        logger.info(f"HTML snippet: {html_snippet}")

        # Логируем заголовок
        try:
            page_title = driver.find_element(By.TAG_NAME, "title").text
            logger.info(f"Page title: {page_title}")
        except Exception as e:
            logger.error(f"Ошибка получения заголовка: {e}")
            page_title = ""

        # Проверяем блокировку
        if any(x in (page_title.lower() + html_snippet.lower()) for x in ["доступ ограничен", "captcha", "подозрительн"]):
            logger.error("Обнаружена блокировка или CAPTCHA")
            html_dir = "html"
            os.makedirs(html_dir, exist_ok=True)
            html_file = f"{html_dir}/ozon_page_{url.split('/')[-2]}.html"
            try:
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info(f"HTML saved to {html_file}")
                files = os.listdir(html_dir)
                logger.info(f"Files in html dir: {files}")
            except Exception as e:
                logger.error(f"Error saving HTML: {e}")
            return "Блокировка доступа", "Цена не найдена", 'ozon'

        # Поиск названия
        title = "Название не найдено"
        try:
            title_elem = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "div[data-widget='webProductHeading'] h1, h1.tsHeadline550Medium, h1"
                ))
            )
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        # Поиск цены
        price = "Цена не найдена"
        try:
            price_elem = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "span[data-auto='main-price'] span, span.mp7_28, div[class*='price'] span"
                ))
            )
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        # Сохраняем HTML
        html_dir = "html"
        os.makedirs(html_dir, exist_ok=True)
        html_file = f"{html_dir}/ozon_page_{url.split('/')[-2]}.html"
        try:
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info(f"HTML saved to {html_file}")
            files = os.listdir(html_dir)
            logger.info(f"Files in html dir: {files}")
        except Exception as e:
            logger.error(f"Error saving HTML: {e}")

        logger.info(f"Получено: {title}, {price}")
        return title, price, 'ozon'

    except Exception as e:
        logger.error(f"Ошибка парсинга Ozon: {e}")
        # Сохраняем HTML при ошибке
        if driver:
            html_dir = "html"
            os.makedirs(html_dir, exist_ok=True)
            html_file = f"{html_dir}/ozon_page_{url.split('/')[-2]}_error.html"
            try:
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info(f"Error HTML saved to {html_file}")
                files = os.listdir(html_dir)
                logger.info(f"Files in html dir: {files}")
            except Exception as e2:
                logger.error(f"Error saving error HTML: {e2}")
        return "Ошибка парсинга", "Ошибка", 'ozon'
    finally:
        if driver:
            driver.quit()

async def parse_wildberries(url: str) -> Tuple[str, str, str]:
    logger.info(f"Парсинг Wildberries: {url}")
    # Очищаем кэш для этой ссылки
    if url in cache:
        del cache[url]
        logger.info(f"Кэш очищен для {url}")

    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")
    options.add_argument("--proxy-server=http://161.35.98.111:8080")  # Замени на свой прокси

    driver = None
    try:
        driver = uc.Chrome(options=options)
        logger.info(f"Driver initialized for Wildberries: {url}")
        driver.get(url)
        await asyncio.sleep(10)  # Увеличено для прокси
        WebDriverWait(driver, 90).until(  # Увеличен таймаут
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Прокрутка
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(3)

        # Логируем HTML
        html_snippet = driver.page_source[:1000]
        logger.info(f"HTML snippet: {html_snippet}")

        # Логируем заголовок
        try:
            page_title = driver.find_element(By.TAG_NAME, "title").text
            logger.info(f"Page title: {page_title}")
        except Exception as e:
            logger.error(f"Ошибка получения заголовка: {e}")
            page_title = ""

        # Проверяем блокировку
        if any(x in (page_title.lower() + html_snippet.lower()) for x in ["капча", "подозрительн"]):
            logger.error("Обнаружена блокировка или CAPTCHA")
            html_dir = "html"
            os.makedirs(html_dir, exist_ok=True)
            html_file = f"{html_dir}/wb_page_{url.split('/')[-2]}.html"
            try:
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info(f"HTML saved to {html_file}")
                files = os.listdir(html_dir)
                logger.info(f"Files in html dir: {files}")
            except Exception as e:
                logger.error(f"Error saving HTML: {e}")
            return "Блокировка доступа", "Цена не найдена", 'wildberries.ru'

        # Поиск названия
        title = "Название не найдено"
        try:
            title_elem = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "h1.product-page__header, h1[itemprop='name'], h1"
                ))
            )
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        # Поиск цены
        price = "Цена не найдена"
        try:
            price_elem = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "span.price-block__price, ins.price-block__price-final, span.current-price, span[data-testid='price-current']"
                ))
            )
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        # Сохраняем HTML
        html_dir = "html"
        os.makedirs(html_dir, exist_ok=True)
        html_file = f"{html_dir}/wb_page_{url.split('/')[-2]}.html"
        try:
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info(f"HTML saved to {html_file}")
            files = os.listdir(html_dir)
            logger.info(f"Files in html dir: {files}")
        except Exception as e:
            logger.error(f"Error saving HTML: {e}")

        logger.info(f"Wildberries: {title}, {price}")
        return title, price, 'wildberries.ru'

    except Exception as e:
        logger.error(f"Ошибка парсинга Wildberries: {e}")
        # Сохраняем HTML при ошибке
        if driver:
            html_dir = "html"
            os.makedirs(html_dir, exist_ok=True)
            html_file = f"{html_dir}/wb_page_{url.split('/')[-2]}_error.html"
            try:
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info(f"Error HTML saved to {html_file}")
                files = os.listdir(html_dir)
                logger.info(f"Files in html dir: {files}")
            except Exception as e2:
                logger.error(f"Error saving error HTML: {e2}")
        return "Ошибка парсинга", "Ошибка парсинга", 'wildberries.ru'
    finally:
        if driver:
            driver.quit()

async def parse_yandex_market(url: str) -> Tuple[str, str, str]:
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")

    try:
        driver = uc.Chrome(options=options)
        driver.get(url)
        await asyncio.sleep(5)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        title = "Название не найдено"
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h1[data-zone-name='title'], h1")
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        price = "Цена не найдена"
        try:
            price_elem = driver.find_element(
                By.CSS_SELECTOR,
                "span[data-auto='snippet-price-current'], span.price-block__final-price"
            )
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d]', '', price_text) + ' ₽'
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        logger.info(f"Яндекс.Маркет: {title}, {price}")
        return title, price, 'market.yandex.ru'

    except Exception as e:
        logger.error(f"Ошибка парсинга Яндекс.Маркет: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'market.yandex.ru'
    finally:
        driver.quit()

async def parse_avito(url: str) -> Tuple[str, str, str]:
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")

    try:
        driver = uc.Chrome(options=options)
        driver.get(url)
        await asyncio.sleep(5)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        title = "Название не найдено"
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h1.title-info-title")
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        price = "Цена не найдена"
        try:
            price_elem = driver.find_element(By.CSS_SELECTOR, "span[itemprop='price']")
            price_content = price_elem.get_attribute("content")
            if price_content and price_content.isdigit():
                price = f"{int(price_content):,d} ₽".replace(",", " ")
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        logger.info(f"Авито: {title}, {price}")
        return title, price, 'avito.ru'

    except Exception as e:
        logger.error(f"Ошибка парсинга Авито: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'avito.ru'
    finally:
        driver.quit()

async def parse_megamarket(url: str) -> Tuple[str, str, str]:
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")

    try:
        driver = uc.Chrome(options=options)
        driver.get(url)
        await asyncio.sleep(5)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        title = "Название не найдено"
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h1.item-page__title")
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        price = "Цена не найдена"
        try:
            price_elem = driver.find_element(By.CSS_SELECTOR, "meta[itemprop='price']")
            price_content = price_elem.get_attribute("content")
            if price_content and price_content.isdigit():
                price = f"{int(price_content):,d} ₽".replace(",", " ")
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        logger.info(f"MegaMarket: {title}, {price}")
        return title, price, 'megamarket.ru'

    except Exception as e:
        logger.error(f"Ошибка парсинга MegaMarket: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'megamarket.ru'
    finally:
        driver.quit()

async def parse_aliexpress(url: str) -> Tuple[str, str, str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')

        title = "Название не найдено"
        try:
            title_elem = soup.find('h1')
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия на AliExpress: {e}")

        price = "Цена не найдена"
        try:
            price_elem = soup.find('div', class_='es--wrap--erdmPRe')
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d,.]', '', price_text).replace(',', '.') + ' ₽'
        except Exception as e:
            logger.error(f"Ошибка поиска цены на AliExpress: {e}")

        return title, price, 'aliexpress.ru'

async def parse_generic(url: str) -> Tuple[str, str, str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    }

    domain = urlparse(url).netloc.lower()

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')

        title = "Название не найдено"
        try:
            title_elem = soup.find('h1')
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        price = "Цена не найдена"
        try:
            for elem in soup.find_all(string=re.compile(r'₽|руб|руб\.')):
                price_text = elem.text.strip()
                if any(c.isdigit() for c in price_text):
                    price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
                    break
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        return title, price, domain