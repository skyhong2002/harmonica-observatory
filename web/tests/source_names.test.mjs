import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<html><body></body></html>', {url:'http://localhost/'});
globalThis.document=dom.window.document;
globalThis.localStorage=dom.window.localStorage;
const {setLocale}=await import('../assets/i18n.js');
const {sourceNameRows,sourceNamesMarkup,sourceNameText,sourceTypesMarkup,sourceAlternativesMarkup,sourceSummaryText,sourceTags}=await import('../assets/source-names.js');
const {sourceCard,sourceDetail,sortSources,directoryHeader,pageHeading}=await import('../assets/views.js');
const source={id:'example',name:'原始名',nameEn:'Original Name',type:'學校社團',names:{original:'原始名','zh-Hant':'中文名',en:'English Name',ja:'日本語名',ko:'한국어 이름'},summary:'Original biography',links:[]};

test('directory defaults to the reading-language name and distinct recorded name without language badges',()=>{
 for(const locale of ['en','zh-Hant','ja','ko']){
  setLocale(locale);document.body.innerHTML=sourceCard(source,new Set(),{posts:[]});
  const names=document.querySelector('.src-name');
  assert.deepEqual([...names.querySelectorAll('.source-name-value')].map(node=>node.textContent),[source.names[locale],'原始名']);
  assert.equal(names.querySelector('.source-language-label'),null);
  assert.equal(document.querySelector('a details'),null);
  assert.equal(document.querySelector('.source-alternatives'),null);
  assert.equal(document.querySelector('.source-translation-note'),null);
 }
 const rows=sourceNameRows({...source,names:{original:'Same','zh-Hant':'Same',en:' SAME ',ja:'Same',ko:'Same'}},'ja');
 assert.equal(rows.length,1);assert.equal(rows[0].text,'Same');
 document.body.innerHTML=sourceNamesMarkup({...source,names:{original:'Same',en:'Same'} });
 assert.equal(document.querySelectorAll('.source-name-line').length,1);
});

test('additional names, original categories and translation provenance remain available inside native details',()=>{
 for(const [locale,summary,originalType] of [['zh-Hant','其他名稱與分類','原始類型'],['en','Other names and categories','Original type'],['ja','別の名称と分類','元の分類'],['ko','다른 이름과 분류','원래 유형']]){
  setLocale(locale);document.body.innerHTML=sourceAlternativesMarkup(source);
  const details=document.querySelector('details');assert.equal(details.open,false);
  assert.equal(details.querySelector('summary').textContent,summary);
  for(const name of Object.values(source.names)) assert.ok(details.textContent.includes(name));
  for(const label of ['社團','Club','クラブ','동아리','學校社團',originalType])assert.ok(details.textContent.includes(label));
  assert.ok(details.querySelector('.source-translation-note'));
 }
 document.body.innerHTML=directoryHeader();assert.equal(document.querySelector('.source-translation-note'),null);
});

test('names are safely escaped and hiding translations does not remove searchable names',()=>{
 setLocale('ja');const input={name:'<img src=x onerror=alert(1)>',nameEn:'Name & Co'};
 document.body.innerHTML=sourceNamesMarkup(input)+sourceAlternativesMarkup(input);
 assert.equal(document.querySelector('img'),null);
 assert.match(document.body.textContent,/<img src=x onerror=alert\(1\)>/);
 assert.equal(sourceNameRows(input)[0].text,input.name);
 for(const name of Object.values(source.names))assert.ok(sourceNameText(source).includes(name));
});

test('the visible category uses only the current language',()=>{
 for(const [locale,current] of [['en','Club'],['zh-Hant','社團'],['ja','クラブ'],['ko','동아리']]){
  setLocale(locale);document.body.innerHTML=sourceTypesMarkup(source);
  assert.equal(document.body.textContent,current);assert.equal(document.querySelector('.source-language-label'),null);
 }
 document.body.innerHTML=sourceTypesMarkup({...source,type:'Unknown original category'});
 assert.equal(document.body.textContent,'Unknown original category');
});

test('profile shows the current and original names, preserves biography and sorts by the visible name',()=>{
 setLocale('ja');document.body.innerHTML=sourceDetail(source,{sources:[source],posts:[]},new Set());
 assert.equal(document.querySelector('h1').textContent,'日本語名');
 assert.equal(document.querySelector('.source-profile > div > .source-names').textContent,'原始名');
 assert.ok(document.querySelector('.source-profile').textContent.includes('Original biography'));
 assert.match(document.querySelector('details .source-translation-note').textContent,/参考訳/);
 const rows=[{...source,id:'z',names:{original:'A',ja:'Z'}},{...source,id:'a',names:{original:'Z',ja:'A'}}];
 assert.deepEqual(sortSources(rows).map(row=>row.id),['a','z']);
});

test('a heading without descriptive copy does not render an empty paragraph',()=>{
 setLocale('en');document.body.innerHTML=pageHeading('posts',null);
 assert.equal(document.querySelector('h1').textContent,'Updates');assert.equal(document.querySelector('p'),null);
 document.body.innerHTML=pageHeading('sources','directoryBody');assert.ok(document.querySelector('p').textContent);
});


test('profile biographies and tags follow the selected language while the original remains collapsed',()=>{
 const translated={...source,summary:'原始說明\n保留換行',summaryLanguage:'zh-Hant',summaries:{'zh-Hant':'原始說明\n保留換行',en:'English biography',ja:'日本語の紹介',ko:'한국어 소개'},tags:['半音階','原始標籤'],tagsLocalized:{en:['Chromatic'],ja:['クロマチック'],ko:['크로매틱']}};
 for(const [locale,label] of [['en','View original'],['ja','原文を見る'],['ko','원문 보기'],['zh-Hant','查看原文']]){
  setLocale(locale);document.body.innerHTML=sourceDetail(translated,{sources:[translated],posts:[]},new Set());
  const biography=document.querySelector('.source-summary');
  assert.equal(biography.textContent,translated.summaries[locale]);
  assert.equal(biography.lang,locale);
  assert.equal(sourceSummaryText(translated),translated.summaries[locale]);
  const details=document.querySelector('.source-summary-original');
  if(locale==='zh-Hant') assert.equal(details,null);
  else {
   assert.equal(details.open,false);assert.equal(details.querySelector('summary').textContent,label);
   assert.equal(details.querySelector('p').textContent,translated.summary);assert.equal(details.querySelector('p').lang,'zh-Hant');
   details.open=true;assert.equal(details.open,true);
  }
  assert.deepEqual([...document.querySelectorAll('.profile-tags .tag')].map(el=>el.textContent),[translated.tagsLocalized[locale]?.[0] || '半音階','原始標籤']);
 }
});

test('missing and blank biography translations fall back to the original without a redundant disclosure',()=>{
 setLocale('en');
 for(const summaries of [undefined,{}, {en:''},{en:'  '},{en:43},{ja:'日本語'}]){
  const input={...source,summary:'  Exact original\ntext  ',summaries};
  assert.equal(sourceSummaryText(input),input.summary);
  document.body.innerHTML=sourceDetail(input,{sources:[input],posts:[]},new Set());
  assert.equal(document.querySelector('.source-summary').textContent,input.summary);
  assert.equal(document.querySelector('.source-summary-original'),null);
 }
 assert.equal(sourceSummaryText({}),'');
 assert.deepEqual(sourceTags({tags:['a','b'],tagsLocalized:{en:['',null]}}),['a','b']);
 assert.deepEqual(sourceTags({tags:'invalid',tagsLocalized:{en:['a']}}),[]);
});

test('translated biographies, original biographies and tags render as literal text',()=>{
 setLocale('en');
 const input={...source,summary:'<img src=x onerror=alert(1)>\nOriginal & text',summaries:{en:'<script>alert(2)</script> & translation'},summaryLanguage:'zh-Hant',tags:['原文'],tagsLocalized:{en:['<svg onload=alert(3)>']}};
 document.body.innerHTML=sourceDetail(input,{sources:[input],posts:[]},new Set());
 assert.equal(document.querySelector('.source-summary').textContent,input.summaries.en);
 assert.equal(document.querySelector('.source-summary-original p').textContent,input.summary);
 assert.equal(document.querySelector('.profile-tags .tag').textContent,input.tagsLocalized.en[0]);
 assert.equal(document.querySelector('.source-biography script, .source-biography img, .profile-tags svg'),null);
});
