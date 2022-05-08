#!/usr/bin/python
# coding=utf-8

import sqlite3

from flask import Flask, render_template, jsonify, request
import requests
import numpy as np
import pandas as pd
import re
import json
from jieba.analyse.tfidf import TFIDF
from bs4 import BeautifulSoup
import util


app = Flask(__name__)
app.config.from_object('config')

login_name = None

# 全局读取数据
category = []
title = []
url = []
click_count = []

with open('all_news_info.json', 'r', encoding='utf8') as f:
    for line in f:
        sample = json.loads(line.strip())
        category.append(sample['category'])
        news_title = sample['title'].split('_网易')[0]
        title.append(news_title)
        url.append(sample['url'])
        click_count.append(sample['click_count'])

news_df = pd.DataFrame({'category': category, 'title': title, 'url': url, 'click_count': click_count})
news_df = news_df.sort_values(by='click_count', ascending=False)
print('所有新闻版块：', news_df['category'].unique())

# 中文停用词
STOPWORDS = set(map(lambda x: x.strip(), open('stopwords.txt').readlines()))


class WordSegmentPOSKeywordExtractor(TFIDF):

    def extract_sentence(self, sentence, keyword_ratios=None):
        """
        Extract keywords from sentence using TF-IDF algorithm.
        Parameter:
            - keyword_ratios: return how many top keywords. `None` for all possible words.
        """
        words = self.postokenizer.cut(sentence)
        freq = {}

        seg_words = []
        pos_words = []
        for w in words:
            wc = w.word
            seg_words.append(wc)
            pos_words.append(w.flag)

            if len(wc.strip()) < 2 or wc.lower() in self.stop_words:
                continue
            freq[wc] = freq.get(wc, 0.0) + 1.0

        if keyword_ratios is not None and keyword_ratios > 0:
            total = sum(freq.values())
            for k in freq:
                freq[k] *= self.idf_freq.get(k, self.median_idf) / total

            tags = sorted(freq, key=freq.__getitem__, reverse=True)
            top_k = int(keyword_ratios * len(seg_words))
            tags = tags[:top_k]

            key_words = [int(word in tags) for word in seg_words]

            return seg_words, pos_words, key_words
        else:
            return seg_words, pos_words


extractor = WordSegmentPOSKeywordExtractor()


def fetch_keywords(new_title):
    """新闻关键词抽取，保留表征能力强名词和动词"""
    seg_words, pos_words, key_words = extractor.extract_sentence(new_title, keyword_ratios=0.8)
    seg_key_words = []
    for word, pos, is_key in zip(seg_words, pos_words, key_words):
        if pos in {'n', 'nt', 'nd', 'nl', 'nh', 'ns', 'nn', 'ni', 'nz', 'v', 'vd', 'vl', 'vu', 'a'} and is_key:
            if word not in STOPWORDS:
                seg_key_words.append(word)

    return seg_key_words


news_df['title_cut'] = news_df['title'].map(fetch_keywords)


# --------------------- html render ---------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/weibo_hot_rank')
def weibo_hot_rank():
    return render_template('weibo_hot_rank.html')


@app.route('/news_category')
def news_category():
    return render_template('news_category.html')


@app.route('/hot_words')
def hot_words():
    return render_template('hot_words.html')


@app.route('/hot_news')
def hot_news():
    return render_template('hot_news.html')


# ------------------ ajax restful api -------------------
@app.route('/check_login')
def check_login():
    """判断用户是否登录"""
    return jsonify({'username': login_name, 'login': login_name is not None})


@app.route('/register/<name>/<password>')
def register(name, password):
    conn = sqlite3.connect('user_info.db')
    cursor = conn.cursor()

    check_sql = "SELECT * FROM sqlite_master where type='table' and name='user'"
    cursor.execute(check_sql)
    results = cursor.fetchall()
    # 数据库表不存在
    if len(results) == 0:
        # 创建数据库表
        sql = """
                CREATE TABLE user(
                    name CHAR(256), 
                    password CHAR(256)
                );
                """
        cursor.execute(sql)
        conn.commit()
        print('创建数据库表成功！')

    sql = "INSERT INTO user (name, password) VALUES (?,?);"
    cursor.executemany(sql, [(name, password)])
    conn.commit()
    return jsonify({'info': '用户注册成功！', 'status': 'ok'})


@app.route('/login/<name>/<password>')
def login(name, password):
    global login_name
    conn = sqlite3.connect('user_info.db')
    cursor = conn.cursor()

    check_sql = "SELECT * FROM sqlite_master where type='table' and name='user'"
    cursor.execute(check_sql)
    results = cursor.fetchall()
    # 数据库表不存在
    if len(results) == 0:
        # 创建数据库表
        sql = """
                CREATE TABLE user(
                    name CHAR(256), 
                    password CHAR(256)
                );
                """
        cursor.execute(sql)
        conn.commit()
        print('创建数据库表成功！')

    sql = "select * from user where name='{}' and password='{}'".format(name, password)
    cursor.execute(sql)
    results = cursor.fetchall()

    login_name = name
    if len(results) > 0:
        print(results)
        return jsonify({'info': name + '用户登录成功！', 'status': 'ok'})
    else:
        return jsonify({'info': '当前用户不存在！', 'status': 'error'})


@app.route('/get_news_by_category/<category>')
def get_news_by_category(category):
    cate_df = news_df[news_df['category'] == category]
    return jsonify(cate_df.values.tolist())


@app.route('/news_words_analysis/<category>')
def news_words_analysis(category):
    cate_df = news_df[news_df['category'] == category]

    word_count = {}
    for key_words in cate_df['title_cut']:
        for word in key_words:
            if word in word_count:
                word_count[word] += 1
            else:
                word_count[word] = 1

    wordclout_dict = sorted(word_count.items(), key=lambda d: d[1], reverse=True)
    wordclout_dict = [{"name": k[0], "value": k[1]} for k in wordclout_dict]

    # 选取 top10 的词作为话题词群
    top_keywords = [w['name'] for w in wordclout_dict[:10]][::-1]
    top_keyword_counts = [w['value'] for w in wordclout_dict[:10]][::-1]

    click_counts = cate_df['click_count'].values
    max_click_count = max(click_counts.tolist())
    min_click_count = min(click_counts.tolist())
    click_counts = (click_counts - min(click_counts)) / (max(click_counts) - min(click_counts)) * 100

    cate_mean_click_count_df = news_df[['category', 'click_count']].groupby(by='category').mean().reset_index()
    all_category = cate_mean_click_count_df['category'].values.tolist()
    mean_click_count = cate_mean_click_count_df['click_count'].values.tolist()

    return jsonify({'词云数据': wordclout_dict, '词群': top_keywords, '词群个数': top_keyword_counts,
                    'top10': cate_df.values.tolist()[:10], 'click_counts': click_counts.tolist(),
                    'max_click_count': max_click_count, 'min_click_count': min_click_count,
                    'all_category': all_category, 'mean_click_count': mean_click_count
                    })


@app.route('/get_weibo_hot_rank')
def get_weibo_hot_rank():
    """获取微博的热搜信息"""
    url = 'https://tophub.today/n/KqndgxeLl9'
    headers = {
        'user-agent': util.get_random_user_agent(),
    }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf8'
    html = response.text
    soup = BeautifulSoup(html, 'lxml')
    table = soup.find('table', class_='table')
    tbody = table.tbody

    trs = tbody.find_all('tr')

    hot_infos = []
    for tr in trs:
        tds = tr.find_all('td')
        hot_info = {'content': tds[1].text, 'hot_score': tds[2].text, 'href': tds[1].a['href']}
        print(hot_info)
        hot_infos.append(hot_info)

    return jsonify(hot_infos)


if __name__ == "__main__":
    app.run(host='127.0.0.1')




