# this script enables to retrieve similar image data of an image  as proposed by Google reverse image search

from itertools import count
import time
from selenium import webdriver
from pathlib import Path
from selenium.webdriver.chrome.options import Options
import datetime
from bs4 import BeautifulSoup
import csv
import sys
import yandex_similar_images_html_scraper
import thumbnail_decoder
import json


def main(source_url, no_results, name):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    # use existing timestamp to change csv without scraping data from scratch
    # timestamp = '2022-03-05_21-58-35'

    # first step: conduct reverse image search and store html files
    # add on: if data has been scraped you can uncomment this line, adapt timestamp respectively and pass same name
    yandex_similar_images_html_scraper.main(
        source_url, no_results, name, timestamp)

    # from html data retrieve relevant data as csv file

    # list to store search results
    search_results = []

    html_dir = 'data/yandex/similar_images/htmlfiles/' + name + '/'
    csv_dir = 'data/yandex/similar_images/csvfiles/' + name + '/'
    thumb_dir = 'data/yandex/similar_images/thumbnails/' + name + '_' + timestamp + '/'

    # open html file
    fname = html_dir + timestamp + '.html'

    with open(fname, 'r') as f:
        page_content = f.read()
        soup = BeautifulSoup(page_content, 'html.parser')
        f.close()

        # old 2020 layout
        results = soup.find_all(
            'div', {'class': 'serp-item'})
        # new layout: div.CbirSimilarList-Thumb
        if not results:
            results = soup.find_all(class_='CbirSimilarList-Thumb')
        print('Found ' + str(len(results)) + ' results')

        for result in results:
            search_result = {}
            print('Processing search result no ' +
                  str(len(search_results) + 1))

            search_result['rank'] = len(search_results)

            # new layout parsing
            if 'CbirSimilarList-Thumb' in (result.get('class') or []):
                try:
                    import urllib.parse as _up
                    a = result.find('a', href=True)
                    href = a['href'] if a else None
                    page_url = None
                    thumb_url = None
                    title = None
                    if href:
                        if href.startswith('/'):
                            href = 'https://yandex.com' + href
                        q = _up.urlparse(href)
                        qs = _up.parse_qs(q.query)
                        # original site url is in img_url param
                        if 'img_url' in qs:
                            page_url = qs['img_url'][0]
                        # thumbnail is in url param (avatars...) or background-image
                        if 'url' in qs:
                            thumb_url = qs['url'][0]
                            if thumb_url.startswith('//'):
                                thumb_url = 'https:' + thumb_url
                    # title from aria-label
                    inner = result.find(attrs={'aria-label': True})
                    if inner:
                        title = inner.get('aria-label')
                    if not thumb_url:
                        div_img = result.find(class_='Thumb-Image')
                        if div_img is not None and div_img.has_attr('style'):
                            import re as _re
                            m = _re.search(r'url\(["\']?(//[^"\')]+)', div_img['style'])
                            if m:
                                thumb_url = 'https:' + m.group(1)
                    search_result['url'] = page_url
                    try:
                        search_result['domain'] = page_url.replace(
                            'https://', '').replace('http://', '').replace('www.', '').split('/')[0] if page_url else None
                    except Exception:
                        search_result['domain'] = None
                    try:
                        search_result['country_code_tld'] = search_result['domain'].split('.')[-1] if search_result['domain'] else None
                    except Exception:
                        search_result['country_code_tld'] = None
                    search_result['title'] = title
                    search_result['thumbnail_url'] = thumb_url
                except Exception as e:
                    print('New-layout parse error: ' + str(e))
                    search_result['url'] = None
                    search_result['domain'] = None
                    search_result['country_code_tld'] = None
                    search_result['title'] = None
                    search_result['thumbnail_url'] = None
            else:
                data = None
                try:
                    data = json.loads(result['data-bem'])
                except Exception as e:
                    print(' json error: ' + str(e))

                try:
                    search_result['url'] = data['serp-item']['snippet']['url']
                except Exception as e:
                    search_result['url'] = None
                    print('No url found ' + str(e))

                try:
                    search_result['domain'] = data['serp-item']['snippet']['domain']
                except Exception as e:
                    search_result['domain'] = None
                    print('No domain found ' + str(e))

                try:
                    search_result['country_code_tld'] = search_result['domain'].split(
                        '.')[-1]
                except Exception as e:
                    search_result['country_code_tld'] = None
                    print('No country code found ' + str(e))

                try:
                    search_result['title'] = result.find(
                        'img', {'class': 'serp-item__thumb'})['alt']
                except Exception as e:
                    search_result['title'] = None
                    print('No title found ' + str(e))

                try:
                    search_result['thumbnail_url'] = 'https:' + result.find(
                        'img', {'class': 'serp-item__thumb'})['src']
                except Exception as e:
                    search_result['thumbnail_url'] = None
                    print('No thumbnail url found ' + str(e))

            search_results.append(search_result)
            if len(search_results) >= int(no_results):
                break

        f.close()
    # store data
    Path('data/yandex/similar_images/csvfiles/').mkdir(parents=True, exist_ok=True)
    Path(csv_dir).mkdir(parents=True, exist_ok=True)
    fname_csv = csv_dir + str(len(search_results)) + \
        '_results_scraped_at_' + timestamp + '.csv'
    if not search_results:
        print('No results found, writing empty csv')
        search_results = [{'rank': 0, 'url': None, 'domain': None,
                           'country_code_tld': None, 'title': None,
                           'thumbnail_url': None}]
    keys = search_results[0].keys()
    with open(fname_csv, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(search_results)
        output_file.close()

    # sixth step: from csv file retrieve thumbnails
    thumbnail_decoder.main(fname_csv, thumb_dir)


if __name__ == "__main__":
    url = sys.argv[1]
    no_results = sys.argv[2]
    name = sys.argv[3]
    main(url, no_results, name)
