import re
import asyncio
from typing import Optional, Tuple
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


async def parse_product_info(url: str) -> Optional[Tuple[str, str, str]]:
    """Определяет тип сайта и вызывает соответствующий парсер"""
    domain = urlparse(url).netloc.lower()

    try:
        if 'megamarket.ru' in domain:
            return await parse_megamarket(url)
        elif 'avito.ru' in domain:
            return await parse_avito(url)
        elif 'ozon.ru' in domain:
            return await parse_ozon(url)
        elif 'wildberries.ru' in domain:
            return await parse_wildberries(url)
        elif 'market.yandex.ru' in domain:
            return await parse_yandex_market(url)
        else:
            return await parse_generic(url)
    except Exception as e:
        print(f"Ошибка в parse_product_info: {e}")
        return None


async def parse_ozon(url: str) -> Tuple[str, str, str]:
    """Асинхронный парсинг Ozon на основе проверенного метода"""
    options = webdriver.ChromeOptions()

    # Критически важные настройки
    options.add_argument("--headless")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    # Для работы в Docker/серверных окружениях
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        await asyncio.sleep(10)  # Асинхронная задержка

        # Сохраняем HTML для отладки (опционально)
        with open("ozon_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        # Поиск названия
        try:
            title = driver.find_element("xpath", '//h1[contains(@class, "title")]').text
        except:
            try:
                title = driver.find_element("xpath", '//h1').text
            except:
                title = "Название не найдено"

        # Поиск цены с улучшенной логикой
        price = "Цена не найдена"
        try:
            # Сначала ищем основной элемент цены
            price_elements = driver.find_elements("xpath", '//*[contains(text(), "₽")]')

            # Выбираем самый вероятный элемент цены (с цифрами)
            for elem in price_elements:
                text = elem.text
                if any(c.isdigit() for c in text):
                    price = re.sub(r'[^\d₽,. ]', '', text).strip()
                    break
        except Exception as e:
            print(f"Ошибка при поиске цены: {e}")

        print(f"Успешно распарсено: {title}, {price}")
        return title, price, 'ozon.ru'

    except Exception as e:
        print(f"Ошибка парсинга Ozon: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'ozon.ru'
    finally:
        driver.quit()


async def parse_wildberries(url: str) -> Tuple[str, str, str]:
    """Финальная версия парсера Wildberries с улучшенным поиском цены"""
    options = webdriver.ChromeOptions()

    # Настройки для обхода защиты
    options.add_argument("--headless")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        await asyncio.sleep(10)  # Увеличиваем время ожидания

        # Поиск названия товара
        title = "Название не найдено"
        try:
            title_elem = driver.find_element("css selector", "h1.product-page__title")
            title = title_elem.text.strip()
        except Exception as e:
            print(f"Ошибка поиска названия: {e}")

        # Улучшенный поиск цены
        price = "Цена не найдена"
        try:
            # Основной вариант - новый дизайн
            price_elem = driver.find_element("css selector",
                                             "span.price-block__final-price, ins.price-block__final-price")
            price_text = price_elem.text.strip()

            # Альтернативный вариант - старый дизайн
            if not price_text or not any(c.isdigit() for c in price_text):
                price_elems = driver.find_elements("xpath",
                                                   "//div[contains(@class, 'price-block')]//span[contains(@class, 'final-price') or contains(text(), '₽')]")
                for elem in price_elems:
                    text = elem.text.strip()
                    if any(c.isdigit() for c in text):
                        price_text = text
                        break

            # Очистка цены
            if price_text:
                price = re.sub(r'[^\d₽]', '', price_text)
                if not price.endswith('₽'):
                    price += '₽'
        except Exception as e:
            print(f"Ошибка поиска цены: {e}")
            # Последняя попытка найти любую цену на странице
            try:
                price_elems = driver.find_elements("xpath", "//*[contains(text(), '₽')]")
                for elem in price_elems:
                    text = elem.text.strip()
                    if any(c.isdigit() for c in text):
                        price = re.sub(r'[^\d₽]', '', text)
                        if not price.endswith('₽'):
                            price += '₽'
                        break
            except:
                pass

        print(f"Wildberries: {title}, {price}")
        return title, price, 'wildberries.ru'

    except Exception as e:
        print(f"Ошибка парсинга Wildberries: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'wildberries.ru'
    finally:
        driver.quit()


async def parse_yandex_market(url: str) -> Tuple[str, str, str]:
    """Парсер для Яндекс.Маркета с поиском названия и цены"""
    options = webdriver.ChromeOptions()

    # Настройки для обхода защиты
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Имитация человеческого поведения
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.navigator.chrome = {
                    runtime: {},
                };
            """
        })

        # Открываем страницу
        driver.get(url)
        await asyncio.sleep(10)  # Ожидание загрузки

        # 1. Надежный поиск названия
        title = "Название не найдено"
        try:
            # Основные варианты селекторов для названия
            title_selectors = [
                "h1[data-zone-name='title']",  # Новый дизайн
                "h1.title",  # Старый дизайн
                "h1[itemprop='name']",  # Для микроразметки
                "div[data-apiary-widget-name='@MarketNode/Title'] h1",
                "h1"  # Крайний случай
            ]

            for selector in title_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    title = element.text.strip()
                    if title and len(title) > 3:  # Проверка на валидность
                        break
                except:
                    continue
        except Exception as e:
            print(f"Ошибка поиска названия: {e}")

        # 2. Поиск цены (как в вашем рабочем варианте)
        price = "Цена не найдена"
        try:
            # Основной вариант для нового дизайна
            price_elem = driver.find_element(
                By.CSS_SELECTOR,
                "span[data-auto='snippet-price-current'], "
                "span.ds-text.ds-text_weight_bold.ds-text_color_price-term, "
                ".price-block__final-price"
            )
            price_text = price_elem.text.strip()
            price = re.sub(r'[^\d]', '', price_text) + '₽'
        except Exception as e:
            print(f"Ошибка поиска цены: {e}")

        print(f"Яндекс.Маркет: {title}, {price}")
        return title, price, 'market.yandex.ru'

    except Exception as e:
        print(f"Ошибка парсинга Яндекс.Маркет: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'market.yandex.ru'
    finally:
        driver.quit()


async def parse_avito(url: str) -> Tuple[str, str, str]:
    """Надежный парсер для Авито с поиском названия и цены"""
    options = webdriver.ChromeOptions()

    # Настройки для обхода защиты
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        await asyncio.sleep(10)  # Ожидание полной загрузки

        # 1. Улучшенный поиск названия
        title = "Название не найдено"
        try:
            # Основные селекторы для названия на Авито
            title_selectors = [
                "h1.title-info-title",  # Основной селектор
                "h1[itemprop='name']",  # Для микроразметки
                "h1.style-title-info-title",  # Альтернативный вариант
                "h1"  # Крайний случай
            ]

            for selector in title_selectors:
                try:
                    title_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    title = title_elem.text.strip()
                    if title and len(title) > 3:  # Проверка на валидность
                        break
                except:
                    continue
        except Exception as e:
            print(f"Ошибка поиска названия: {e}")

        # 2. Точный поиск цены
        price = "Цена не найдена"
        try:
            # Вариант 1: Из атрибута content (наиболее надежный)
            price_elem = driver.find_element(By.CSS_SELECTOR, "span[itemprop='price']")
            price_content = price_elem.get_attribute("content")

            if price_content and price_content.isdigit():
                price = f"{int(price_content):,d} ₽".replace(",", " ")
            else:
                # Вариант 2: Из текста элемента
                price_text = price_elem.text.strip()
                price = re.sub(r'[^\d]', '', price_text)
                if price:
                    price = f"{int(price):,d} ₽".replace(",", " ")

        except Exception as e:
            print(f"Ошибка поиска цены: {e}")
            try:
                # Вариант 3: Альтернативный поиск
                price_elem = driver.find_element(By.CSS_SELECTOR, "span[data-marker='item-price']")
                price_text = price_elem.text.strip()
                price = re.sub(r'[^\d]', '', price_text)
                if price:
                    price = f"{int(price):,d} ₽".replace(",", " ")
            except:
                pass

        print(f"Авито: {title}, {price}")
        return title, price, 'avito.ru'

    except Exception as e:
        print(f"Ошибка парсинга Авито: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'avito.ru'
    finally:
        driver.quit()


async def parse_megamarket(url: str) -> Tuple[str, str, str]:
    """Финальная версия парсера для MegaMarket"""
    options = webdriver.ChromeOptions()

    # Настройки для обхода защиты
    options.add_argument("--headless=new")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        await asyncio.sleep(15)  # Увеличенное время ожидания

        # 1. Точный поиск названия
        title = "Название не найдено"
        try:
            # Основные селекторы для названия
            title_selectors = [
                "h1.item-page__title",  # Основной селектор
                "h1.dtitle",  # Альтернативный вариант
                "h1.title",  # Дополнительный вариант
                "h1"  # Крайний случай
            ]

            for selector in title_selectors:
                try:
                    title_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    title = title_elem.text.strip()
                    if title and len(title) > 3:  # Проверка на валидность
                        break
                except:
                    continue
        except Exception as e:
            print(f"Ошибка поиска названия: {e}")

        # 2. Точный поиск цены
        price = "Цена не найдена"
        try:
            # Основные селекторы для цены
            price_selectors = [
                "meta[itemprop='price']",  # Из мета-тега (надежный вариант)
                "span.sales-block-offer-price__price-final",  # Из текста
                "div.item-price__final",  # Альтернативный блок
                "span.price-block__final-price"  # Дополнительный вариант
            ]

            for selector in price_selectors:
                try:
                    price_elem = driver.find_element(By.CSS_SELECTOR, selector)

                    # Пробуем получить из content
                    price_content = price_elem.get_attribute("content")
                    if price_content and price_content.isdigit():
                        price = f"{int(price_content):,d} ₽".replace(",", " ")
                        break

                    # Если нет content, берем текст
                    price_text = price_elem.text.strip()
                    if price_text:
                        clean_price = re.sub(r'[^\d]', '', price_text)
                        if clean_price:
                            price = f"{int(clean_price):,d} ₽".replace(",", " ")
                            break
                except:
                    continue
        except Exception as e:
            print(f"Ошибка поиска цены: {e}")

        print(f"MegaMarket: {title}, {price}")
        return title, price, 'megamarket.ru'

    except Exception as e:
        print(f"Ошибка парсинга MegaMarket: {e}")
        return "Ошибка парсинга", "Ошибка парсинга", 'megamarket.ru'
    finally:
        # Для отладки сохраняем HTML
        with open("megamarket_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.quit()


async def parse_aliexpress(url: str) -> Tuple[str, str, str]:
    """Парсинг товаров с AliExpress"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Название товара
        try:
            title = soup.find('h1').text.strip()
        except:
            title = "Название не найдено"

        # Цена
        try:
            price = soup.find('div', class_='es--wrap--erdmPRe').text.strip()
            price = re.sub(r'[^\d₽,. ]', '', price).strip()
        except:
            price = "Цена не найдена"

        return title, price, 'aliexpress.ru'


async def parse_generic(url: str) -> Tuple[str, str, str]:
    """Базовый парсинг для других сайтов"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    domain = urlparse(url).netloc.lower()

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Название товара (пробуем найти h1)
        try:
            title = soup.find('h1').text.strip()
        except:
            title = "Название не найдено"

        # Цена (ищем элемент с символом ₽ или руб)
        price = "Цена не найдена"
        for elem in soup.find_all(string=re.compile(r'₽|руб|руб\.')):
            price_text = elem.text.strip()
            if any(c.isdigit() for c in price_text):
                price = re.sub(r'[^\d₽,. ]', '', price_text).strip()
                break

        return title, price, domain