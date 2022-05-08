#!/usr/bin/python
# _*_ coding: utf-8 _*_

"""
新闻数据爬虫
"""
import time
import json
import chardet
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup


def get_html(url):
    headers = {
        'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36 Edg/79.0.309.56"
    }
    response = requests.get(url, headers=headers)
    encode = chardet.detect(response.content)
    response.encoding = 'gbk' if encode['encoding'] == 'GB2312' else 'utf8'
    return response.text


root_url = 'https://news.163.com/rank/'
html = get_html(root_url)
soup = BeautifulSoup(html, 'lxml')
subNav = soup.find('div', class_='subNav')
all_categories = subNav.find_all('a')

# 网易新闻的所有版块和对应的链接
all_categories_map = {}
for category in all_categories:
    all_categories_map[category.text.strip()] = category['href']
print(all_categories_map)

file_out = open('all_news_info.json', 'w', encoding='utf-8')

news_infoes = []
# 分别爬取每个版块的热门新闻
for category in all_categories_map:
    cate_url = all_categories_map[category]
    print('--> 爬取 {} 版块：{}'.format(category, cate_url))
    html = get_html(cate_url)
    soup = BeautifulSoup(html, 'lxml')
    items = soup.find_all('tr')

    news_title_set = set()
    for item in tqdm(items):
        try:
            tds = item.select('td')
            if len(tds) < 2:
                continue

            news_url = tds[0].a['href']

            news_soup = BeautifulSoup(get_html(news_url), 'lxml')
            if news_soup.title is None or news_soup.title.string.strip() == '':
                news_title = tds[0].a.text.strip()
            else:
                news_title = news_soup.title.string

            if '_网易新闻' in news_title:
                news_title = news_title.replace('_网易新闻', '')

            # 避免新闻爬取重复
            if news_title in news_title_set:
                continue
            news_title_set.add(news_title)

            click_count = int(tds[1].text.strip())

            news_info = {'category': category, 'title': news_title, 'url': news_url, 'click_count': click_count}
            news_infoes.append(news_info)
            if len(news_infoes) == 10:
                file_out.writelines([json.dumps(info, ensure_ascii=False) + '\n' for info in news_infoes])
                file_out.flush()
                news_infoes.clear()
            time.sleep(0.5)
        except:
            continue

if len(news_infoes) > 0:
    file_out.writelines([json.dumps(info) + '\n' for info in news_infoes])
    file_out.flush()
