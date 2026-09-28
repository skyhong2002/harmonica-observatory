import { eventText } from './event-localization.js';
import { t, getLocale, countryName } from './i18n.js';
import { esc, link, icon, timestamp, shortEventDate, number, avatar, sourceHref, safeUrl, textMatch, platformName, empty, postDisplayText } from './utils.js';
import { filterBar } from './views.js';
import { reportLink } from './reporting.js';
import { sourceDisplayName } from './source-names.js';

const labels = {
  en: {share:'Share', original:'Open source', local:'Post times use your device timezone', snapshot:'Website snapshot', observed:'Observed, not published', snapshots:'Website page snapshots appear when you select Web.', noFollowing:'Your followed feed is empty', startFollowing:'Follow sources in the directory to see their posts here. Following is saved in this browser.'},
  'zh-Hant': {share:'分享', original:'開啟來源', local:'貼文時間依裝置時區顯示', snapshot:'網站頁面快照', observed:'觀測時間，非發布日期', snapshots:'選擇「網站」平台可瀏覽網站頁面快照。', noFollowing:'還沒有追蹤來源', startFollowing:'到來源名錄追蹤感興趣的來源，就能在這裡看到其貼文。追蹤儲存在此瀏覽器。'},
  ja: {share:'共有', original:'元の投稿を開く', local:'投稿時刻は端末のタイムゾーンで表示', snapshot:'ウェブページのスナップショット', observed:'取得日時（公開日ではありません）', snapshots:'ウェブページのスナップショットは「ウェブ」を選ぶと表示されます。', noFollowing:'フォロー中のフィードは空です', startFollowing:'名簿から情報源をフォローすると、ここに投稿が表示されます。フォローはこのブラウザーに保存されます。'},
  ko: {share:'공유', original:'원문 열기', local:'게시 시간은 기기 시간대로 표시됩니다', snapshot:'웹 페이지 스냅샷', observed:'수집 시간 (게시일 아님)', snapshots:'웹 페이지 스냅샷은 웹을 선택하면 표시됩니다.', noFollowing:'팔로우 소식이 비어 있습니다', startFollowing:'목록에서 관심 있는 출처를 팔로우하면 여기에 게시물이 표시됩니다. 팔로우는 이 브라우저에 저장됩니다.'},
};
const words = () => labels[getLocale()] || labels.en;
export function timelinePosts(catalog, state = {}, following = new Set()) {
  const sources = new Map((catalog.sources || []).map(s=>[s.id,s]));
  return (catalog.posts || []).filter(p =>
    (p.contentKind !== 'website_snapshot' || state.platform === 'website') &&
    (!state.country || p.countryCode === state.country) &&
    (!state.platform || p.platform === state.platform) &&
    (!state.type || sources.get(p.sourceId)?.type === state.type) &&
    (!(state.followed || state.kind === 'following') || following.has(p.sourceId)) &&
    (state.kind === 'stories' ? p.isStory : !p.isStory) && textMatch(p,state.q)
  ).sort((a,b)=>(Date.parse(b.publishedAt || b.observedAt)||0)-(Date.parse(a.publishedAt || a.observedAt)||0));
}
function archivedStory(p) {
  return p.isStory && (p.sourceAvailable === false || ['expired','unknown','archived'].includes(p.storyState) || (p.expiresAt && Date.parse(p.expiresAt) <= Date.now()));
}
export function timelineCard(p, sources = [], following = new Set(), events = [], index = 0) {
  const source = sources.find(s=>s.id === p.sourceId);
  const name = source ? sourceDisplayName(source) : p.sourceName || t('source');
  const text = postDisplayText(p, p.text);
  const title = p.title && p.title !== p.text && !(p.text || '').startsWith(p.title) ? postDisplayText(p, p.title) : '';
  const expandable = text.length > 180 || text.split('\n').length > 6;
  const hasImage = !!safeUrl(p.image), followed = !!source && following.has(source.id);
  const linkedEvents = events.filter(e=>(p.eventIds || []).includes(e.id) || p.url && (e.url === p.url || e.sourceUrl === p.url));
  const isSnapshot = p.contentKind === 'website_snapshot';
  const postTime = `${isSnapshot ? esc(words().observed)+': ' : ''}${timestamp(isSnapshot ? p.observedAt : p.publishedAt)}`;
  const href = source ? sourceHref(source) : p.sourceUrl;
  return `<article class="post-card home-feed-card" data-timeline-index="${index}" data-timeline-post="${esc(p.id || p.url)}"><header class="home-feed-source"><div class="home-feed-source-main">${link(href,avatar({...source,...p,avatar:p.avatar || source?.avatar,name}), 'timeline-avatar-link',`aria-label="${esc(name)}"`)}<div><span class="feed-latest-meta">${postTime} · ${esc(platformName(p.platform))}</span><strong>${link(href,esc(name),'source-name-link')}</strong></div></div>${link(p.sourceUrl || p.url, platformIconSvg(String(p.platform).toLowerCase()),'timeline-platform',`title="${esc(platformName(p.platform))}" aria-label="${esc(platformName(p.platform))}"`)}</header><div class="home-feed-body feed-content${hasImage ? '' : ' home-feed-body-no-image'}${title ? '' : ' home-feed-body-no-title'}">${title ? `<h3 class="home-feed-title">${esc(title)}</h3>` : ''}${hasImage ? link(p.url,`<img src="${esc(safeUrl(p.image))}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`,'home-feed-thumb',`aria-label="${esc(words().original + ': ' + name)}"`) : ''}<p class="feed-latest-excerpt feed-text${expandable ? '' : ' is-expanded'}">${esc(text)}</p>${expandable ? `<button type="button" class="feed-text-toggle" data-expand-post aria-expanded="false">${t('readMore')}</button>` : ''}</div>${archivedStory(p) ? `<p class="story-expired">${t('storyExpired')}</p>` : ''}${linkedEvents.length ? `<div class="timeline-events">${linkedEvents.map(e=>link(e.url || e.sourceUrl,`<span>${esc(shortEventDate(e))}${e.allDay ? ' · '+esc(t('allDay')) : ''}${e.timezone ? ' · '+esc(e.timezone) : e.allDay ? '' : ' · UTC'}</span>${esc(eventText(e))}`,'timeline-event')).join('')}</div>` : ''}<footer class="home-feed-footer"><div class="timeline-meta">${isSnapshot ? `<span class="tag">${esc(words().snapshot)}</span>` : ''}<span>${esc(countryName(p.countryCode || source?.countryCode,p.country || source?.country))}</span>${p.isStory ? `<span class="tag">${t('story')}</span>` : ''}</div><div class="timeline-actions">${source ? `<button type="button" class="timeline-action" data-follow="${esc(source.id)}" aria-pressed="${followed}" aria-label="${esc(t(followed ? 'unfollow' : 'follow')+' '+name)}">${icon(followed ? 'check' : 'heart')}${t(followed ? 'following' : 'follow')}</button>` : ''}<button type="button" class="timeline-action" data-share="${esc(p.url || '')}" data-share-title="${esc(name)}">${icon('arrow')}${words().share}</button></div><div class="feed-card-links">${reportLink({...p,name:p.title || name,countryCode:p.countryCode || source?.countryCode})}${link(p.url,words().original,'feed-open-link')}</div></footer></article>`;
}
export function timelineView(catalog,state = {},following = new Set(),limit = 24) {
  const posts = timelinePosts(catalog,state,following),shown=Math.min(posts.length,Math.max(1,limit));
  const noFollowing = (state.followed || state.kind === 'following') && !following.size;
  const emptyFeed = noFollowing ? `<div class="empty-state">${icon('heart')}<h2>${esc(words().noFollowing)}</h2><p>${esc(words().startFollowing)}</p>${link('/source/',esc(t('sources')),'button button-outline')}</div>` : empty();
  return `<section class="observatory-timeline" data-timeline><div class="feed-river-controls"><div class="feed-river-summary"><strong role="status">${t('results',{count:number(posts.length)})}</strong></div>${filterBar(state,catalog,'posts',following)}</div><div class="feed-river" data-timeline-grid>${posts.length ? posts.slice(0,shown).map((p,i)=>timelineCard(p,catalog.sources,following,catalog.events,i)).join('') : emptyFeed}</div><div class="feed-load-more-wrap" ${posts.length > shown ? 'data-timeline-more' : ''}><span class="feed-load-more-status" tabindex="-1">${t('showing',{shown:number(shown),total:number(posts.length)})}</span>${posts.length > shown ? `<button type="button" class="feed-load-more-button" data-action="more">${t('loadMore')}</button>` : ''}</div></section>`;
}

let autoLoadEnabled = false;
// Preserve the original site's shortest-column placement and document scrolling.
export function bindTimeline(root) {
  const timeline = root.querySelector('[data-timeline]');
  if (!timeline) return () => {};
  const grid = timeline.querySelector('[data-timeline-grid]');
  const cards = [...grid.querySelectorAll('[data-timeline-index]')].sort((a,b)=>Number(a.dataset.timelineIndex)-Number(b.dataset.timelineIndex));
  let columns = 0, resizeTimer, stopped = false;
  function distribute(force = false) {
    const width=grid.clientWidth || window.innerWidth;
    const count=window.innerWidth >= 901 ? 3 : Math.max(1,Math.min(2,Math.floor((width+14)/354)));
    if ((!force && count === columns) || !cards.length) return;
    const anchor = columns ? cards.find(card=>{const r=card.getBoundingClientRect();return r.top<window.innerHeight && r.bottom>80;}) : null;
    const anchorTop=anchor?.getBoundingClientRect().top;
    columns=count;
    const focus = document.activeElement;
    const fragment=document.createDocumentFragment();
    for(let i=0;i<count;i++){const column=document.createElement('div');column.className='feed-river-column';column.dataset.feedColumn=String(i+1);fragment.append(column);}
    grid.replaceChildren(fragment);
    const targets=[...grid.children];
    for(const card of cards){const shortest=targets.reduce((a,b)=>b.getBoundingClientRect().height<a.getBoundingClientRect().height?b:a,targets[0]);shortest.append(card);}
    if (focus && grid.contains(focus)) focus.focus({preventScroll:true});
    if(anchor && Number.isFinite(anchorTop)){const delta=anchor.getBoundingClientRect().top-anchorTop;if(Math.abs(delta)>1)window.scrollBy(0,delta);}
  }
  const images=[...grid.querySelectorAll('.home-feed-thumb img')];
  function orientation(event) {
    const image=event.target;
    if (!image.naturalWidth || !image.naturalHeight) return;
    const card=image.closest('.home-feed-card'),ratio=image.naturalWidth/image.naturalHeight;
    card.style.setProperty('--feed-image-aspect',`${image.naturalWidth} / ${image.naturalHeight}`);
    card.classList.toggle('home-feed-card-landscape',ratio>=1.05);
    card.classList.toggle('home-feed-card-portrait',ratio<=.95);
    clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!stopped)distribute(true);},80);
  }
  function imageError(event) {
    const image=event.target,card=image.closest('.home-feed-card');
    if(!card)return;
    image.closest('.home-feed-thumb')?.remove();
    card.querySelector('.home-feed-body')?.classList.add('home-feed-body-no-image');
    clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!stopped)distribute(true);},80);
  }
  images.forEach(image=>{
    if(image.complete){if(image.naturalWidth)orientation({target:image});else imageError({target:image});}
    image.addEventListener('load',orientation);image.addEventListener('error',imageError);
  });
  function expand(event) {
    if(event.target.closest('[data-action="more"]'))autoLoadEnabled=true;
    const button=event.target.closest('[data-expand-post]');
    if(button)queueMicrotask(()=>{button.closest('.home-feed-card')?.classList.toggle('home-feed-card-text-expanded',button.getAttribute('aria-expanded')==='true');distribute(true);});
  }
  function resize(){clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!stopped)distribute();},100);}
  distribute();
  window.addEventListener('resize',resize);
  timeline.addEventListener('click',expand);
  const marker=timeline.querySelector('[data-timeline-more]');
  let observer;
  if(marker && autoLoadEnabled && window.IntersectionObserver){observer=new window.IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();if(!stopped)marker.querySelector('[data-action="more"]')?.click();}},{rootMargin:'360px 0px'});observer.observe(marker);}
  return ()=>{stopped=true;clearTimeout(resizeTimer);window.removeEventListener('resize',resize);timeline.removeEventListener('click',expand);images.forEach(image=>{image.removeEventListener('load',orientation);image.removeEventListener('error',imageError);});observer?.disconnect();};
}

function platformIconSvg(key) {
  if (key === "facebook") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 13.5H16.5L17.5 9.5H14V7.5C14 6.47062 14 5.5 16 5.5H17.5V2.1401C17.1743 2.09685 15.943 2 14.6429 2C11.9284 2 10 3.65686 10 6.69971V9.5H7V13.5H10V22H14V13.5Z"/></svg>`;
  }
  if (key === "instagram") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.001 9C10.3436 9 9.00098 10.3431 9.00098 12C9.00098 13.6573 10.3441 15 12.001 15C13.6583 15 15.001 13.6569 15.001 12C15.001 10.3427 13.6579 9 12.001 9ZM12.001 7C14.7614 7 17.001 9.2371 17.001 12C17.001 14.7605 14.7639 17 12.001 17C9.24051 17 7.00098 14.7629 7.00098 12C7.00098 9.23953 9.23808 7 12.001 7ZM18.501 6.74915C18.501 7.43926 17.9402 7.99917 17.251 7.99917C16.5609 7.99917 16.001 7.4384 16.001 6.74915C16.001 6.0599 16.5617 5.5 17.251 5.5C17.9393 5.49913 18.501 6.0599 18.501 6.74915ZM12.001 4C9.5265 4 9.12318 4.00655 7.97227 4.0578C7.18815 4.09461 6.66253 4.20007 6.17416 4.38967C5.74016 4.55799 5.42709 4.75898 5.09352 5.09255C4.75867 5.4274 4.55804 5.73963 4.3904 6.17383C4.20036 6.66332 4.09493 7.18811 4.05878 7.97115C4.00703 9.0752 4.00098 9.46105 4.00098 12C4.00098 14.4745 4.00753 14.8778 4.05877 16.0286C4.0956 16.8124 4.2012 17.3388 4.39034 17.826C4.5591 18.2606 4.7605 18.5744 5.09246 18.9064C5.42863 19.2421 5.74179 19.4434 6.17187 19.6094C6.66619 19.8005 7.19148 19.9061 7.97212 19.9422C9.07618 19.9939 9.46203 20 12.001 20C14.4755 20 14.8788 19.9934 16.0296 19.9422C16.8117 19.9055 17.3385 19.7996 17.827 19.6106C18.2604 19.4423 18.5752 19.2402 18.9074 18.9085C19.2436 18.5718 19.4445 18.2594 19.6107 17.8283C19.8013 17.3358 19.9071 16.8098 19.9432 16.0289C19.9949 14.9248 20.001 14.5389 20.001 12C20.001 9.52552 19.9944 9.12221 19.9432 7.97137C19.9064 7.18906 19.8005 6.66149 19.6113 6.17318C19.4434 5.74038 19.2417 5.42635 18.9084 5.09255C18.573 4.75715 18.2616 4.55693 17.8271 4.38942C17.338 4.19954 16.8124 4.09396 16.0298 4.05781C14.9258 4.00605 14.5399 4 12.001 4ZM12.001 2C14.7176 2 15.0568 2.01 16.1235 2.06C17.1876 2.10917 17.9135 2.2775 18.551 2.525C19.2101 2.77917 19.7668 3.1225 20.3226 3.67833C20.8776 4.23417 21.221 4.7925 21.476 5.45C21.7226 6.08667 21.891 6.81333 21.941 7.8775C21.9885 8.94417 22.001 9.28333 22.001 12C22.001 14.7167 21.991 15.0558 21.941 16.1225C21.8918 17.1867 21.7226 17.9125 21.476 18.55C21.2218 19.2092 20.8776 19.7658 20.3226 20.3217C19.7668 20.8767 19.2076 21.22 18.551 21.475C17.9135 21.7217 17.1876 21.89 16.1235 21.94C15.0568 21.9875 14.7176 22 12.001 22C9.28431 22 8.94514 21.99 7.87848 21.94C6.81431 21.8908 6.08931 21.7217 5.45098 21.475C4.79264 21.2208 4.23514 20.8767 3.67931 20.3217C3.12348 19.7658 2.78098 19.2067 2.52598 18.55C2.27848 17.9125 2.11098 17.1867 2.06098 16.1225C2.01348 15.0558 2.00098 14.7167 2.00098 12C2.00098 9.28333 2.01098 8.94417 2.06098 7.8775C2.11014 6.8125 2.27848 6.0875 2.52598 5.45C2.78014 4.79167 3.12348 4.23417 3.67931 3.67833C4.23514 3.1225 4.79348 2.78 5.45098 2.525C6.08848 2.2775 6.81348 2.11 7.87848 2.06C8.94514 2.0125 9.28431 2 12.001 2Z"/></svg>`;
  }
  if (key === "threads") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.1835 1.41016L12.1822 1.41016C9.09012 1.43158 6.70036 2.47326 5.09369 4.51569C3.66581 6.33087 2.93472 8.86436 2.91016 12.0068V12.0082C2.93472 15.1508 3.66586 17.6696 5.09369 19.4847C6.70043 21.5271 9.10257 22.5688 12.1946 22.5902H12.1958C14.944 22.5711 16.8929 21.8504 18.4985 20.2463C20.6034 18.1434 20.5408 15.5048 19.8456 13.8832C19.3163 12.6493 18.2709 11.6618 16.8701 11.0477C16.6891 8.06345 15.0097 6.32178 12.2496 6.30415C10.6191 6.29409 9.14792 7.02378 8.24685 8.39104L9.90238 9.5267C10.4353 8.71818 11.2789 8.32815 12.2371 8.33701C13.6244 8.34586 14.5362 9.11128 14.7921 10.4541C14.02 10.3333 13.1902 10.2982 12.3076 10.3488C9.66843 10.5008 7.9399 12.061 8.05516 14.2244C8.17571 16.4862 10.367 17.7186 12.4476 17.605C14.9399 17.4684 16.4209 15.6292 16.7722 13.2836C17.3493 13.6575 17.7751 14.1344 18.0163 14.6969C18.4559 15.7222 18.4838 17.4132 17.1006 18.7952C15.8838 20.0108 14.4211 20.5407 12.1891 20.5572C9.71428 20.5388 7.85698 19.746 6.65154 18.2136C5.51973 16.7748 4.92843 14.6882 4.90627 12.0002C4.92843 9.31211 5.51973 7.22549 6.65154 5.78673C7.85698 4.25433 9.71424 3.46156 12.189 3.44303C14.6819 3.4617 16.5728 4.25837 17.8254 5.79937C18.5162 6.64934 18.949 7.66539 19.2379 8.71407L21.1776 8.19656C20.8148 6.85917 20.2414 5.58371 19.363 4.50305C17.7098 2.46918 15.2816 1.43166 12.1835 1.41016ZM12.4204 12.3782C13.3044 12.3272 14.1239 12.3834 14.8521 12.5345C14.7114 14.1116 14.0589 15.4806 12.3401 15.575C11.2282 15.6376 10.1031 15.1413 10.0484 14.114C10.0077 13.3503 10.5726 12.4847 12.4204 12.3782Z"/></svg>`;
  }
  if (key === "youtube") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.2439 4C12.778 4.00294 14.1143 4.01586 15.5341 4.07273L16.0375 4.09468C17.467 4.16236 18.8953 4.27798 19.6037 4.4755C20.5486 4.74095 21.2913 5.5155 21.5423 6.49732C21.942 8.05641 21.992 11.0994 21.9982 11.8358L21.9991 11.9884L21.9991 11.9991C21.9991 11.9991 21.9991 12.0028 21.9991 12.0099L21.9982 12.1625C21.992 12.8989 21.942 15.9419 21.5423 17.501C21.2878 18.4864 20.5451 19.261 19.6037 19.5228C18.8953 19.7203 17.467 19.8359 16.0375 19.9036L15.5341 19.9255C14.1143 19.9824 12.778 19.9953 12.2439 19.9983L12.0095 19.9991L11.9991 19.9991C11.9991 19.9991 11.9956 19.9991 11.9887 19.9991L11.7545 19.9983C10.6241 19.9921 5.89772 19.941 4.39451 19.5228C3.4496 19.2573 2.70692 18.4828 2.45587 17.501C2.0562 15.9419 2.00624 12.8989 2 12.1625V11.8358C2.00624 11.0994 2.0562 8.05641 2.45587 6.49732C2.7104 5.51186 3.45308 4.73732 4.39451 4.4755C5.89772 4.05723 10.6241 4.00622 11.7545 4H12.2439ZM9.99911 8.49914V15.4991L15.9991 11.9991L9.99911 8.49914Z"/></svg>`;
  }
  if (key === "x") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10.4883 14.651L15.25 21H22.25L14.3917 10.5223L20.9308 3H18.2808L13.1643 8.88578L8.75 3H1.75L9.26086 13.0145L2.31915 21H4.96917L10.4883 14.651ZM16.25 19L5.75 5H7.75L18.25 19H16.25Z"/></svg>`;
  }
  if (key === "rss") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 17C5.20914 17 7 18.7909 7 21H3V17ZM3 10C9.07513 10 14 14.9249 14 21H12C12 16.0294 7.97056 12 3 12V10ZM3 3C12.9411 3 21 11.0589 21 21H19C19 12.1634 11.8366 5 3 5V3Z"/></svg>`;
  }
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle class="platform-icon-stroke" cx="12" cy="12" r="7"/><path class="platform-icon-stroke" d="M5 12h14M12 5c2 2 3 4.3 3 7s-1 5-3 7M12 5c-2 2-3 4.3-3 7s1 5 3 7"/></svg>`;
}
