"""Small server-rendered entry view and localized metadata for the JS application.

The browser enhances the same routes. Known source URLs retain meaningful HTML,
canonical URLs and hreflang links without running JavaScript.
"""
from __future__ import annotations
import html
import json
import re
from urllib.parse import urlencode, urlsplit, urlunsplit

LOCALES = ('zh-Hant', 'en', 'ja', 'ko')
WORDS = {
    'en': {'brand': 'Harmonica Observatory', 'home': 'Home', 'events': 'Events', 'post': 'Posts', 'source': 'Sources', 'scores': 'Scores', 'feeds': 'Subscribe', 'status': 'System status', 'contribute': 'Contribute API capacity', 'submit': 'Suggest a source', 'about': 'About', 'privacy': 'Privacy', 'description': 'Discover public harmonica events, artists, ensembles, clubs and scores around the world. Browse original sources across countries and languages.', 'original': 'Original sources', 'latest': 'Latest public posts', 'all': 'Browse all sources'},
    'zh-Hant': {'brand': '口琴觀測站', 'home': '首頁', 'events': '活動', 'post': '貼文', 'source': '來源', 'scores': '樂譜', 'feeds': '訂閱', 'status': '系統狀態', 'contribute': '貢獻 API 額度', 'submit': '回報來源', 'about': '關於', 'privacy': '隱私', 'description': '探索全球公開口琴活動、演奏者、樂團、社團與樂譜資訊，跨越國家與語言瀏覽原始來源，保留原文與活動時區。', 'original': '原始來源', 'latest': '最新公開貼文', 'all': '瀏覽所有來源'},
    'ja': {'brand': 'ハーモニカ観測所', 'home': 'ホーム', 'events': 'イベント', 'post': '投稿', 'source': '情報源', 'scores': '楽譜', 'feeds': '購読', 'status': '稼働状況', 'contribute': 'API 枠を提供', 'submit': '情報源を提案', 'about': 'このサイトについて', 'privacy': 'プライバシー', 'description': '世界のハーモニカイベント、演奏家、アンサンブル、クラブ、楽譜を探す公開情報サイト。国や言語を越えて原文と情報源を確認できます。', 'original': '元の情報源', 'latest': '最新の公開投稿', 'all': 'すべての情報源を見る'},
    'ko': {'brand': '하모니카 관측소', 'home': '홈', 'events': '행사', 'post': '게시물', 'source': '정보 출처', 'scores': '악보', 'feeds': '구독', 'status': '시스템 상태', 'contribute': 'API 할당량 기여', 'submit': '출처 제안', 'about': '소개', 'privacy': '개인정보', 'description': '전 세계 하모니카 행사, 연주자, 앙상블, 동아리와 악보를 탐색하세요. 국가와 언어를 넘어 원문과 공개 출처를 확인할 수 있습니다.', 'original': '원본 출처', 'latest': '최신 공개 게시물', 'all': '모든 출처 보기'},
}


SCORE_GUIDE = {
    'en': ('Find & buy music', 'Find books, sales announcements, music libraries and enquiry contacts.'),
    'zh-Hant': ('找譜與購譜', '找一本譜集、查看販售公告，或到曲庫與團隊網站詢問樂譜。'),
    'ja': ('楽譜の入手先', '楽譜集、販売案内、曲庫や問い合わせ先を探せます。'),
    'ko': ('악보 찾기·구매', '악보집, 판매 공지, 곡목 자료실과 문의처를 찾아보세요.'),
}
ORIGINAL_DESCRIPTION = {'en': 'Original description', 'zh-Hant': '原文說明',
                        'ja': '紹介文の原文', 'ko': '소개 원문'}
WEBSITE_LABEL = {'en': 'Website', 'zh-Hant': '網站', 'ja': 'ウェブサイト', 'ko': '웹사이트'}
STORY_LABEL = {'en': 'Instagram story', 'zh-Hant': 'Instagram 限時動態',
               'ja': 'Instagram ストーリー', 'ko': 'Instagram 스토리'}

# Locale order follows LOCALES. Keep the no-JavaScript source view consistent
# with the browser's country-only facet, without translating proper place names.
COUNTRY_NAMES = {
    'AR': ('阿根廷', 'Argentina', 'アルゼンチン', '아르헨티나'),
    'AU': ('澳洲', 'Australia', 'オーストラリア', '오스트레일리아'),
    'BR': ('巴西', 'Brazil', 'ブラジル', '브라질'),
    'CA': ('加拿大', 'Canada', 'カナダ', '캐나다'),
    'CH': ('瑞士', 'Switzerland', 'スイス', '스위스'),
    'CN': ('中國', 'China', '中国', '중국'),
    'CZ': ('捷克', 'Czechia', 'チェコ', '체코'),
    'DE': ('德國', 'Germany', 'ドイツ', '독일'),
    'DK': ('丹麥', 'Denmark', 'デンマーク', '덴마크'),
    'ES': ('西班牙', 'Spain', 'スペイン', '스페인'),
    'FR': ('法國', 'France', 'フランス', '프랑스'),
    'GB': ('英國', 'United Kingdom', 'イギリス', '영국'),
    'HK': ('香港', 'Hong Kong', '香港', '홍콩'),
    'ID': ('印尼', 'Indonesia', 'インドネシア', '인도네시아'),
    'IL': ('以色列', 'Israel', 'イスラエル', '이스라엘'),
    'IN': ('印度', 'India', 'インド', '인도'),
    'IT': ('義大利', 'Italy', 'イタリア', '이탈리아'),
    'JP': ('日本', 'Japan', '日本', '일본'),
    'KR': ('韓國', 'South Korea', '韓国', '대한민국'),
    'MX': ('墨西哥', 'Mexico', 'メキシコ', '멕시코'),
    'MY': ('馬來西亞', 'Malaysia', 'マレーシア', '말레이시아'),
    'NL': ('荷蘭', 'Netherlands', 'オランダ', '네덜란드'),
    'NO': ('挪威', 'Norway', 'ノルウェー', '노르웨이'),
    'NZ': ('紐西蘭', 'New Zealand', 'ニュージーランド', '뉴질랜드'),
    'PH': ('菲律賓', 'Philippines', 'フィリピン', '필리핀'),
    'PL': ('波蘭', 'Poland', 'ポーランド', '폴란드'),
    'RU': ('俄羅斯', 'Russia', 'ロシア', '러시아'),
    'SE': ('瑞典', 'Sweden', 'スウェーデン', '스웨덴'),
    'SG': ('新加坡', 'Singapore', 'シンガポール', '싱가포르'),
    'TW': ('臺灣', 'Taiwan', '台湾', '대만'),
    'US': ('美國', 'United States', 'アメリカ合衆国', '미국'),
    'ZA': ('南非', 'South Africa', '南アフリカ', '남아프리카 공화국'),
    'WORLD': ('國際', 'International', '国際', '국제'),
    'ONLINE': ('線上', 'Online', 'オンライン', '온라인'),
    'UNKNOWN': ('尚未標示', 'Not specified', '未指定', '미지정'),
}


def normalize_locale(value: str) -> str:
    value = str(value or '').replace('_', '-').lower()
    if value.startswith('zh'):
        return 'zh-Hant'
    for lang in ('en', 'ja', 'ko'):
        if value == lang or value.startswith(lang + '-'):
            return lang
    return 'en'


def e(value: object) -> str:
    return html.escape(str(value or ''), quote=True)


def source_name(source: dict, locale: str) -> str:
    names = source.get('names') if isinstance(source.get('names'), dict) else {}
    return str(names.get(locale) or (source.get('nameEn') if locale == 'en' else '')
               or source.get('name') or source.get('id') or WORDS[locale]['source'])


def source_share_image(source: dict, origin: str) -> str:
    """Use only an existing catalog avatar in the public local avatar directory."""
    avatar = source.get('avatar')
    if not isinstance(avatar, str) or not re.fullmatch(
        r'/assets/source-avatars/[A-Za-z0-9_-]+\.(?:avif|gif|jpe?g|png|webp)', avatar
    ):
        return ''
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {'https', 'http'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return ''
        return urlunsplit((parsed.scheme, parsed.netloc, avatar, '', ''))
    except ValueError:
        return ''


def source_country(source: dict, locale: str) -> str:
    code = str(source.get('countryCode') or 'UNKNOWN').upper()
    names = COUNTRY_NAMES.get(code)
    return names[LOCALES.index(locale)] if names else str(source.get('country') or code)


def source_link_label(link: dict, locale: str) -> str:
    label = str(link.get('label') or link.get('url') or '')
    return WEBSITE_LABEL[locale] if label == '網站' else label


def post_title(post: dict, locale: str) -> str:
    title = str(post.get('title') or '')
    if post.get('isStory') and post.get('platform') == 'instagram':
        generated = re.fullmatch(r'Instagram story (@[A-Za-z0-9_.]+)', title)
        if generated:
            return STORY_LABEL[locale] + ' ' + generated.group(1)
    return title


def render_document(template: str, path: str, catalog: dict, origin: str, locale: str = 'en') -> str:
    locale = normalize_locale(locale)
    words = WORDS[locale]
    route = path.strip('/').split('/')[0] or 'home'
    route_id = path.rstrip('/').rsplit('/', 1)[-1]
    source = next((s for s in catalog.get('sources', []) if s.get('url') == path or
                   (path.startswith(('/source/', '/post/source/')) and
                    (str(s.get('id')) == route_id or
                     str(s.get('url') or '').rstrip('/').rsplit('/', 1)[-1] == route_id))), None)
    canonical_path = (source.get('url') or path) if source else path
    page = source_name(source, locale) if source else words.get(route, words['home'])
    summaries = source.get('summaries', {}) if source else {}
    localized_summary = summaries.get(locale) if isinstance(summaries, dict) else ''
    description = (localized_summary or source.get('summary') or words['description']) if source else words['description']
    score_guide = path.rstrip('/') == '/scores/sources'
    if score_guide:
        page, description = SCORE_GUIDE[locale]
    title = page + ' · ' + words['brand']
    canonical = origin.rstrip('/') + canonical_path
    canonical += '?' + urlencode({'lang': locale})
    document = re.sub(r'<html\b[^>]*>', '<html lang="' + locale + '">', template, count=1)
    document = re.sub(r'<title>.*?</title>', lambda _: '<title>' + e(title) + '</title>', document, count=1, flags=re.S)
    document = re.sub(r'<meta\s+name=["\']description["\'][^>]*>', '', document, flags=re.I)
    document = re.sub(r'<link\s+rel=["\']canonical["\'][^>]*>', '', document, flags=re.I)
    head = '\n<meta name="description" content="' + e(description) + '">\n'
    head += '<link rel="canonical" href="' + e(canonical) + '">\n'
    for language in LOCALES:
        href = origin.rstrip('/') + canonical_path + '?' + urlencode({'lang': language})
        head += '<link rel="alternate" hreflang="' + language + '" href="' + e(href) + '">\n'
    head += '<meta property="og:site_name" content="' + e(words['brand']) + '">\n'
    head += '<meta property="og:title" content="' + e(title) + '">\n'
    head += '<meta property="og:description" content="' + e(description) + '">\n'
    head += '<meta property="og:url" content="' + e(canonical) + '">\n'
    if source and path.startswith(('/source/', '/post/source/')) and path.rstrip('/') not in {'/source', '/post/source'}:
        share_image = source_share_image(source, origin)
        if share_image:
            head += '<meta property="og:image" content="' + e(share_image) + '">\n'
            head += '<meta property="og:image:alt" content="' + e(source_name(source, locale)) + '">\n'
    document = document.replace('</head>', head + '</head>', 1)
    nav = ' · '.join('<a href="/' + slug + '/?lang=' + locale + '">' + e(words[slug]) + '</a>'
                     for slug in ('events', 'post', 'source', 'scores', 'feeds', 'contribute'))
    content = '<section class="server-content" aria-label="' + e(page) + '"><nav>' + nav + '</nav><h1>' + e(page) + '</h1><p>' + e(description) + '</p>'
    if source:
        if localized_summary and source.get('summary') and localized_summary != source['summary']:
            original_language = source.get('summaryLanguage')
            language = ' lang="' + e(original_language) + '"' if original_language in LOCALES else ''
            content += '<details class="source-original-summary"><summary>' + e(ORIGINAL_DESCRIPTION[locale]) + '</summary><p' + language + '>' + e(source['summary']) + '</p></details>'
        content += '<p>' + e(source_country(source, locale)) + '</p><h2>' + e(words['original']) + '</h2><ul>'
        content += ''.join('<li><a href="' + e(link['url']) + '" rel="noreferrer">' + e(source_link_label(link, locale)) + '</a></li>' for link in source.get('links', []))
        content += '</ul><h2>' + e(words['latest']) + '</h2><ul>'
        content += ''.join('<li><a href="' + e(p['url']) + '">' + e(post_title(p, locale)) + '</a></li>' for p in [p for p in catalog.get('posts', []) if p.get('sourceId') == source.get('id')][:12])
        content += '</ul>'
    elif score_guide:
        content += '<ul>' + ''.join('<li><a href="' + e(row.get('sourceUrl') or row.get('url')) + '">'
            + e(row.get('title') or row.get('name')) + '</a> · ' + e(row.get('name')) + '</li>'
            for row in catalog.get('scoreSources', [])[:24]) + '</ul>'
    else:
        content += '<ul>' + ''.join('<li><a href="' + e(s.get('url') or '/source/') + '?lang=' + locale + '">' + e(source_name(s, locale)) + '</a></li>' for s in catalog.get('sources', [])[:24]) + '</ul>'
    content += '<a href="/source/?lang=' + locale + '">' + e(words['all']) + '</a></section>'
    if '<!--SERVER_CONTENT-->' in document:
        document = document.replace('<!--SERVER_CONTENT-->', content)
    else:
        document = document.replace('</body>', '<noscript>' + content + '</noscript></body>', 1)
    return document
