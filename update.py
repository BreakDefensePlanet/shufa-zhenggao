# -*- coding: utf-8 -*-
"""
墨讯 · 书法征稿信息站 —— 自动更新脚本
抓取搜狗微信搜索的征稿启事 → 解析截稿日期/级别 → 更新 index.html 的 DATA/OVER 数组
用法: python update.py  (脚本与 index.html 同目录)
容错: 抓取失败或无有效数据时保持原文件不变
"""
import urllib.request, urllib.parse, re, json, sys, os, io, datetime, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE, 'index.html')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'}

KEYWORDS = [
    '{year}年{month}月 全国书法美术征稿启事 汇总',
    '书法大赛 征稿启事 截稿 {year}',
    '中国书法家协会 征稿启事 {year}',
    '硬笔书法 征稿启事 {year}',
    '书法展览 征稿启事 {year} 截稿日期',
]

PROVINCES = ['北京','天津','上海','重庆','河北','山西','辽宁','吉林','黑龙江','江苏','浙江','安徽',
             '福建','江西','山东','河南','湖北','湖南','广东','海南','四川','贵州','云南','陕西',
             '甘肃','青海','台湾','内蒙古','广西','西藏','宁夏','新疆','香港','澳门']

def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    for a, b in [('&ldquo;', '"'), ('&rdquo;', '"'), ('&middot;', '·'), ('&nbsp;', ' '),
                 ('&amp;', '&'), ('&#39;', "'"), ('&mdash;', '-'), ('&bull;', '·'),
                 ('&rarr;', '→'), ('&quot;', '"'), ('&hellip;', '…')]:
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip()

def parse_deadline(text):
    """从文本提取截稿日期，返回 'YYYY-MM-DD' 或 None"""
    if not text:
        return None
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        return '%04d-%02d-%02d' % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if m:
        return '%04d-%02d-%02d' % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # 月.日 形式（无年份，按当年）
    m = re.search(r'(?:截稿|截止)[^0-9]{0,6}(\d{1,2})[.月](\d{1,2})日?', text)
    if m:
        return '%04d-%02d-%02d' % (datetime.date.today().year, int(m.group(1)), int(m.group(2)))
    m = re.search(r'(\d{1,2})[.月](\d{1,2})日?(?:截稿|截止)', text)
    if m:
        return '%04d-%02d-%02d' % (datetime.date.today().year, int(m.group(1)), int(m.group(2)))
    return None

def guess_tags(title):
    tags = []
    if '中书协' in title or '中国书法家协会' in title:
        tags.append('中书协')
    if '硬笔' in title:
        tags.append('硬笔')
    if re.search(r'青少年|少儿|小学生|中学生|大学生|儿童', title):
        tags.append('青少年')
    if '全国' in title:
        tags.append('全国')
    for p in PROVINCES:
        if p in title and '全国' not in title:
            tags.append('省级')
            break
    if not tags:
        tags.append('全国')
    if '市级' not in tags and not any(t in tags for t in ['中书协', '全国', '省级']):
        tags.append('市级')
    return tags[:3]

def extract_prize(summary):
    if '入会条件' in summary:
        return '入展可作为加入书法家协会（或相关协会）的条件之一'
    m = re.search(r'奖金.{0,30}万', summary)
    if m:
        return '总奖金约' + m.group(0).replace('奖金', '') + '元'
    if '免费' in summary or '不收' in summary:
        return '不收参评费'
    return ''

def extract_points(title, summary):
    pts = []
    if summary:
        s = summary.replace('获取最新最全的书法征稿启事', '').strip()
        if s:
            pts.append(s[:70] + ('…' if len(s) > 70 else ''))
    if '截稿' in title or '截止' in title:
        pts.append('以官方征稿启事为准')
    return pts[:3] or ['以官方征稿启事为准']

def normalize_title(t):
    """标题归一化生成匹配 key：去前缀、去括号内容、去启事词、去日期尾巴、去引号分隔符"""
    t = re.sub(r'^【[^】]*】\s*', '', t)
    t = re.sub(r'^[^：:|丨]{0,18}[:：|丨]', '', t)          # 去"书画赛事丨""截稿日期…|"前缀
    t = re.sub(r'^\([^)]*\)\s*', '', t)
    t = re.sub(r'^\d+[.、]\s*', '', t)
    t = t.replace('（', '(').replace('）', ')')
    t = re.sub(r'\([^)]*\)', '', t)                        # 去所有括号内容（含截稿日期）
    t = re.sub(r'(征稿启事|征稿通知|征集启事|征稿启示|征稿|启事)', '', t)  # 全局删启事词
    t = re.sub(r'\d{4}年\d{1,2}月\d{1,2}日$', '', t)       # 删日期尾巴
    t = re.sub(r'(\d{1,2})[.月](\d{1,2})日?$', '', t)      # 删 9.30 形式尾巴
    t = re.sub(r'[|丨・·―—\-–_：:]', '', t)
    for ch in ['「', '」', '『', '』', '"', '"', "'", '’', '‘', ' ', '　']:
        t = t.replace(ch, '')
    return t[:20]

def extract_org(title):
    """从标题提取主办方/地区信息"""
    m = re.search(r'【([^】]{1,14})征稿】', title)
    if m:
        return m.group(1) + '（待核实）'
    m = re.search(r'([\u4e00-\u9fa5]{2,10}(?:书法家协会|书协|美术家协会|文联|美术馆|书画院|研究院|文化馆))', title)
    if m:
        return m.group(1)
    return '待核实（以官方为准）'

def fetch_items():
    now = datetime.date.today()
    kw_list = [k.format(year=now.year, month=now.month) for k in KEYWORDS]
    items, seen = [], set()
    for kw in kw_list:
        try:
            url = 'https://weixin.sogou.com/weixin?type=2&query=' + urllib.parse.quote(kw)
            text = fetch(url).decode('utf-8', 'replace')
            blocks = re.findall(r'<li id="sogou_vr_11002601_box_[^"]*".*?</li>', text, re.S)
            for b in blocks:
                tm = re.search(r'<h3>\s*<a[^>]*>(.*?)</a>', b, re.S)
                sm = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', b, re.S)
                if not tm:
                    continue
                title = clean(tm.group(1))
                summary = clean(sm.group(1)) if sm else ''
                if not title or '汇总' in title or '最新' in title:
                    continue  # 跳过汇总/资讯帖，只收具体征稿启事
                key = normalize_title(title)
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append({'title': title, 'summary': summary})
            print('  ✓', kw, '→', len(blocks), '条')
        except Exception as e:
            print('  ✗', kw, '失败:', e)
        time.sleep(2)
    return items

def load_existing():
    """从 index.html 读现有 DATA/OVER（JS 对象数组 → 转合法 JSON）"""
    try:
        html = open(INDEX, encoding='utf-8').read()
        m = re.search(r'var DATA = (\[.*?\]);\n', html, re.S)
        n = re.search(r'var OVER = (\[.*?\]);\n', html, re.S)

        def js2json(txt):
            try:
                return json.loads(txt)  # 脚本自己写入的是合法 JSON，直接解析
            except Exception:
                # 旧版 JS 字面量（人工首次迁移）：去行注释 + 键加引号 + 单引号字符串转双引号
                txt = re.sub(r'(?m)^\s*//.*$', '', txt)
                txt = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', txt)
                txt = txt.replace("'", '"')
                return json.loads(txt)

        data = js2json(m.group(1)) if m else []
        over = js2json(n.group(1)) if n else []
        return data, over
    except Exception as e:
        print('读取现有数据失败:', e)
        return [], []

def merge_items(fetched, existing, old_over):
    today = datetime.date.today().isoformat()

    # 1. 现有条目按 key 索引（existing 在前 = 人工条目优先）
    uniq = {}
    for it in existing:
        uniq.setdefault(normalize_title(it['name']), it)

    # 2. 新抓取条目：匹配到人工条目则继承信息（更新截稿日），否则新建
    for f in fetched:
        dl = parse_deadline(f['title'] + ' ' + f['summary'])
        if not dl:
            continue
        key = normalize_title(f['title'])
        base = uniq.get(key)
        if base:
            base['deadline'] = dl  # 保留人工条目的简洁名称和信息，只更新截稿日
        else:
            # 清理抓取标题：去【】/书画赛事丨前缀、括号内容、启事尾巴
            name = re.sub(r'^【[^】]*】\s*', '', f['title'])
            name = re.sub(r'^[^：:|丨]{0,18}[:：|丨]', '', name)
            name = re.sub(r'\([^)]*\)', '', name)
            name = re.sub(r'(征稿启事|征稿通知|征集启事|征稿启示|征稿|启事)$', '', name)
            name = re.sub(r'^\d+[.、]\s*', '', name).strip()
            uniq[key] = {
                'name': name,
                'org': extract_org(f['title']),
                'deadline': dl,
                'prize': extract_prize(f['summary']),
                'points': extract_points(f['title'], f['summary']),
                'tags': guess_tags(f['title']),
                'source': '自动抓取 · 以官方为准',
            }

    # 3. 分 DATA（征稿中）/ OVER（已截止）
    items = list(uniq.values())
    data = [it for it in items if it['deadline'] >= today]
    over = [it for it in items if it['deadline'] < today]
    data.sort(key=lambda x: x['deadline'])
    over.sort(key=lambda x: x['deadline'], reverse=True)

    # 4. 合并原 OVER 中未出现的条目（防丢），去重限 30 条
    over_map = {normalize_title(it['name']): it for it in over}
    for it in old_over:
        over_map.setdefault(normalize_title(it['name']), it)
    over_list = sorted(over_map.values(), key=lambda x: x['deadline'], reverse=True)[:30]
    return data, over_list

def write_index(data, over, update_date):
    html = open(INDEX, encoding='utf-8').read()
    djson = json.dumps(data, ensure_ascii=False, indent=1)
    ojson = json.dumps(over, ensure_ascii=False, indent=1)
    html, n1 = re.subn(r'var DATA = \[.*?\];\n', 'var DATA = ' + djson + ';\n', html, count=1, flags=re.S)
    html, n2 = re.subn(r'var OVER = \[.*?\];\n', 'var OVER = ' + ojson + ';\n', html, count=1, flags=re.S)
    # 更新日期标记
    html, n3 = re.subn(r'数据更新于 <b>\d{4}年\d{1,2}月\d{1,2}日</b>',
                       '数据更新于 <b>' + update_date + '</b>', html, count=1)
    if n1 == 0 or n2 == 0:
        raise RuntimeError('index.html 中未找到 DATA/OVER 标记，拒绝写入')
    open(INDEX, 'w', encoding='utf-8').write(html)
    return n1, n2, n3

def main():
    print('墨讯自动更新 ·', datetime.date.today())
    print('抓取搜狗微信搜索…')
    fetched = fetch_items()
    print('抓取条目数:', len(fetched))
    if not fetched:
        print('无有效抓取结果，保持原文件不变')
        return 1
    data, over = load_existing()
    print('现有数据: DATA', len(data), '条 / OVER', len(over), '条')
    merged, over_list = merge_items(fetched, data, over)
    print('合并后: DATA', len(merged), '条 / OVER', len(over_list), '条')
    if len(merged) < 3:
        print('数据异常（少于3条），拒绝写入')
        return 1
    d = datetime.date.today()
    update_date = '%d年%d月%d日' % (d.year, d.month, d.day)
    n1, n2, n3 = write_index(merged, over_list, update_date)
    print(f'写入完成: DATA标记替换{n1} / OVER标记替换{n2} / 日期更新{n3}')
    print('OK')
    return 0

if __name__ == '__main__':
    sys.exit(main())
