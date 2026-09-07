# this script enables to retrieve similar image data of an image  as proposed by Google reverse image search
# Updated 2026: use Google Lens uploadbyurl -> "Visual matches" (udm=44).
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


def main(source_url, no_results, name, country_code, host_language, timestamp):

    webdriver_path = './chromedriver'
    driver = _make_driver(webdriver_path)

    try:
        lens_url = 'https://lens.google.com/uploadbyurl?url=' + \
            urllib.parse.quote(source_url, safe='')
        print('Google Lens search: ' + lens_url)
        driver.get(lens_url)
        time.sleep(10)

        visual_url = None
        try:
            for a in driver.find_elements(By.TAG_NAME, 'a'):
                try:
                    if (a.text or '').strip() == 'Visual matches' and a.get_attribute('href'):
                        visual_url = a.get_attribute('href')
                        break
                except Exception:
                    continue
        except Exception as e:
            print('Could not list links: ' + str(e))

        if visual_url:
            if visual_url.startswith('/'):
                visual_url = 'https://www.google.com' + visual_url
            print('Heading to Visual matches')
            driver.get(visual_url)
            time.sleep(8)
        else:
            print('Visual matches link not found, staying on Lens overview page')

    except Exception as e:
        print('Issue with searching for source url')
        print(e)

    # third step: scroll down as long as result amount corresponds with wished result
    results = []
    try:
        while len(results) < int(no_results):
            old_amount_results = len(results)
            print('Current amount of results : ' + str(len(results)))
            # old 2020 selector + several new Lens selectors
            results = driver.find_elements(By.CSS_SELECTOR, "div.isv-r")
            if not results:
                results = driver.find_elements(By.CSS_SELECTOR, "div[data-ved]")
            driver.execute_script(
                "window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(5)
            if old_amount_results == len(results):
                break
    except Exception as e:
        print('Issue with scrolling ' + str(e))

    # fourth step: save html data
    try:
        time.sleep(3)
        htmlcontent = driver.page_source
        Path('data/').mkdir(parents=True, exist_ok=True)
        Path('data/google/').mkdir(parents=True, exist_ok=True)
        Path('data/google/similar_images/').mkdir(parents=True, exist_ok=True)
        Path(
            'data/google/similar_images/htmlfiles/').mkdir(parents=True, exist_ok=True)
        Path('data/google/similar_images/htmlfiles/' +
             name + '/').mkdir(parents=True, exist_ok=True)
        fh = open('data/google/similar_images/htmlfiles/' + name + '/country_code_' +
                  country_code + '_host_lang_' + host_language + '_at_' + timestamp + '.html', 'w')
        fh.write(htmlcontent)
        fh.close()

    except Exception as e:
        print('Issue with saving html')
        print(e)

    # close driver when finished
    driver.quit()


if __name__ == "__main__":
    url = sys.argv[1]
    no_results = sys.argv[2]
    name = sys.argv[3]
    country_code = sys.argv[4]
    host_language = sys.argv[5]
    timestamp = sys.argv[6]

    main(url, no_results, name, country_code, host_language, timestamp)
