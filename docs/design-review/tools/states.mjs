// Screenshot inventory for the design review. docs/design-review/states.md
// documents the same IDs; change both together and only between rounds that
// re-shoot the baseline.
//
// catalog: normal | empty | error | loading      session: out | in
// click:   selectors clicked in order after load  anchor: start the shot here
export const SIZES = {
  desktop: { width: 2560, height: 1440, deviceScaleFactor: 1, maxHeight: 2160 },
  mobile: { width: 390, height: 844, deviceScaleFactor: 2, maxHeight: 1688, isMobile: true, hasTouch: true },
};

const RICH = '/source/54-cy-leo/';
const SPARSE = '/source/134-crossover-harmonica-ensemble/';

export const STATES = [
  // Home
  { id: 'home-zh', path: '/', lang: 'zh-Hant' },
  { id: 'home-en', path: '/', lang: 'en' },
  { id: 'home-ja', path: '/', lang: 'ja' },
  { id: 'home-ko', path: '/', lang: 'ko' },
  { id: 'home-feed-zh', path: '/', lang: 'zh-Hant', anchor: '.home-posts' },
  { id: 'home-dark-zh', path: '/', lang: 'zh-Hant', theme: 'dark' },
  { id: 'home-loading-zh', path: '/', lang: 'zh-Hant', catalog: 'loading' },
  { id: 'home-error-zh', path: '/', lang: 'zh-Hant', catalog: 'error' },
  { id: 'home-empty-zh', path: '/', lang: 'zh-Hant', catalog: 'empty' },
  { id: 'menu-open-zh', path: '/', lang: 'zh-Hant', click: ['.nav-more > summary'], viewportOnly: true },
  { id: 'home-signed-in-zh', path: '/', lang: 'zh-Hant', session: 'in', viewportOnly: true },
  // Posts
  { id: 'posts-zh', path: '/post/', lang: 'zh-Hant' },
  { id: 'posts-en', path: '/post/', lang: 'en' },
  { id: 'posts-search-zh', path: '/post/?q=%E5%8F%A3%E7%90%B4%E6%A8%82%E5%9C%98', lang: 'zh-Hant' },
  { id: 'posts-no-results-zh', path: '/post/?q=zzqxv', lang: 'zh-Hant' },
  { id: 'posts-following-empty-zh', path: '/post/?kind=following', lang: 'zh-Hant' },
  { id: 'posts-expanded-zh', path: '/post/', lang: 'zh-Hant', click: ['[data-expand-post]'], anchor: '[data-expand-post]' },
  { id: 'posts-empty-zh', path: '/post/', lang: 'zh-Hant', catalog: 'empty' },
  // Events
  { id: 'events-zh', path: '/events/', lang: 'zh-Hant' },
  { id: 'events-ja', path: '/events/', lang: 'ja' },
  { id: 'events-past-zh', path: '/events/?period=past', lang: 'zh-Hant' },
  { id: 'events-country-zh', path: '/events/?country=JP&period=allEvents', lang: 'zh-Hant' },
  { id: 'events-empty-zh', path: '/events/', lang: 'zh-Hant', catalog: 'empty' },
  // Sources directory and detail
  { id: 'sources-zh', path: '/source/', lang: 'zh-Hant' },
  { id: 'sources-ko', path: '/source/', lang: 'ko' },
  { id: 'sources-search-zh', path: '/source/?q=%E5%8F%A3%E7%90%B4%E7%A4%BE', lang: 'zh-Hant' },
  { id: 'sources-country-zh', path: '/source/?country=JP', lang: 'zh-Hant' },
  { id: 'sources-followed-empty-zh', path: '/source/?followed=1', lang: 'zh-Hant' },
  { id: 'source-detail-zh', path: RICH, lang: 'zh-Hant' },
  { id: 'source-detail-en', path: RICH, lang: 'en' },
  { id: 'source-detail-sparse-zh', path: SPARSE, lang: 'zh-Hant' },
  // Scores
  { id: 'scores-zh', path: '/scores/', lang: 'zh-Hant' },
  { id: 'scores-no-results-zh', path: '/scores/?q=zzqxv', lang: 'zh-Hant' },
  { id: 'score-sources-zh', path: '/scores/sources/', lang: 'zh-Hant' },
  { id: 'score-sources-books-en', path: '/scores/sources/?scoreKind=books', lang: 'en' },
  // Community and information
  { id: 'contribute-zh', path: '/contribute/', lang: 'zh-Hant' },
  { id: 'contribute-signed-in-zh', path: '/contribute/', lang: 'zh-Hant', session: 'in' },
  { id: 'submit-zh', path: '/submit/', lang: 'zh-Hant' },
  { id: 'submit-signed-in-zh', path: '/submit/', lang: 'zh-Hant', session: 'in', anchor: '#submission-form' },
  { id: 'feeds-zh', path: '/feeds/', lang: 'zh-Hant' },
  { id: 'status-zh', path: '/status/', lang: 'zh-Hant' },
  { id: 'about-zh', path: '/about/', lang: 'zh-Hant' },
  { id: 'about-faq-open-zh', path: '/about/', lang: 'zh-Hant', click: ['details.faq summary'], anchor: 'details.faq' },
  { id: 'privacy-zh', path: '/privacy/', lang: 'zh-Hant' },
  { id: 'not-found', path: '/no-such-page/', lang: 'zh-Hant' },
];

// Reference sites: photographed once and reused in every round.
export const REFERENCES = [
  { id: 'luma-discover', url: 'https://luma.com/discover' },
  { id: 'luma-city-calendar', url: 'https://luma.com/taipei' },
  { id: 'bandsintown-home', url: 'https://www.bandsintown.com/' },
  { id: 'bandsintown-artist', url: 'https://www.bandsintown.com/a/15521707-the-search' },
  { id: 'bluesky-profile-feed', url: 'https://bsky.app/profile/bsky.app' },
];

export const SIGNED_IN_SESSION = {
  csrfToken: 'preview', identity: 'google', googleLoginEnabled: true,
  account: { name: '林小美', email: 'mei.lin@example.com' },
  contributions: [{ id: 'apy_0123456789abcdef0123', name: '小美的 Apify 額度', status: 'active', budgetUsd: 5, spentUsd: 1.24, reservedUsd: 0.31, budgetRemainingUsd: 3.45 }],
  submissions: [
    { id: 'sub_demo1', url: 'https://www.instagram.com/example.harmonica/', note: '台中的口琴社團，每月有公開練習', countryCode: 'TW', status: 'pending', createdAt: '2026-11-01T10:00:00Z' },
    { id: 'sub_demo2', url: 'https://www.facebook.com/example.ensemble', note: '', countryCode: 'JP', status: 'accepted', createdAt: '2026-10-12T03:00:00Z' },
  ],
};

// Fixed clock: the snapshot's evaluation time, so relative times never drift.
export const NOW = '2026-11-05T17:30:00+08:00';
