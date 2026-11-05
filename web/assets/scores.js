import { isRedesign } from './redesign.js';
import { pageNotes } from './page-notes.js';
import { t, getLocale, countryName } from './i18n.js';
import { esc, link, icon, number, safeUrl, textMatch, image, date, hasFilters } from './utils.js';
import { pageHeading } from './views.js';
import { reportLink } from './reporting.js';

const labels = {
  'zh-Hant': {
    guide: '樂譜說明', announcement: '來源公告原文', media: '樂譜封面／來源圖片', work: '曲目與作者', context: '學年度・編制・組別', actions: '出處與連結', repertoire: '比賽指定曲', collections: '出版者與譜集', browse: '樂譜瀏覽',
    indexLine: '比賽指定曲與出版線索索引，不一定提供樂譜下載。',
    indexNote: '這是比賽指定曲與出版線索索引，不代表每筆都有可下載的完整樂譜。請由原始出處核對曲目，再向出版者或提供者詢問取得方式。',
    collectionsNote: '公開出版公告、譜集與聯絡方式。保留來源原文；實際取得方式與授權以原始來源為準。',
    academicYear: '學年度', yearNote: '臺灣學年度以西元起始年顯示，括號保留來源的民國年。', rocYear: '民國 {year}',
    instrument: '編制', allInstruments: '所有編制', division: '組別', allDivisions: '所有組別', publisher: '出版者／提供者', allPublishers: '所有來源',
    sort: '排序', year_desc: '學年度：新到舊', year_asc: '學年度：舊到新', title: '曲名：A–Z', composer: '作曲者：A–Z', name: '來源名稱：A–Z',
    evidence: '原始出處', publisherLink: '出版者或詢問處', sourceAndEvidence: '原始出處',
    noResults: '沒有符合條件的曲目', noCollections: '沒有符合條件的出版來源', reset: '清除篩選', notes: '原始備註', records: '{count} 筆曲目索引', collectionRecords: '{count} 筆出版／譜集來源',
    solo: '口琴獨奏', quartet: '口琴四重奏', ensemble: '口琴合奏',
  },
  en: {
    guide: 'About this index', announcement: 'Original announcement', media: 'Cover / source image', work: 'Work & credits', context: 'Year · instrumentation · division', actions: 'Sources & links', repertoire: 'Competition repertoire', collections: 'Publishers & collections', browse: 'Browse scores',
    indexLine: 'An index of competition pieces and where they’re published — not a download library.',
    indexNote: 'This is an index of competition repertoire and publishing leads. Entries do not necessarily include a downloadable full score. Check the original source, then contact the publisher or source for availability.',
    collectionsNote: 'Public publishing announcements, collections and where to ask. Original descriptions are preserved; availability and permissions are determined by each source.',
    academicYear: 'Academic year', yearNote: 'Taiwan academic years show the Gregorian starting year, followed by the original ROC year.', rocYear: 'ROC {year}',
    instrument: 'Instrumentation', allInstruments: 'All instrumentation', division: 'Division', allDivisions: 'All divisions', publisher: 'Publisher / provider', allPublishers: 'All sources',
    sort: 'Sort', year_desc: 'Year: newest first', year_asc: 'Year: oldest first', title: 'Title: A–Z', composer: 'Composer: A–Z', name: 'Source name: A–Z',
    evidence: 'Original source', publisherLink: 'Publisher or where to ask', sourceAndEvidence: 'Original source',
    noResults: 'No matching repertoire', noCollections: 'No matching publishing sources', reset: 'Clear filters', notes: 'Original notes', records: '{count} repertoire entries', collectionRecords: '{count} publishing / collection sources',
    solo: 'Harmonica solo', quartet: 'Harmonica quartet', ensemble: 'Harmonica ensemble',
  },
  ja: {
    guide: '楽譜について', announcement: '公開案内の原文', media: '表紙・出典の画像', work: '曲目・作者', context: '学年度・編成・部門', actions: '原資料・リンク', repertoire: 'コンクール課題曲', collections: '出版社・楽譜集', browse: '楽譜を探す',
    indexLine: 'コンクール課題曲と出版情報の索引です。楽譜のダウンロードはできない場合があります。',
    indexNote: 'コンクール課題曲と出版情報の索引です。すべての項目にダウンロード可能な楽譜があるわけではありません。原資料で曲目を確認し、入手方法は出版社・情報源にお問い合わせください。',
    collectionsNote: '公開の出版案内、楽譜集、お問い合わせ先です。説明は原文を保持し、入手条件・利用許諾は各情報源に従います。',
    academicYear: '学年度', yearNote: '台湾の学年度は開始年を西暦で表示し、原資料の民国年を括弧内に併記しています。', rocYear: '民国{year}年',
    instrument: '編成', allInstruments: 'すべての編成', division: '部門', allDivisions: 'すべての部門', publisher: '出版社・提供元', allPublishers: 'すべての情報源',
    sort: '並べ替え', year_desc: '年度：新しい順', year_asc: '年度：古い順', title: '曲名：A–Z', composer: '作曲者：A–Z', name: '情報源名：A–Z',
    evidence: '原資料', publisherLink: '出版社・お問い合わせ', sourceAndEvidence: '情報源・原資料',
    noResults: '条件に合う曲目がありません', noCollections: '条件に合う出版情報がありません', reset: '絞り込みを解除', notes: '原文の備考', records: '曲目索引 {count} 件', collectionRecords: '出版社・楽譜集 {count} 件',
    solo: 'ハーモニカ独奏', quartet: 'ハーモニカ四重奏', ensemble: 'ハーモニカ合奏',
  },
  ko: {
    guide: '악보 안내', announcement: '공개 공지 원문', media: '표지·출처 이미지', work: '곡목·제작진', context: '학년도·편성·부문', actions: '출처·링크', repertoire: '콩쿠르 지정곡', collections: '출판사·악보집', browse: '악보 찾기',
    indexLine: '대회 지정곡과 출판 정보 색인으로, 악보 다운로드를 제공하지 않을 수 있어요.',
    indexNote: '콩쿠르 지정곡과 출판 정보의 목록입니다. 모든 항목에 내려받을 수 있는 전체 악보가 있는 것은 아닙니다. 원본 출처에서 곡목을 확인한 후 출판사나 출처에 입수 방법을 문의하세요.',
    collectionsNote: '공개 출판 공지, 악보집 및 문의처입니다. 설명은 원문을 유지하며 입수 조건과 이용 허가는 각 출처를 따릅니다.',
    academicYear: '학년도', yearNote: '대만 학년도는 시작하는 서기 연도를 표시하며, 출처의 민국년을 괄호 안에 함께 표시합니다.', rocYear: '민국 {year}년',
    instrument: '편성', allInstruments: '모든 편성', division: '부문', allDivisions: '모든 부문', publisher: '출판사·제공처', allPublishers: '모든 출처',
    sort: '정렬', year_desc: '학년도: 최신순', year_asc: '학년도: 오래된순', title: '곡명: A–Z', composer: '작곡가: A–Z', name: '출처 이름: A–Z',
    evidence: '원본 출처', publisherLink: '출판사·문의처', sourceAndEvidence: '원본 출처',
    noResults: '조건에 맞는 곡목이 없습니다', noCollections: '조건에 맞는 출판 정보가 없습니다', reset: '필터 초기화', notes: '원문 비고', records: '곡목 색인 {count}건', collectionRecords: '출판사·악보집 출처 {count}건',
    solo: '하모니카 독주', quartet: '하모니카 4중주', ensemble: '하모니카 합주',
  },
};
const guideCopy = {
  'zh-Hant': {unverified:'公告連結待確認，請向來源詢問。', collections:'找譜與購譜', collectionRecords:'{count} 筆找譜資訊', collectionsNote:'本站提供外部來源連結。價格、庫存與使用授權請向提供者確認。', kind:'你想找什麼？', allKinds:'全部資訊', books:'譜集與教材', announcements:'販售公告', contacts:'曲庫與洽詢', booksHelp:'已有名稱的曲集或教材；部分連結會前往商店分類頁。', announcementsHelp:'樂譜販售資訊；是否仍可購買，請查看公告或詢問發布者。', contactsHelp:'曲庫、團隊網站與聯絡線索；不表示已有特定樂譜可取得。', provider:'提供者', how:'取得方式', record:'收錄紀錄與原文', recorded:'收錄日期', recordedPrice:'當時記錄的價格', recordedAvailability:'當時記錄的狀態', product:'查看商品頁', shop:'瀏覽商店', category:'瀏覽商店分類', readAnnouncement:'閱讀販售公告', library:'查看曲庫', profile:'前往粉專詢問', website:'前往來源網站', introduction:'查看作品介紹', searchGuide:'搜尋書名、提供者或口琴編制', sourcePage:'查看原始頁面'},
  en: {unverified:'The announcement link needs verification; please ask the source.', collections:'Find & buy music', collectionRecords:'{count} music leads', collectionsNote:'Links open external sources. Confirm prices, stock and permissions with the provider.', kind:'What are you looking for?', allKinds:'All information', books:'Books & sheet music', announcements:'Sales announcements', contacts:'Libraries & enquiries', booksHelp:'Named books and collections; some links open a shop category rather than a product page.', announcementsHelp:'Published sales information. Check the announcement or ask the provider about availability.', contactsHelp:'Libraries, team websites and contact leads; these do not guarantee a particular score is available.', provider:'Provider', how:'How to obtain', record:'Recorded details & original text', recorded:'Date recorded', recordedPrice:'Price recorded then', recordedAvailability:'Status recorded then', product:'View product page', shop:'Browse shop', category:'Browse shop category', readAnnouncement:'Read sales announcement', library:'Open music library', profile:'Visit page to enquire', website:'Visit source website', introduction:'Read artist / work profile', searchGuide:'Search titles, providers or instrumentation', sourcePage:'View original page'},
  ja: {unverified:'案内のリンクは未確認です。提供元にお問い合わせください。', collections:'楽譜の入手先', collectionRecords:'楽譜情報 {count} 件', collectionsNote:'リンク先は外部サイトです。価格・在庫・利用条件は提供元にご確認ください。', kind:'何を探しますか？', allKinds:'すべての情報', books:'楽譜集・教材', announcements:'販売案内', contacts:'曲庫・問い合わせ先', booksHelp:'名称のある楽譜集や教材。一部のリンクは商品ではなく店舗カテゴリに移動します。', announcementsHelp:'公開された販売情報です。現在の購入可否は案内や提供元をご確認ください。', contactsHelp:'曲庫や団体サイト、連絡先です。特定の楽譜が入手できるとは限りません。', provider:'提供元', how:'入手方法', record:'記録情報・原文', recorded:'記録日', recordedPrice:'記録時の価格', recordedAvailability:'記録時の状況', product:'商品ページを見る', shop:'店舗を見る', category:'店舗カテゴリを見る', readAnnouncement:'販売案内を読む', library:'曲庫を見る', profile:'公開ページで問い合わせる', website:'提供元サイトへ', introduction:'人物・作品紹介を読む', searchGuide:'書名・提供元・編成で検索', sourcePage:'元のページを見る'},
  ko: {unverified:'공지 링크를 확인 중입니다. 제공처에 문의하세요.', collections:'악보 찾기·구매', collectionRecords:'악보 정보 {count}건', collectionsNote:'외부 출처로 연결됩니다. 가격, 재고 및 이용 조건은 제공처에 확인하세요.', kind:'무엇을 찾으시나요?', allKinds:'모든 정보', books:'악보집·교재', announcements:'판매 공지', contacts:'자료실·문의처', booksHelp:'제목이 있는 악보집과 교재입니다. 일부 링크는 상품 대신 상점 분류로 연결됩니다.', announcementsHelp:'공개된 판매 정보입니다. 현재 구매 가능 여부는 공지나 제공처에서 확인하세요.', contactsHelp:'자료실, 단체 사이트와 문의 단서입니다. 특정 악보의 입수를 보장하지 않습니다.', provider:'제공처', how:'입수 방법', record:'수집 기록·원문', recorded:'기록 날짜', recordedPrice:'기록 당시 가격', recordedAvailability:'기록 당시 상태', product:'상품 페이지 보기', shop:'상점 둘러보기', category:'상점 분류 보기', readAnnouncement:'판매 공지 읽기', library:'곡목 자료실 보기', profile:'공개 페이지에서 문의', website:'출처 사이트 방문', introduction:'연주자·작품 소개 읽기', searchGuide:'제목, 제공처 또는 편성 검색', sourcePage:'원본 페이지 보기'},
};
// The repertoire search matches titles, composers and arrangers (and the
// instrumentation and publisher), so its placeholder names those.
const searchCopy = {
  'zh-Hant': '搜尋曲名、作曲者、編曲者…', en: 'Search titles, composers, arrangers…',
  ja: '曲名・作曲者・編曲者を検索…', ko: '곡명, 작곡가, 편곡자 검색…',
};
for (const locale of Object.keys(labels)) Object.assign(labels[locale], guideCopy[locale], { searchScores: searchCopy[locale] });
export const scoreLabels = labels;
const l = (key, values = {}) => (labels[getLocale()] || labels.en)[key].replace(/\{(\w+)\}/g, (_, name) => values[name] ?? '');
// Controlled catalogue facets follow the interface language. Original titles,
// names and notes remain untouched; select values retain their stable source keys.
const facetWords = {
  '口琴': ['Harmonica', 'ハーモニカ', '하모니카'],
  '口琴獨奏': ['Harmonica solo', 'ハーモニカ独奏', '하모니카 독주'],
  '口琴四重奏': ['Harmonica quartet', 'ハーモニカ四重奏', '하모니카 4중주'],
  '口琴五重奏': ['Harmonica quintet', 'ハーモニカ五重奏', '하모니카 5중주'],
  '口琴合奏': ['Harmonica ensemble', 'ハーモニカ合奏', '하모니카 합주'],
  '口琴大合奏': ['Harmonica orchestra', 'ハーモニカ大合奏', '하모니카 대합주'],
  '口琴重奏': ['Harmonica chamber ensemble', 'ハーモニカ重奏', '하모니카 중주'],
  '複音口琴': ['Tremolo harmonica', '複音ハーモニカ', '트레몰로 하모니카'],
  '半音階口琴': ['Chromatic harmonica', 'クロマチックハーモニカ', '크로매틱 하모니카'],
  '十孔口琴': ['Diatonic harmonica', '10穴ハーモニカ', '다이아토닉 하모니카'],
  '低音口琴': ['Bass harmonica', 'バスハーモニカ', '베이스 하모니카'],
  '複音口琴獨奏': ['Tremolo harmonica solo', '複音ハーモニカ独奏', '트레몰로 하모니카 독주'],
  '半音階口琴獨奏': ['Chromatic harmonica solo', 'クロマチックハーモニカ独奏', '크로매틱 하모니카 독주'],
  '三部半音階口琴(16孔)': ['3 chromatic harmonicas (16 holes)', 'クロマチックハーモニカ3パート（16穴）', '크로매틱 하모니카 3파트 (16홀)'],
  '和弦口琴': ['Chord harmonica', 'コードハーモニカ', '코드 하모니카'],
  '倍低音口琴(39音)': ['Bass harmonica (39 notes)', 'バスハーモニカ（39音）', '베이스 하모니카 (39음)'],
  '複音': ['Tremolo', '複音', '트레몰로'], '半音階': ['Chromatic', 'クロマチック', '크로매틱'],
  '十孔': ['Diatonic', '10穴', '다이아토닉'], '獨奏': ['Solo', '独奏', '독주'],
  '小合奏': ['Small ensemble', '小編成合奏', '소규모 합주'], '大合奏': ['Orchestra', '大合奏', '대합주'],
  '合奏': ['Ensemble', '合奏', '합주'], '四重奏': ['Quartet', '四重奏', '4중주'], '重奏': ['Chamber ensemble', '重奏', '중주'],
  '國中': ['Junior high', '中学校', '중학교'], '國中小': ['Elementary / junior high', '小・中学校', '초·중학교'],
  '國小': ['Elementary school', '小学校', '초등학교'], '高中': ['Senior high', '高校', '고등학교'],
  '高中職': ['Senior high / vocational', '高校・職業高校', '고등학교·직업학교'], '大專': ['College', '大学・短大', '대학'],
  '社會': ['Open', '一般', '일반'], 'Open': ['Open', '一般', '일반'],
  '國中團體組': ['Junior high ensemble', '中学校団体', '중학교 단체'],
  '國小團體組': ['Elementary ensemble', '小学校団体', '초등학교 단체'],
  '高中職團體組': ['Senior high / vocational ensemble', '高校・職業高校団体', '고등학교·직업학교 단체'],
  '大專團體組': ['College ensemble', '大学・短大団体', '대학 단체'],
  '兒童': ['Children', '児童', '어린이'], '少年': ['Junior', 'ジュニア', '주니어'],
  '青少年': ['Youth', '青少年', '청소년'], '成人': ['Adult', '成人', '성인'],
  '決賽': ['Final', '決勝', '결선'], '複賽': ['Semifinal', '準決勝', '준결선'],
};
const facet = value => getLocale() === 'zh-Hant' ? value : facetWords[value]?.[['en','ja','ko'].indexOf(getLocale())] || value;
export const instrumentation = value => String(value || '').split('、').map(facet).join(getLocale() === 'zh-Hant' || getLocale() === 'ja' ? '、' : ', ');
export function divisionLabel(value = '') {
  if (getLocale() === 'zh-Hant') return value;
  const staged = value.match(/^(.+)（(決賽|複賽)）$/);
  if (staged) return `${facet(staged[1])} · ${facet(staged[2])}`;
  const base = value.replace(/組$/, '');
  return facetWords[value] ? facet(value) : facetWords[base] ? facet(base) : value;
}
const purchaseWords = {
  'Facebook 粉專公告洽詢':['Enquire about the Facebook announcement','Facebookの案内について問い合わせ','Facebook 공지에 관해 문의'],
  'Facebook 粉專或商品頁追蹤':['Check the Facebook page or product page','Facebookまたは商品ページで確認','Facebook 또는 상품 페이지 확인'],
  'Facebook 粉專洽詢':['Enquire on Facebook','Facebookで問い合わせ','Facebook에서 문의'],
  'Facebook 粉專追蹤':['Check the Facebook page','Facebookページで確認','Facebook 페이지 확인'],
  'Google Site 查詢':['Browse the Google Site','Googleサイトで確認','Google 사이트 확인'],
  'Shopee 賣場購買':['Visit the Shopee shop','Shopee店舗で購入','Shopee 상점에서 구매'],
  '以公開介紹回溯譜集與洽詢入口':['Find collections and contacts in the artist profile','人物紹介から楽譜集・連絡先を探す','연주자 소개에서 악보집·문의처 찾기'],
  '依公開貼文洽詢或購買':['Follow the post to enquire or buy','公開投稿から問い合わせ・購入','공개 게시물에서 문의·구매'],
  '公開曲庫頁查詢':['Search the public music library','公開曲庫で検索','공개 곡목 자료실 검색'],
  '官網聯絡資訊洽詢':['Use the website contact details','公式サイトの連絡先に問い合わせ','공식 사이트 연락처로 문의'],
  '黃石樂器商品分類頁查詢':['Browse the retailer’s book category','販売店の書籍カテゴリで確認','판매점의 도서 분류 확인'],
  '黃石樂器商品頁線上購買':['Order on the retailer’s product page','販売店の商品ページで購入','판매점 상품 페이지에서 구매'],
};
const purchaseMethod = value => getLocale() === 'zh-Hant' ? value : purchaseWords[value]?.[['en','ja','ko'].indexOf(getLocale())] || value;
export function academicYearNumber(row) {
  const year = Number(row.year) || 0;
  return row.countryCode === 'TW' && year > 0 && year < 1000 ? year + 1911 : year;
}
export function academicYearLabel(row) {
  const year = academicYearNumber(row);
  return year && String(year) !== String(row.year) ? `${year} (${l('rocYear', { year: row.year })})` : String(row.year || '—');
}
const fields = { year: 'year', instrument: 'instrument', division: 'division', publisher: 'sourceName', country: 'countryCode' };
const match = (row, state, omit = '') => textMatch(row, state.q) && Object.entries(fields).every(([key, field]) => key === omit || !state[key] || String(row[field] || (key === 'country' ? 'UNKNOWN' : '')) === String(state[key]));

export function filterScores(rows, state = {}) {
  const collator = new Intl.Collator(getLocale(), { numeric: true, sensitivity: 'base' });
  const sort = ['year_desc', 'year_asc', 'title', 'composer'].includes(state.scoreSort) ? state.scoreSort : 'year_desc';
  return rows.filter(row => match(row, state)).sort((a, b) => {
    if (sort === 'year_desc' || sort === 'year_asc') {
      const difference = academicYearNumber(a) - academicYearNumber(b);
      if (difference) return difference * (sort === 'year_desc' ? -1 : 1);
    } else if (sort === 'composer') {
      if (!a.composer !== !b.composer) return a.composer ? -1 : 1;
      const comparison = collator.compare(a.composer || '', b.composer || '');
      if (comparison) return comparison;
    }
    return collator.compare(a.title || '', b.title || '') || collator.compare(a.id || '', b.id || '');
  });
}

export function scoreFacets(rows, state = {}, key) {
  const field = fields[key];
  if (!field) return [];
  const counts = new Map();
  for (const row of rows.filter(row => match(row, state, key))) {
    const value = String(row[field] || (key === 'country' ? 'UNKNOWN' : ''));
    if (value) counts.set(value, (counts.get(value) || 0) + 1);
  }
  if (state[key] && !counts.has(String(state[key]))) counts.set(String(state[key]), 0);
  const collator = new Intl.Collator(getLocale(), { numeric: true });
  const comparableYear = value => academicYearNumber(rows.find(row => String(row.year) === value) || { year: value });
  return [...counts].sort(([a], [b]) => key === 'year' ? comparableYear(b) - comparableYear(a) : collator.compare(a, b)).map(([value, count]) => ({ value, count }));
}

function tabs(active, state, catalog) {
  const query = new URLSearchParams({ lang: getLocale() });
  if (state.q) query.set('q', state.q);
  if (state.country) query.set('country', state.country);
  return `<nav class="score-tabs" aria-label="${esc(l('browse'))}">${[['repertoire', '/scores/', catalog.scores?.length || 0], ['collections', '/scores/sources/', catalog.scoreSources?.length || 0]].map(([key, href, count]) => link(href + '?' + query.toString(), `${esc(l(key))}<span>${number(count)}</span>`, `score-tab ${key === active ? 'is-active' : ''}`, key === active ? 'aria-current="page"' : '')).join('')}</nav>`;
}
function select(key, label, allLabel, rows, state) {
  const valueLabel = value => key === 'country' ? countryName(value) : key === 'instrument' ? instrumentation(value) : key === 'division' ? divisionLabel(value) : key === 'year' ? academicYearLabel(rows.find(row => String(row.year) === value) || { year: value }) : value;
  return `<label>${esc(label)}<select data-filter="${key}"><option value="">${esc(allLabel)}</option>${scoreFacets(rows, state, key).map(({ value, count }) => `<option value="${esc(value)}" ${String(state[key] || '') === value ? 'selected' : ''}>${esc(valueLabel(value))} (${number(count)})</option>`).join('')}</select></label>`;
}
function controls(rows, state, collections = false) {
  const relevantState = collections ? { q: state.q, country: state.country } : state;
  return `<section class="filter-bar scores-filters" aria-label="${t('filter')}"><label class="search-label"><span>${t('search')}</span><div class="search-wrap">${icon('search')}<input id="catalog-search" type="search" value="${esc(state.q || '')}" placeholder="${esc(collections ? t('searchPlaceholder') : l('searchScores'))}" autocomplete="off"></div></label>${select('country', t('country'), t('allCountries'), rows, relevantState)}${collections ? '' : select('year', l('academicYear'), t('allYears'), rows, state) + select('instrument', l('instrument'), l('allInstruments'), rows, state) + select('division', l('division'), l('allDivisions'), rows, state) + select('publisher', l('publisher'), l('allPublishers'), rows, state)}${collections ? '' : `<label>${esc(l('sort'))}<select data-filter="scoreSort">${['year_desc', 'year_asc', 'title', 'composer'].map(value => `<option value="${value}" ${(state.scoreSort || 'year_desc') === value ? 'selected' : ''}>${esc(l(value))}</option>`).join('')}</select></label>`}${['q', 'country', ...(collections ? [] : ['year', 'instrument', 'division', 'publisher'])].some(key => state[key]) ? `<button class="clear-filter" data-action="reset">${esc(l('reset'))}</button>` : ''}</section>`;
}
export function scoreEvidenceLinks(row) {
  const evidence = safeUrl(row.sourceUrl), publisher = safeUrl(row.url);
  const seen = new Set();
  const links = [];
  function add(url, label) { const safe = safeUrl(url); if (safe && !seen.has(safe)) { seen.add(safe); links.push(link(safe, esc(label), 'score-evidence-link')); } }
  if (evidence && evidence === publisher) add(evidence, l('sourceAndEvidence'));
  else { add(evidence, l('evidence')); add(publisher, l('publisherLink')); }
  for (const item of Array.isArray(row.links) ? row.links : []) add(item.url, item.label || l('evidence'));
  return `<div class="score-evidence">${links.join('')}</div>`;
}
function repertoireRow(row) {
  return `<tr class="score-row repertoire-row"><td class="score-main"><h3>${esc(row.title)}</h3>${row.composer || row.arranger ? `<p class="score-credits">${row.composer ? `<span>${t('composer')}: ${esc(row.composer)}</span>` : ''}${row.arranger ? `<span>${t('arranger')}: ${esc(row.arranger)}</span>` : ''}</p>` : ''}${row.notes ? `<details class="score-notes"><summary>${esc(l('notes'))}</summary><p>${esc(row.notes)}</p></details>` : ''}</td><td class="score-context"><div class="score-row-meta"><span class="score-year">${esc(academicYearLabel(row))}</span><span>${esc(instrumentation(row.instrument || ''))}</span><span>${esc(divisionLabel(row.division || ''))}</span>${row.countryCode && row.countryCode !== 'UNKNOWN' ? `<span class="score-country">${esc(countryName(row.countryCode))}</span>` : ''}</div></td><td class="score-publisher"><span class="score-mobile-label">${esc(l('publisher'))}</span>${esc(row.sourceName || '—')}</td><td class="score-actions"><div class="score-row-links">${scoreEvidenceLinks(row)}${reportLink(row, row.sourceUrl || row.url)}</div></td></tr>`;
}
function repertoireTable(rows) {
  return `<table class="score-table"><caption class="sr-only">${esc(l('repertoire'))}</caption><thead><tr><th scope="col">${esc(l('work'))}</th><th scope="col">${esc(l('context'))}</th><th scope="col">${esc(l('publisher'))}</th><th scope="col">${esc(l('actions'))}</th></tr></thead><tbody>${rows.map(repertoireRow).join('')}</tbody></table>`;
}
function collectionMedia(row) {
  const seenImages = new Set(), seenPosts = new Set();
  function gallery(urls, original, title) {
    const images = urls.map(safeUrl).filter(url => url && !seenImages.has(url) && seenImages.add(url));
    return images.length ? `<div class="collection-media">${images.map(url => link(original, image(url, '', `${l('media')}: ${title || row.name || row.title || ''}`), 'collection-media-link')).join('')}</div>` : '';
  }
  const direct = gallery(Array.isArray(row.images) ? row.images : [], row.imageSourceUrl || row.sourceUrl || row.url, row.title);
  const posts = (Array.isArray(row.relatedPosts) ? row.relatedPosts : []).filter(post => {
    const url = safeUrl(post.url);
    return url && !seenPosts.has(url) && seenPosts.add(url);
  });
  return direct + posts.map(post => {
    const text = post.text || '', expanded = text.length <= 240 && text.split('\n').length <= 6;
    return `<section class="collection-post feed-content"><div class="collection-post-heading"><strong>${esc(l('announcement'))}</strong>${post.publishedAt ? `<time datetime="${esc(post.publishedAt)}">${esc(date(post.publishedAt))}</time>` : ''}</div>${gallery([post.image, ...(Array.isArray(post.images) ? post.images : [])], post.url, post.title || row.title)}${text ? `<p class="feed-text post-text${expanded ? ' is-expanded' : ''}">${esc(text)}</p>${expanded ? '' : `<button type="button" class="collection-expand" data-expand-post aria-expanded="false">${t('readMore')}</button>`}` : ''}${link(post.url, t('original'), 'collection-original-link')}</section>`;
  }).join('');
}
export function collectionKind(row) {
  if (row.referenceStatus === 'unverified') return 'contacts';
  if (/^紙本/.test(row.format || '')) return 'books';
  if (['電子樂譜公告','樂譜販售公告','PDF／MP3 公告'].includes(row.format)) return 'announcements';
  return 'contacts';
}
export function collectionAction(row) {
  const urls = [...new Set([row.imageSourceUrl,row.sourceUrl,row.url,...(row.links || []).map(item=>item.url)].map(safeUrl).filter(Boolean))];
  const parsed = value => { try { return new URL(value, 'https://harmonica.observe.tw'); } catch { return null; } };
  const product = urls.find(url => /\/product\/[^/]+/.test(parsed(url)?.pathname || ''));
  if (product && collectionKind(row) === 'books') return {url:product,label:'product'};
  const category = urls.find(url => /\/product-category\//.test(parsed(url)?.pathname || ''));
  if (category) return {url:category,label:'category'};
  if (row.format === '線上資料庫') return {url:safeUrl(row.url || row.sourceUrl),label:'library'};
  if (collectionKind(row) === 'announcements') {
    const post = urls.find(url => /\/(posts|photos|p|reel)\//.test(parsed(url)?.pathname || '') || ['story_fbid','fbid'].some(key=>parsed(url)?.searchParams.has(key)));
    if (post) return {url:post,label:'readAnnouncement'};
  }
  const url = safeUrl(row.url) || urls[0] || '';
  const host = parsed(url)?.hostname || '';
  const label = row.format === '人物／作品介紹' ? 'introduction' : collectionKind(row) === 'books' || row.format === '商品分類' ? 'shop' : /(^|\.)facebook\.com$/.test(host) ? 'profile' : 'website';
  return {url,label};
}
const hasCover = row => Array.isArray(row.images) && row.images.some(safeUrl) && !(row.relatedPosts || []).length;
// New interface: in a group where some items show a cover, an item without one
// keeps the same layout with a neutral placeholder tile in the cover slot.
function collectionRow(row, placeholder = false) {
  const action = collectionAction(row);
  const cover = hasCover(row);
  const tile = !cover && placeholder;
  const media = collectionMedia(row);
  const detail = (label,value) => value ? `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>` : '';
  // New interface: a button that opens the product page already says how to
  // obtain the book; the recorded method (often "browse the category") would
  // only repeat or contradict it.
  const showHow = !(isRedesign() && action.label === 'product');
  const extra = [...new Set([row.imageSourceUrl,row.sourceUrl,row.url,...(row.links || []).map(item=>item.url)].map(safeUrl).filter(url=>url && url !== action.url))];
  return `<article class="score-row repertoire-row collection-row${cover || tile ? ' collection-illustrated' : ''}" data-collection-kind="${collectionKind(row)}">${cover ? `<div class="collection-cover">${media}</div>` : tile ? `<div class="collection-cover collection-cover-placeholder" aria-hidden="true">${icon('music')}</div>` : ''}<div class="score-main"><h3 class="collection-title">${esc(row.title || row.name)}</h3><p class="collection-provider">${esc(l('provider'))}: ${esc(row.name || '')}</p>${row.referenceStatus === 'unverified' ? `<p class="collection-reference-note">${esc(l('unverified'))}</p>` : ''}<dl class="collection-facts">${detail(l('instrument'),instrumentation(row.instrumentation))}${showHow ? detail(l('how'),purchaseMethod(row.purchaseMethod)) : ''}</dl>${cover ? '' : media}<div class="score-row-links">${link(action.url, esc(l(action.label)), 'button button-outline collection-primary')}${reportLink(row)}</div><details class="collection-record"><summary>${esc(l('record'))}${row.lastSeenAt ? ` · ${esc(row.lastSeenAt)}` : ''}</summary><dl>${detail(l('recorded'),row.lastSeenAt)}${detail(t('composer'),row.composer)}${detail(t('arranger'),row.arranger)}${detail(l('recordedPrice'),row.price)}${detail(l('recordedAvailability'),row.availability)}</dl>${row.summary ? `<p class="collection-original">${esc(row.summary)}</p>` : ''}<div class="score-evidence">${extra.map(url=>link(url,esc(l('sourcePage')),'score-evidence-link')).join('')}</div></details></div></article>`;
}
function collectionControls(rows, state) {
  const base = rows.filter(row=>match(row,{q:state.q,country:state.country}));
  const countries = state.country || rows.some(row=>row.countryCode && row.countryCode!=='UNKNOWN');
  return `<section class="filter-bar scores-filters collection-filters" aria-label="${t('filter')}"><label class="search-label"><span>${t('search')}</span><div class="search-wrap">${icon('search')}<input id="catalog-search" type="search" value="${esc(state.q || '')}" placeholder="${esc(l('searchGuide'))}" autocomplete="off"></div></label><label>${esc(l('kind'))}<select data-filter="scoreKind"><option value="">${esc(l('allKinds'))} (${number(base.length)})</option>${['books','announcements','contacts'].map(kind=>`<option value="${kind}" ${state.scoreKind===kind?'selected':''}>${esc(l(kind))} (${number(base.filter(row=>collectionKind(row)===kind).length)})</option>`).join('')}</select></label>${countries ? select('country',t('country'),t('allCountries'),rows,{q:state.q,country:state.country}) : ''}${state.q || state.country || state.scoreKind ? `<button class="clear-filter" data-action="reset">${esc(l('reset'))}</button>` : ''}</section>`;
}

function noResults(collections, filtered = true) {
  return `<div class="empty-state">${icon(filtered ? 'search' : 'music')}<h2>${esc(l(collections ? 'noCollections' : 'noResults'))}</h2>${filtered ? `<p>${t('noResultsBody')}</p><div class="empty-actions"><button class="button button-outline" data-action="reset">${esc(l('reset'))}</button></div>` : ''}</div>`;
}
function pagination(length, limit) {
  return length > limit ? `<div class="pagination"><p>${t('showing', { shown: number(limit), total: number(length) })}</p><button class="button button-outline" data-action="more">${t('loadMore')}${icon('plus')}</button></div>` : '';
}
export function scoresView(catalog, state = {}, limit = 24) {
  const rows = catalog.scores || [], results = filterScores(rows, state);
  if (isRedesign()) {
    // One count per list: the tab and "showing x of y"; a result count only
    // while filtered. One line under the title says what the list is (an index,
    // not downloads); the year rule moves to the page notes.
    const filtered = ['q', 'country', 'year', 'instrument', 'division', 'publisher'].some(key => state[key]);
    const heading = pageHeading('scores', 'scoresBody').replace('</h1>', `</h1><p class="page-heading-note">${esc(l('indexLine'))}</p>`);
    return `${heading}${tabs('repertoire', state, catalog)}${controls(rows, state)}${filtered ? `<div class="results-bar"><p role="status">${esc(l('records', { count: number(results.length) }))}</p></div>` : ''}<div class="score-list">${results.length ? repertoireTable(results.slice(0, limit)) : noResults(false, hasFilters(state))}</div>${pagination(results.length, limit)}${pageNotes([esc(l('yearNote'))])}`;
  }
  return `${pageHeading('scores', 'scoresBody')}${tabs('repertoire', state, catalog)}${controls(rows, state)}<div class="results-bar"><p role="status">${esc(l('records', { count: number(results.length) }))}</p></div><div class="score-list">${results.length ? repertoireTable(results.slice(0, limit)) : noResults(false, hasFilters(state))}</div>${pagination(results.length, limit)}<details class="score-guide"><summary>${esc(l('guide'))}</summary><p>${esc(l('indexNote'))}</p><p>${esc(l('yearNote'))}</p></details>`;
}
export function scoreSourcesView(catalog, state = {}, limit = 24) {
  const rows = catalog.scoreSources || [];
  const collator = new Intl.Collator(getLocale(), { numeric: true, sensitivity: 'base' });
  const kinds = ['books','announcements','contacts'];
  const results = rows.filter(row => match(row, { q: state.q, country: state.country }) && (!state.scoreKind || collectionKind(row) === state.scoreKind)).sort((a,b)=>kinds.indexOf(collectionKind(a))-kinds.indexOf(collectionKind(b)) || collator.compare(a.title || a.name || '',b.title || b.name || ''));
  const visible = results.slice(0,limit);
  const content = kinds.map(kind=>{
    const group = visible.filter(row=>collectionKind(row)===kind);
    return group.length ? `<div class="collection-group-heading"><h2>${esc(l(kind))} <span>${number(results.filter(row=>collectionKind(row)===kind).length)}</span></h2><p>${esc(l(kind+'Help'))}</p></div>${group.map(row => collectionRow(row, isRedesign() && group.some(hasCover))).join('')}` : '';
  }).join('');
  if (isRedesign()) {
    // Each group heading carries its own count, so the total appears only
    // while a search or country narrows every group; the note moves to the foot.
    const filtered = state.q || state.country;
    return `${pageHeading('scoreSources', 'scoreSourcesBody')}${tabs('collections', state, catalog)}${collectionControls(rows,state)}${filtered ? `<div class="results-bar"><p role="status">${esc(l('collectionRecords', { count: number(results.length) }))}</p></div>` : ''}<div class="score-list score-source-list">${results.length ? content : noResults(true, hasFilters(state))}</div>${pagination(results.length, limit)}${pageNotes([esc(l('collectionsNote'))])}`;
  }
  return `${pageHeading('scoreSources', 'scoreSourcesBody')}${tabs('collections', state, catalog)}${collectionControls(rows,state)}<div class="results-bar"><p role="status">${esc(l('collectionRecords', { count: number(results.length) }))}</p></div><div class="score-list score-source-list">${results.length ? content : noResults(true, hasFilters(state))}</div>${pagination(results.length, limit)}<p class="score-index-note">${icon('info')}<span>${esc(l('collectionsNote'))}</span></p>`;
}
