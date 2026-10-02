import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {setLocale} from '../assets/i18n.js';
import {accountPanel, contributeView, submitView, refreshCommunity, syncCommunityUi, handleGoogleAuth} from '../assets/community.js';

function browser(search='') {
  const {window}=new JSDOM('<main></main>', {url:'https://harmonica.observe.tw/contribute/'+search});
  for(const key of ['window','document','location','localStorage']) Object.defineProperty(globalThis,key,{configurable:true,value:key==='window'?window:window[key]});
  return window;
}
const anonymous={csrfToken:'csrf',identity:'browser',googleLoginEnabled:true,account:null,contributions:[],submissions:[]};

test('account UI localizes sign-in, escapes identity and preserves active form drafts', async()=>{
  const window=browser();
  const originalFetch=globalThis.fetch;
  let session={...anonymous};
  globalThis.fetch=async path=>({ok:true,json:async()=>path.endsWith('/session')?session:{}});
  try {
    await refreshCommunity();
    const labels={en:'Sign in with Google','zh-Hant':'使用 Google 帳號登入',ja:'Google でログイン',ko:'Google 계정으로 로그인'};
    for(const [locale,label] of Object.entries(labels)) {
      setLocale(locale);
      for(const view of [contributeView,()=>submitView({countries:[]})]) {
        document.querySelector('main').innerHTML=view();
        assert.equal(document.querySelector('[data-google-auth="login"]').textContent,label);
      }
    }
    setLocale('en');
    document.querySelector('main').innerHTML=contributeView();
    const input=document.querySelector('#contribution-name');input.value='Keep draft';input.focus();
    session={...anonymous,identity:'google',account:{name:'<img src=x onerror=alert(1)>',email:'"<b>@example.org'}};
    await refreshCommunity();syncCommunityUi();
    assert.equal(document.querySelector('#google-account img'),null);
    assert.equal(document.querySelector('#google-account b'),null);
    assert.ok(document.querySelector('[data-google-auth="logout"]'));
    assert.ok(!document.querySelector('[data-google-auth="login"]'));
    assert.equal(input.value,'Keep draft');assert.equal(document.activeElement,input);
  } finally {globalThis.fetch=originalFetch;window.close();}
});

test('logout uses CSRF, refreshes identity, and callback errors offer retry',async()=>{
  const window=browser('?auth_error=cancelled');setLocale('en');
  const originalFetch=globalThis.fetch;
  let loggedIn=true;const calls=[];
  globalThis.fetch=async(path,options={})=>{
    calls.push({path,options});
    if(path==='/auth/logout') loggedIn=false;
    return {ok:true,json:async()=>path.endsWith('/session')?{...anonymous,...(loggedIn?{identity:'google',account:{name:'Alice',email:'a@example.org'}}:{})}:{}};
  };
  try {
    await refreshCommunity();document.querySelector('main').innerHTML=accountPanel();
    assert.match(document.querySelector('#login-message').textContent,/cancelled/);
    const render=()=>document.querySelector('main').innerHTML=accountPanel();
    await handleGoogleAuth(document.querySelector('button'),render);
    const request=calls.find(c=>c.path==='/auth/logout');
    assert.equal(request.options.method,'POST');
    assert.equal(request.options.headers['X-CSRF-Token'],'csrf');
    assert.ok(document.querySelector('[data-google-auth="login"]'));
    window.history.replaceState(null,'','?auth_error=failed');render();
    assert.match(document.querySelector('#login-message').textContent,/try again/);
  } finally {globalThis.fetch=originalFetch;window.close();}
});

test('login request carries language and reports failures without losing draft',async()=>{
  const window=browser();setLocale('ja');
  const originalFetch=globalThis.fetch;let call;
  globalThis.fetch=async(path,options={})=>{
    if(path==='/auth/google/start'){call={path,options};return {ok:false,json:async()=>({code:'login_unavailable'})};}
    return {ok:true,json:async()=>path.endsWith('/session')?anonymous:{}};
  };
  try {
    await refreshCommunity();document.querySelector('main').innerHTML=contributeView();
    const button=document.querySelector('[data-google-auth="login"]');
    document.querySelector('#contribution-name').value='Draft';
    await handleGoogleAuth(button,()=>assert.fail('must not render on failure'));
    assert.equal(call.options.headers['X-CSRF-Token'],'csrf');
    assert.equal(JSON.parse(call.options.body).returnTo,'/contribute/?lang=ja');
    assert.equal(button.disabled,false);
    assert.equal(document.querySelector('#contribution-name').value,'Draft');
    assert.ok(document.querySelector('#login-message').textContent);
  } finally {globalThis.fetch=originalFetch;window.close();}
});
