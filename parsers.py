import re
import asyncio
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=ru-RU")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # Пробуем пути к Chrome
    possible_chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/lib/chromium-browser/chrome",
        "/usr/bin/chromium",
        "/opt/google/chrome/chrome"
    ]
    chrome_found = False
    for path in possible_chrome_paths:
        if os.path.exists(path):
            options.binary_location = path
            logger.info(f"Using Chrome binary at: {path}")
            chrome_found = True
            break
    if not chrome_found:
        logger.error("No Chrome binary found in expected paths")
        return "Ошибка: Chrome не найден", "Ошибка: Chrome не найден", 'ozon.ru'

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })

        # Загружаем страницу
        driver.get(url)
        await asyncio.sleep(5)  # Задержка для JavaScript
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Логируем заголовок
        page_title = driver.find_element(By.TAG_NAME, "title").text
        logger.info(f"Page title: {page_title}")

        # Проверяем блокировку
        if "доступ ограничен" in page_title.lower() or "captcha" in page_title.lower():
            logger.error("Обнаружена блокировка или капча")
            html_file = f"html/ozon_page_{url.split('/')[-2]}.html"
            os.makedirs("html", exist_ok=True)
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info(f"HTML сохранён в {html_file}")
            driver.quit()
            return "Блокировка доступа", "Цена не найдена", 'ozon.ru'

        # Поиск названия
        title = "Название не найдено"
        try:
            title_elem = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "div[data-widget='webProductHeading'] h1, h1.tsHeadline3, h1"
                ))
            )
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия на Ozon: {e}")

        # Поиск цены
        price = "Цена не найдена"
        try:
            price_elem = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "span.mp7_28, span[class*='price'], div[class*='price'] span:contains('₽')"
                ))
            )
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d\s]', '', price_text).strip() + ' ₽'
        except Exception as e:
            logger.error(f"Ошибка поиска цены на Ozon: {e}")

        # Сохраняем HTML
        try:
            html_dir = "html"
            os.makedirs(html_dir, exist_ok=True)
            html_file = f"{html_dir}/ozon_page_{url.split('/')[-2]}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info(f"HTML сохранён в {html_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения HTML: {e}")

        logger.info(f"Успешно распарсено Ozon: {title}, {price}")
        return title, price, 'ozon.ru'

    except Exception as e:
        logger.error(f"Ошибка парсинга Ozon: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'ozon.ru'
    finally:
        driver.quit()

async def parse_wildberries(url: str) -> Tuple[str, str, str]:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/google-chrome"

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        title = "Название не найдено"
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h1.product-page__title")
            title = title_elem.text.strip()
        except Exception as e:
            logger.error(f"Ошибка поиска названия: {e}")

        price = "Цена не найдена"
        try:
            price_elem = driver.find_element(
                By.CSS_SELECTOR,
                "span.price-block__final-price, ins.price-block__final-price"
            )
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d]', '', price_text) + ' ₽'
        except Exception as e:
            logger.error(f"Ошибка поиска цены: {e}")

        logger.info(f"Wildberries: {title}, {price}")
        return title, price, 'wildberries.ru'

    except Exception as e:
        logger.error(f"Ошибка парсинга Wildberries: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'wildberries.ru'
    finally:
        driver.quit()

async def parse_yandex_market(url: str) -> Tuple[str, str, str]:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/google-chrome"

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        title = "Название не найдено"
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, "h1[data-zone-name='title']")
            title = title_elem.text.strip()
        except:
            try:
                title_elem = driver.find_element(By.TAG_NAME, "h1")
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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/google-chrome"

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/google-chrome"

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
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