# v2c1 blind review: Claude Opus 5.5 (effort high)

Post-hill-climb regression check for the stylesheet consolidation, catalog
loading and small-text changes. Raw reviewer output below, unedited.

- Date: 2026-11-12
- Brief: `brief-v2.md`, SHA-256 `edf74b5ace37af3e0b83bd6384eeb0d059508f5f06f2872ced4c30bc65cf371b`
- Reviewer: claude-proxy `claude-opus-5-5`, effort high, no other context
- Mapping (revealed after the review): **A = new** (branch `css-consolidation`), **B = reference**, **C = baseline** (`main` at `b6f6797`)
- Site sets: 45 states × desktop (2560×1440) and mobile (390) = 90 images each, from the frozen public catalog of 2026-11-12 (366 sources, 563 posts, 1 active story, 15 events, 797 scores); browser clock fixed at 2026-11-05 17:30 Asia/Taipei
- Reference set: 6 sites × 2 sizes, re-shot on 2026-11-12 with `tools/capture.mjs references`

| Set | Mean of 12 scores |
|---|---:|
| A (new) | 7.25 |
| C (baseline) | 7.13 |
| B (reference) | 7.71 |

The new set scores the same as or higher than the baseline in every category;
typography, navigation and accessibility are +0.5, citing the larger mobile
tab labels, footer and menu text. The remaining issues the reviewer lists
apply equally to both versions.

---

## 組 A
一句話總評：這是口琴觀測站的成熟版本。品牌配色、空狀態、手機版的表格轉卡片都做得完整；主要扣分在 1440p 寬螢幕留白太多、次要文字偏小偏淡、貢獻與狀態頁的技術用語外露。A 和 C 版面幾乎完全相同，只有 A 的小字（手機分頁標籤、頁尾、選單與統計標籤）略大一些。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | home-zh desktop：H1「全球口琴公開資訊，一站看完」、副標，加上 366／32／7／797 四個統計數字，一進來就知道網站是做什麼的。接著是「近 24 小時限動」和「接下來的活動」，日期方塊（11月／14／週六）放在每列最左邊，最先被看到。sources-zh desktop 的表格欄位依序是名稱、國家、類型、連結、動態、更新、追蹤，主次清楚。扣分：source-detail-zh desktop 的限動卡片幾乎全是圖片，日期和平台只是小字；submit-zh desktop 右欄的「名錄面向世界，收錄範圍隨已驗證的公開來源逐步擴展。」字級比表單標題「提供來源」還大，和主任務搶注意力。 |
| 字體排印 | 7 | 繁中標題字重與字級分明（home-zh、sources-zh），日文 events-ja、韓文 sources-ko 都沒有缺字或斷行錯誤。手機分頁標籤和頁尾連結約 12 CSS px（not-found mobile 兩字標籤寬 48 device px），可以讀。扣分：desktop 1x 下的次要文字只有約 12–13 px，例如 sources-zh 的描述列、scores-zh 的「作曲:／編曲:」、status-zh 的「最近成功檢查來源: 11月12日 · 18:15」。中文裡混用半形冒號「作曲: 林家靖」「提供者: 黃石樂器」。score-sources-books-en mobile 的「Recorded details & original text •」換行後，日期被擠到下一行單獨成行。 |
| 色彩 | 7.5 | 深綠品牌色（logo、主要按鈕「驗證並貢獻」「送出審核」、已登入的「我的帳號」）搭米白底，系統一致。目前頁面的導覽項用淺綠底標示。語意色：contribute-signed-in-zh 的「撤回貢獻」用淡紅底，「有效」用綠灰 chip。home-dark-zh 兩種尺寸的深色外觀都成立。扣分：status-zh desktop 的「已暫停」（橘棕）、「需要留意」（紅）和頁首的棕點色相太接近，一眼分不出嚴重程度；首頁內嵌的行事曆用藍、綠、紅圓點和灰底，和品牌色是兩套系統。 |
| 間距與版面 | 6.5 | 所有 desktop 截圖的內容區只有約 1220 CSS px，在 2560 寬的螢幕上左右各空約 500 px（例如 sources-zh、source-detail-zh、scores-zh），沒有利用到 1440p。privacy-zh desktop 右側的「聯絡與回饋」卡片右緣停在約 1396 px（顯示座標），沒有對齊上方容器右緣 1609 px；about-zh 的同一張卡片則有對齊。about-zh、feeds-zh desktop 下半部都是大片空白。優點：卡片、表格、表單的內距節奏一致，沒有看到溢出或重疊。 |
| 一致性 | 7.5 | 空狀態一律是虛線圓角卡片，內容是圖示、標題、說明、一個按鈕（sources-followed-empty、source-detail-sparse、scores-no-results、posts-no-results），非常一致。外框按鈕、chip、圓角與陰影整站同一套。扣分：home-zh 的行事曆元件（「今天」藥丸按鈕、「12 11月, 週四」格式、藍綠圓點）是另一套視覺語言；半形和全形冒號混用；about 與 privacy 的側欄卡片對齊方式不同。 |
| 資訊密度 | 7 | sources-zh desktop 一屏可看到約 24 筆來源，密度好；mobile 版改成卡片後，每筆仍有國家、類型、連結圖示、動態數與更新日期。扣分：source-detail-zh desktop 的貼文是 3 欄大圖卡，一屏只放得下約 6 張，mobile 一屏不到 2 張；scores-zh desktop 每首曲目佔 4 行高，「出版者／提供者」欄大多只有一行字，留白很多。 |
| 導覽 | 8 | Desktop 頁首有 6 個主項目，目前位置用淺綠底標示；「更多」選單（menu-open-zh desktop）分成「參與與訂閱」「瀏覽設定」（語言下拉選單，加上淺色／深色／系統分段控制）和底部連結，組織清楚。Mobile 頁首下方是 6 格圖示加文字的分頁列，目前頁面有淺綠底，單手可達。來源頁有「← 回到來源名錄」；sources-zh 有「顯示 24／33 筆」和「顯示更多 +」。scores 的「比賽指定曲 797／找譜與購譜 39」分頁帶有計數。 |
| 狀態與回饋 | 8 | 涵蓋載入骨架（home-loading）、錯誤、空資料、搜尋無結果（「沒有符合條件的曲目」加「清除篩選」）、未追蹤（「你還沒有追蹤任何來源」加「瀏覽全部來源」，並說明追蹤清單只存在這個瀏覽器）、來源沒有貼文（「前往原始來源 ↗」）、登入前後（頁首由「Google 登入」變成「我的帳號」，帳號卡顯示姓名、Email 和「登出」）、FAQ 展開時 + 變 −。扣分：home-error desktop 整頁只剩一張提示卡，其他可用的導引都沒有保留；contribute-zh 的額度卡用「尚無資料」當大字數值。 |
| 響應式 | 8 | 手機不是單純縮放：sources 表格改成卡片，並另外提供「排序」下拉和「遞增」按鈕；篩選收進「篩選 (1)」按鈕，還會顯示已套用幾個條件；status-zh 的服務表格改成每個服務一張卡片；contribute-zh 的額度側欄移到表單下方；scores-zh 的表格改成卡片。沒看到橫向溢出。扣分：submit-zh mobile 的世界名錄說明塊排到「我的提供紀錄」之後；source-detail-en mobile 簡介截斷後，「▶ View original」和「Read the full text」上下排列，關係不清楚。 |
| 文案 | 7 | 繁中整體自然，例如「每則都連回原始來源」「追蹤清單只儲存在這個瀏覽器」；英、日、韓的介面字串都有對應翻譯（posts-en、events-ja、sources-ko）。扣分：contribute-zh 外露技術詞，例如 Apify、API 金鑰、抓取額度、「預留給進行中抓取的費用」，「目前無可靠估計」重複 3 次；status-zh 有「未知（來源檢查尚未確認）」「24 小時內成功檢查來源」這類系統語氣；about-zh 提到「竹梅活動觀測站 ↗」，一般使用者看不懂它和本站的關係。 |
| 無障礙 | 6.5 | Mobile 的按鈕、追蹤鈕、分頁列點擊範圍都夠大（sources-country mobile 的「追蹤」約 92×50 CSS px）。扣分：desktop 灰色次要字小又淡（sources-zh 描述、scores-zh 的「原始備註」、footer）；sources-zh desktop 的「來源連結」欄只有圖示，沒有文字；「回報資料」「Report」是低對比的純文字連結；所有截圖都看不到焦點樣式的線索。 |
| 動畫與轉場 | 6 | 靜態線索：home-loading 有骨架屏；FAQ 展開時 + 變 −；「更多」展開時箭頭由 ▾ 變 ▴，選單是浮層卡片；長文「展開」後有對應的收合狀態。轉場本身看不到，依規則給保守分數。 |

要保留的優點：
- 空狀態元件（虛線卡、圖示、標題、說明、單一行動按鈕）在追蹤、搜尋、來源無貼文、樂譜無結果之間完全一致，而且每個都有下一步。
- 手機頂部的 6 格圖示分頁列，目前頁面用淺綠底標示，主要頁面一按就到。
- 來源名錄的手機卡片和排序控制（「排序」下拉加「遞增」按鈕），以及篩選按鈕上的已套用數量「篩選 (1)」。
- 系統狀態頁的服務表格在手機上轉成每個服務一張卡片，資訊完整、沒有橫向捲動。
- 「更多」選單把語言和外觀（淺色／深色／系統）集中在「瀏覽設定」，結構清楚。
- 活動列表一致使用「月、日、星期」日期方塊，最重要的日期資訊最先被看到。

最重要的五個問題（由嚴重到輕微）：
1. [間距與版面] [sources-zh、source-detail-zh、scores-zh、about-zh] [desktop] 內容區只有約 1220 CSS px，在 2560 寬螢幕上左右共約 1000 px 空白，about 和 feeds 下半頁也是空的 —— 1440p 使用者一屏看到的內容少，頁面顯得空 —— 建議把容器放寬到 1440–1600 px，或在寬螢幕改用多欄（來源頁加側欄、樂譜表格加寬、限動改 4–5 欄）。
2. [字體排印／無障礙] [sources-zh、scores-zh、status-zh、footer] [desktop] 次要資訊約 12–13 px 而且是淡灰色（描述、作曲／編曲、最近成功檢查時間、頁尾），1x 寬螢幕上很難讀，來源連結欄又只有圖示 —— 長輩口琴愛好者的閱讀負擔大 —— 建議 desktop 內文最小 14 px、加深灰字對比，連結圖示加 tooltip 或文字標籤。
3. [文案] [contribute-zh、contribute-signed-in-zh、status-zh] [兩者] 「Apify」「API 金鑰」「抓取額度」「預留給進行中抓取的費用」「目前無可靠估計」×3、「尚無資料」被當成大字數值、「未知（來源檢查尚未確認）」等系統語言直接外露 —— 一般社群成員看不懂，也會降低對網站的信任 —— 建議把技術細節收進「進階說明」，數值不可用時改顯示「—」加一句白話說明，同一個估計訊息合併成一行。
4. [一致性] [home-zh、privacy-zh、scores-zh] [desktop] 首頁內嵌的行事曆元件是另一套視覺語言（灰底、藍綠圓點、「12 11月, 週四」格式）；privacy 側欄卡片沒有對齊容器右緣；「作曲: 」「提供者: 」用半形冒號 —— 這些小地方削弱了整站的完成度 —— 建議行事曆套用站內色票與日期格式，側欄統一對齊，中文介面統一用全形「：」。
5. [資訊密度／色彩] [source-detail-zh、status-zh] [兩者] 來源頁限動卡片幾乎全是大圖，mobile 一屏不到 2 則；狀態頁的「已暫停」和「需要留意」色相太接近 —— 前者讓使用者難以掃讀時間軸，後者讓人分不出嚴重程度 —— 建議限動改成較矮的縮圖格線或橫向捲動列；狀態色拉開成綠、黃、紅三階，並加上圖示。

## 組 B
一句話總評：B 是參考組，包含 Accupass、Bandsintown、Bluesky、Luma 四個成熟商業產品。視覺品牌和互動成熟度都高，但寬螢幕利用、商業干擾與可見的狀態覆蓋各有不足。這些頁面的數量和內容都和口琴觀測站不同，只用同一把尺評它們自己的產品。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | luma-city-calendar desktop：城市標題下面是依日期分組的活動時間軸，每筆有時間、標題、主辦與縮圖，日期最先被看到。bandsintown-artist desktop：藝人主視覺、追蹤按鈕、近期演出列表的主次清楚。扣分：accupass-home desktop 首屏被大型輪播橫幅和多條推薦帶佔據，使用者要找的搜尋或分類不是第一焦點。 |
| 字體排印 | 8 | Luma、Bluesky 的無襯線字階清楚，行高舒適（luma-city-calendar、bluesky-profile-feed desktop）；Accupass 的中文標題粗細分明。扣分：accupass-home 卡片上的次要資訊字很小；Bluesky 貼文 metadata 灰字偏小。 |
| 色彩 | 8.5 | 四個品牌識別都很強：Bandsintown 的品牌色和深色區塊、Luma 的柔和漸層與白卡、Bluesky 的藍色系、Accupass 的多彩分類。扣分：accupass-home 的大量海報、多彩橫幅互相競爭，整頁色彩雜訊高。 |
| 間距與版面 | 7.5 | luma-city-calendar desktop 卡片和時間軸的節奏乾淨。扣分：bluesky-profile-feed desktop 的中央動態欄很窄，2560 寬螢幕兩側大量空白；accupass-search-harmonica desktop 整頁只有 1440 高、內容稀少，大面積留白。 |
| 一致性 | 8 | 各產品內部的按鈕、卡片、圓角都同一套。Bluesky 的貼文卡、Luma 的活動卡在 desktop 與 mobile 一致。扣分：accupass-home 的各推薦區塊卡片尺寸和樣式不一。 |
| 資訊密度 | 7.5 | luma-city-calendar 和 bluesky-profile-feed 一屏能看到多筆有用內容。扣分：accupass-home mobile 長頁大半是橫幅與輪播；bandsintown-home 的大圖卡片讓一屏筆數偏少。 |
| 導覽 | 8.5 | bluesky-profile-feed mobile 有底部分頁列，desktop 有左側主導覽與個人頁分頁（貼文、回覆、媒體等）；Luma、Accupass 頁首都有搜尋入口。扣分：Bandsintown 手機版的主要導覽入口較隱晦。 |
| 狀態與回饋 | 6.5 | 可見的狀態有限：accupass-search-harmonica 能看到搜尋結果頁的呈現，其他截圖大多是有資料的正常狀態；載入、錯誤、空資料、登入前後都看不到。依規則保守評分。 |
| 響應式 | 8.5 | 四者手機版都重新排版，不是單純縮放：bluesky 改用底部分頁列，luma 改成單欄時間軸，accupass 把卡片改成橫向捲動或單欄，bandsintown-artist mobile 的演出列表維持可點的列高。沒看到橫向溢出。 |
| 文案 | 8 | 文案簡短、以行動為導向（追蹤、購票、RSVP 等），符合各自情境。扣分：accupass-home 的行銷用語與促銷字樣多。 |
| 無障礙 | 7 | 手機點擊範圍普遍充足（bluesky、luma mobile）。扣分：accupass-home 的海報圖上壓文字，對比沒有保證；Bluesky、Luma 的 metadata 灰字對比偏低；截圖中看不到焦點樣式的線索。 |
| 動畫與轉場 | 6.5 | 可見線索有 accupass-home 的輪播指示點、luma 的時間軸標記、bluesky 的分頁底線指示；轉場本身看不到，依規則給保守分數。 |

要保留的優點：
- Luma 城市行事曆依日期分組的時間軸：日期在左、卡片在右，非常好掃讀（luma-city-calendar 兩種尺寸）。
- Bluesky 手機的底部分頁列，加上個人頁的內容分頁，在動態類頁面的導覽效率高。
- Bandsintown 藝人頁把「追蹤」和近期演出列表放在首屏，主要行動明確。
- 四個產品各自有強烈且一貫的品牌色。
- 手機版都重新設計資訊結構，而不是單純縮小。

最重要的五個問題（由嚴重到輕微）：
1. [資訊層級／資訊密度] [accupass-home] [兩者] 首屏和大半頁面被輪播橫幅、推薦帶佔據 —— 真正要找活動的使用者要多次捲動 —— 建議把搜尋、分類、近期活動往上提，減少橫幅數量。
2. [間距與版面] [bluesky-profile-feed] [desktop] 2560 寬螢幕上中央欄很窄，兩側大量空白 —— 1440p 使用效率低 —— 建議在寬螢幕顯示更多側欄資訊，或加寬內容欄。
3. [狀態與回饋] [accupass-search-harmonica 等] [兩者] 截圖裡幾乎看不到載入、錯誤、空資料或登入前後的狀態設計，無法確認回饋是否完整 —— 建議補齊這些狀態並給出下一步。
4. [無障礙] [accupass-home、luma-city-calendar] [兩者] 圖片上壓文字和淡灰 metadata 的對比偏低 —— 弱視者、戶外使用時難讀 —— 建議文字加遮罩，灰字提高對比。
5. [間距與版面] [accupass-search-harmonica] [desktop] 結果頁內容稀少，版面大面積留白，也沒有推薦或放寬搜尋的引導 —— 小眾關鍵字（口琴）在這裡容易走到死路 —— 建議提供相關分類、放寬條件或訂閱提醒。

## 組 C
一句話總評：C 和 A 是同一套口琴觀測站設計，版面、色彩、元件、狀態幾乎逐像素相同（home-en、posts-en、score-sources-books-en 的 desktop 差異為 0）。差別只在 C 的小字更小：手機分頁標籤和頁尾連結約 10.5 CSS px（A 約 12 px），頁首副標「HARMONICA OBSERVATORY」、更多選單的分區與底部連結、貢獻頁的統計標籤也都略小。所以字體排印、導覽、無障礙比 A 低半分。

| 項目 | 分數 | 證據（頁面／狀態 ID、尺寸、看到的事實） |
|---|---|---|
| 資訊層級 | 8 | 和 A 相同：home-zh desktop 有 H1「全球口琴公開資訊，一站看完」、四個統計數字和活動日期方塊；sources-search-zh desktop 有「共 33 筆」、名稱粗體加描述的表格。扣分相同：source-detail-zh 的限動卡以大圖為主；submit-zh desktop 右欄的「名錄面向世界…」標題比表單標題大。 |
| 字體排印 | 6.5 | 繁中、日文（events-ja）、韓文（sources-ko）都正確顯示。扣分：手機分頁列標籤（首頁、動態、活動…）約 10.5 CSS px（not-found mobile 兩字標籤寬只有 42 device px），頁尾連結「關於與常見問題」「隱私說明」等也約 10.5 px（sources-followed-empty mobile），明顯偏小。desktop 的次要字和 A 一樣約 12–13 px，更多選單底部的「系統狀態」「關於與常見問題」「隱私說明」比 A 再小一些。中文半形冒號問題相同（scores-zh 的「作曲: 林家靖」、status-zh 的「最近成功檢查來源: 10月15日」）。 |
| 色彩 | 7.5 | 和 A 相同：深綠搭米白的品牌系統；contribute-signed-in-zh 的「撤回貢獻」用淡紅底；home-dark-zh 的深色外觀成立。扣分相同：status-zh desktop 的「已暫停」「需要留意」色相接近；首頁行事曆的藍綠圓點自成一套。 |
| 間距與版面 | 6.5 | 和 A 相同：所有 desktop 內容區約 1220 CSS px，左右空約 500 px（sources-country-zh、score-sources-zh）；privacy-zh desktop 的側欄卡片右緣沒有對齊容器（約 1396 對 1609 顯示座標）；feeds-zh desktop 右欄在 ICS 區只有一項，JSON 區右半全空。 |
| 一致性 | 7.5 | 和 A 相同：空狀態卡（source-detail-sparse-zh、scores-no-results-zh、sources-followed-empty-zh）和外框按鈕、chip 都一致。扣分相同：首頁行事曆元件風格不同；全形和半形冒號混用。 |
| 資訊密度 | 7 | sources-zh、sources-country-zh desktop 一屏可看到 21–24 筆；scores-zh mobile 卡片把年度、編制、組別、國家壓成一行。扣分相同：source-detail-zh mobile 一屏不到 2 則限動；scores-zh desktop 每列 4 行高。 |
| 導覽 | 7.5 | 結構和 A 相同：desktop 有 6 個主項目和更多選單，mobile 有 6 格分頁列，加上「← 回到來源名錄」和 scores 的分頁計數。扣分：分頁列文字只有約 10.5 px，手機上辨識度比 A 差，長者需要靠圖示猜。 |
| 狀態與回饋 | 8 | 和 A 相同：scores-no-results-zh 有「沒有符合條件的曲目」加「清除篩選」；sources-followed-empty-zh 有「你還沒有追蹤任何來源」加「瀏覽全部來源」；source-detail-sparse-zh 有「這個來源還沒有收錄的貼文」加「前往原始來源 ↗」；contribute-signed-in-zh 有帳號卡和「有效」chip；about-faq-open-zh 展開時 − 和 + 對照。扣分相同：contribute-zh 用「尚無資料」當大字數值。 |
| 響應式 | 8 | 和 A 相同：sources-country-zh mobile 有「篩選 (1)」、國家和類型下拉、「排序」加「遞增」；status-zh mobile 的服務表格轉成卡片；contribute-signed-in-zh mobile 把額度卡移到「貢獻 Apify 額度」下方。扣分相同：source-detail-en mobile 的「▶ View original」和「Read the full text」關係不清。 |
| 文案 | 7 | 和 A 相同：contribute-zh 有 Apify、API 金鑰、「目前無可靠估計」×3；status-zh 有「未知（來源檢查尚未確認）」；about-zh 有「竹梅活動觀測站 ↗」。sources-followed-empty-zh 的「在來源旁點愛心即可追蹤。追蹤清單只儲存在這個瀏覽器。」很好。 |
| 無障礙 | 6 | 追蹤按鈕、篩選按鈕的點擊範圍足夠（sources-country-zh mobile）。扣分：比 A 多了手機分頁標籤和頁尾 10.5 px 小字；desktop 的淡灰小字、圖示專用的「來源連結」欄（sources-search-zh desktop）、低對比的「回報資料」連結都和 A 相同；看不到焦點樣式的線索。 |
| 動畫與轉場 | 6 | 和 A 相同：有載入骨架（home-loading-zh）、FAQ 的 +／− 切換、更多選單的 ▴ 箭頭與浮層；轉場不可見，依規則給保守分數。 |

要保留的優點：
- 一致的空狀態卡片系統，每個空狀態都附一個明確的下一步按鈕。
- 手機版來源名錄的卡片、排序、篩選數量徽章「篩選 (1)」。
- 系統狀態在手機上改成每個服務一張卡片，桌面維持一張可比較的表格。
- 「更多」選單集中語言與外觀設定，外觀用分段控制，狀態一目了然。
- 已登入狀態：頁首深綠的「我的帳號」按鈕、帳號卡顯示 Email 並附「登出」，登入前後差異明確。
- 活動的「月、日、星期」日期方塊在首頁、活動頁、各語言中保持一致。

最重要的五個問題（由嚴重到輕微）：
1. [字體排印／無障礙] [所有頁面的手機分頁列與頁尾，例如 not-found、sources-followed-empty-zh] [mobile] 分頁標籤和頁尾連結只有約 10.5 CSS px，是全站最常看到的文字，卻小於一般建議的最小字級 —— 手機是主要使用情境，長輩讀者會看不清導覽 —— 建議至少 12 px，分頁列標籤 12–13 px 並維持粗細對比。
2. [間距與版面] [sources-zh、source-detail-zh、scores-zh、about-zh] [desktop] 內容區只有約 1220 CSS px，在 2560 寬螢幕上兩側空約 1000 px —— 1440p 一屏內容少 —— 建議放寬容器，或在寬螢幕改用多欄。
3. [文案] [contribute-zh、contribute-signed-in-zh、status-zh] [兩者] Apify、API 金鑰、抓取額度、「目前無可靠估計」×3、「尚無資料」大字、「未知（來源檢查尚未確認）」 —— 技術與系統語言外露 —— 建議白話化，把技術細節收進進階說明。
4. [字體排印／一致性] [sources-zh、scores-zh、status-zh、privacy-zh、home-zh] [desktop] 次要字約 12–13 px 而且偏淡；中文介面混用半形冒號；首頁行事曆是另一套視覺語言；privacy 側欄沒有對齊 —— 降低可讀性與完成度 —— 建議提高最小字級與對比，統一全形標點、行事曆樣式與側欄對齊。
5. [資訊密度／色彩] [source-detail-zh、status-zh] [兩者] 限動卡片大圖讓 mobile 一屏不到 2 則；狀態色「已暫停」和「需要留意」難以區分 —— 掃讀效率與嚴重程度判斷都受影響 —— 建議改用較矮的縮圖格線，狀態色拉開成三階並加上圖示。

```json
{"A": {"scores": {"資訊層級": 8, "字體排印": 7, "色彩": 7.5, "間距與版面": 6.5, "一致性": 7.5, "資訊密度": 7, "導覽": 8, "狀態與回饋": 8, "響應式": 8, "文案": 7, "無障礙": 6.5, "動畫與轉場": 6}, "issues": ["[間距與版面] sources-zh/source-detail-zh/scores-zh/about-zh desktop：內容區約 1220 CSS px，2560 寬螢幕兩側共約 1000 px 空白，未善用 1440p", "[字體排印/無障礙] sources-zh/scores-zh/status-zh/footer desktop：次要資訊約 12–13 px 淡灰小字，來源連結欄只有圖示", "[文案] contribute-zh/contribute-signed-in-zh/status-zh：Apify、API 金鑰、抓取額度、「目前無可靠估計」×3、「尚無資料」大字、「未知（來源檢查尚未確認）」等技術語言外露", "[一致性] home-zh 行事曆元件自成一套視覺語言；privacy-zh 側欄卡未對齊容器右緣；中文介面混用半形冒號（作曲: 、提供者: ）", "[資訊密度/色彩] source-detail-zh 限動大圖卡在 mobile 一屏不到 2 則；status-zh 的「已暫停」與「需要留意」色相過近"]}, "B": {"scores": {"資訊層級": 8, "字體排印": 8, "色彩": 8.5, "間距與版面": 7.5, "一致性": 8, "資訊密度": 7.5, "導覽": 8.5, "狀態與回饋": 6.5, "響應式": 8.5, "文案": 8, "無障礙": 7, "動畫與轉場": 6.5}, "issues": ["[資訊層級/資訊密度] accupass-home：輪播橫幅與推薦帶佔據首屏與大半頁面，搜尋與分類不是焦點", "[間距與版面] bluesky-profile-feed desktop：中央欄窄，2560 寬螢幕兩側大量空白", "[狀態與回饋] 截圖幾乎都是有資料狀態，看不到載入、錯誤、空資料、登入前後的設計", "[無障礙] accupass-home 圖上壓字、luma/bluesky 的淡灰 metadata 對比偏低", "[間距與版面] accupass-search-harmonica desktop：結果稀少、留白大，缺少放寬搜尋或相關推薦的引導"]}, "C": {"scores": {"資訊層級": 8, "字體排印": 6.5, "色彩": 7.5, "間距與版面": 6.5, "一致性": 7.5, "資訊密度": 7, "導覽": 7.5, "狀態與回饋": 8, "響應式": 8, "文案": 7, "無障礙": 6, "動畫與轉場": 6}, "issues": ["[字體排印/無障礙] 全站 mobile 分頁列標籤與頁尾連結約 10.5 CSS px，小於建議最小字級（A 約 12 px）", "[間距與版面] sources-zh/source-detail-zh/scores-zh/about-zh desktop：內容區約 1220 CSS px，2560 寬螢幕兩側共約 1000 px 空白", "[文案] contribute-zh/contribute-signed-in-zh/status-zh：Apify、API 金鑰、「目前無可靠估計」×3、「尚無資料」大字、「未知（來源檢查尚未確認）」等技術語言外露", "[字體排印/一致性] desktop 次要字約 12–13 px 偏淡；中文混用半形冒號；home-zh 行事曆自成一套樣式；privacy-zh 側欄未對齊", "[資訊密度/色彩] source-detail-zh 限動大圖卡在 mobile 一屏不到 2 則；status-zh 的「已暫停」與「需要留意」難以區分"]}}
```
