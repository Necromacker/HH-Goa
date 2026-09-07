# this script deploys a reverse image search on google for a given source image and scrape search results
# Updated 2026: Google Images reverse search now lives behind Google Lens.
# We navigate directly to lens.google.com/uploadbyurl and then to the
# "Exact matches" (udm=48) page instead of clicking the 2020 camera-button XPaths.
import time
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from pathlib import Path
from selenium.webdriver.chrome.options import Options
import sys


def _make_driver(webdriver_path='./chromedriver'):
    options = Options()
    options.add_argument("--incognito")
    options.add_argument("--headless=new")
    options.add_argument("window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(webdriver_path, options=options)
    try:
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass
    return driver


def main(source_url, no_results, name, timestamp, max_results, country_code, host_language):

    # number of pages processed (new Lens UI is a single scrolling page)
    pages = 1

    webdriver_path = './chromedriver'
    driver = _make_driver(webdriver_path)

    try:
        lens_url = 'https://lens.google.com/uploadbyurl?url=' + \
            urllib.parse.quote(source_url, safe='')
        print('Google Lens search: ' + lens_url)
        driver.get(lens_url)
        time.sleep(10)

        if '/sorry/' in driver.current_url:
            print('Google blocked the headless request (sorry page). '
                  'Try again later or non-headless.')
            raise RuntimeError('Google bot check')

        # find "Exact matches" link -> old "Pages that include matching images"
        exact_url = None
        try:
            for a in driver.find_elements(By.TAG_NAME, 'a'):
                try:
                    if (a.text or '').strip() == 'Exact matches' and a.get_attribute('href'):
                        exact_url = a.get_attribute('href')
                        break
                except Exception:
                    continue
        except Exception as e:
            print('Could not list links: ' + str(e))

        if exact_url:
            if exact_url.startswith('/'):
                exact_url = 'https://www.google.com' + exact_url
            print('Heading to Exact matches: ' + exact_url[:150])
            driver.get(exact_url)
            time.sleep(8)
        else:
            print('Exact matches link not found, staying on Lens overview page')

        # light scroll to trigger lazy images
        try:
            for _ in range(3):
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
        except Exception as e:
            print('Issue with scrolling ' + str(e))

        htmlcontent = driver.page_source
        Path('data/').mkdir(parents=True, exist_ok=True)
        Path('data/google/').mkdir(parents=True, exist_ok=True)
        Path('data/google/matching_pages/').mkdir(parents=True, exist_ok=True)
        Path(
            'data/google/matching_pages/htmlfiles/').mkdir(parents=True, exist_ok=True)
        Path('data/google/matching_pages/htmlfiles/' +
             name + '_' + timestamp + '/').mkdir(parents=True, exist_ok=True)
        fh = open('data/google/matching_pages/htmlfiles/' + name + '_' + timestamp + '/page_' +
                  str(pages) + '_' + country_code + '_host_lang_' +
                  host_language + '_at_' + timestamp + '.html', 'w')
        fh.write(htmlcontent)
        fh.close()
        print('Processed page ' + str(pages))

    except Exception as e:
        print(str(e) + ' search action unsuccessful')
        # still try to save whatever we have
        try:
            htmlcontent = driver.page_source
            if len(htmlcontent) > 1000:
                Path('data/google/matching_pages/htmlfiles/' +
                     name + '_' + timestamp + '/').mkdir(parents=True, exist_ok=True)
                fh = open('data/google/matching_pages/htmlfiles/' + name + '_' + timestamp + '/page_' +
                          str(pages) + '_' + country_code + '_host_lang_' +
                          host_language + '_at_' + timestamp + '.html', 'w')
                fh.write(htmlcontent)
                fh.close()
        except Exception:
            pass
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return pages


if __name__ == "__main__":
    url = sys.argv[1]
    no_results = sys.argv[2]
    name = sys.argv[3]
    timestamp = sys.argv[4]
    max_results = sys.argv[5]
    country_code = sys.argv[6]
    host_language = sys.argv[7]
    main(url, no_results, name, timestamp,
         max_results, country_code, host_language)
