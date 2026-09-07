# this script deploys a reverse image search on yandex for a given source image and scrapes 'Sites containing information about the image'
# Updated 2026: navigate directly to yandex images searchbyimage URL.
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


def main(source_url, no_results, name, timestamp):

    # number of pages processed
    pages = 1

    webdriver_path = './chromedriver'
    driver = _make_driver(webdriver_path)

    yandex_isearch = 'https://yandex.com/images/search?rpt=imageview&url=' + \
        urllib.parse.quote(source_url, safe='')

    try:
        print('Yandex search: ' + yandex_isearch[:150])
        driver.get(yandex_isearch)
        time.sleep(8)
    except Exception as e:
        print(e)

        # container: //*[@id="CbirSites_infinite-NzQkc36"]/section

        # fetch data

    # third step: scroll down as long as result amount corresponds with wished result
    results = []
    try:
        scroll_counter = 1
        while len(results) < int(no_results):
            old_amount_results = len(results)
            print('Current amount of results : ' + str(len(results)))
            results = driver.find_elements_by_css_selector(
                ".CbirSites-Item")
            driver.execute_script(
                "window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(5)
            # driver.execute_script(
            #     "window.scrollTo(0," + str(500 * scroll_counter) + ")")
            # time.sleep(1)
            scroll_counter = scroll_counter + 1
            if old_amount_results == len(results):
                print('After ' + str(scroll_counter) +
                      ' scrolls amount is the same')
                break
    except Exception as e:
        print('Issue with scrolling ' + str(e))

    # fourth step: save html data
    try:
        time.sleep(3)
        htmlcontent = driver.page_source
        Path('data/').mkdir(parents=True, exist_ok=True)
        Path('data/yandex/').mkdir(parents=True, exist_ok=True)
        Path('data/yandex/info_pages/').mkdir(parents=True, exist_ok=True)
        Path(
            'data/yandex/info_pages/htmlfiles/').mkdir(parents=True, exist_ok=True)
        Path('data/yandex/info_pages/htmlfiles/' +
             name + '/').mkdir(parents=True, exist_ok=True)
        fh = open('data/yandex/info_pages/htmlfiles/' +
                  name + '/' + timestamp + '.html', 'w')
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
    timestamp = sys.argv[4]
    # max_results = sys.argv[5]
    # country_code = sys.argv[6]
    # host_language = sys.argv[7]
    main(url, no_results, name, timestamp)
