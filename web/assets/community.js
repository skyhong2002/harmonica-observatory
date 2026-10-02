import { submissionContext, contextNote } from "./reporting.js";
import { t, getLocale, countryName } from "./i18n.js";
import {
  esc,
  link,
  icon,
  date,
  money,
  number,
  platformName,
  toast,
} from "./utils.js";
import { pageHeading } from "./views.js";
let session = null,
  community = null,
  lastImpact = null;
let formFeedback = null;
const pendingWithdrawals = new Set();
export const getCommunity = () => community;
export const getSession = () => session;
export async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.body
          ? {
              "Content-Type": "application/json",
              "X-CSRF-Token": session?.csrfToken || "",
            }
          : {}),
        ...options.headers,
      },
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error("request_failed");
    }
    if (!response.ok) {
      const error = new Error(payload.code || "request_failed");
      error.code = payload.code;
      throw error;
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}
export async function refreshCommunity() {
  const results = await Promise.allSettled([
    api("/api/v1/community"),
    api("/api/v1/session"),
  ]);
  community = results[0].status === "fulfilled" ? results[0].value : null;
  session = results[1].status === "fulfilled" ? results[1].value : null;
  return { community, session };
}
export function syncCommunityUi() {
  const account = document.querySelector('#google-account');
  if (account && !account.querySelector('[aria-busy="true"]')) account.outerHTML = accountPanel();
  const panel = document.querySelector(".capacity-panel");
  if (panel) panel.outerHTML = capacityPanel();
  const owned = document.querySelector("#owned-contributions");
  if (owned && !owned.contains(document.activeElement)) owned.innerHTML = contributionRows();
  const form = document.querySelector("#contribution-form, #submission-form");
  if (!form) return;
  const button = form.querySelector('button[type="submit"]');
  const message = form.querySelector("#form-message");
  // Refresh only data around an active form: never replace typed fields or tokens.
  if (button && !form.dataset.submitting) button.disabled = !session;
  if (message && message.textContent === t("sessionError") && session) message.textContent = "";
}
function errorMessage(error) {
  const codes = {
    https_required: "httpsRequired",
    invalid_token: "invalidToken",
    invalid_session: "sessionError",
    csrf: "sessionError",
    csrf_failed: "sessionError",
    invalid_csrf: "sessionError",
    invalid_origin: "sessionError",
    origin_forbidden: "sessionError",
    rate_limited: "rateLimited",
    daily_limit: "rateLimited",
    invalid_name: "invalidInput",
    invalid_budget: "invalidInput",
    consent_required: "invalidInput",
    invalid_url: "invalidInput",
    invalid_submission: "invalidInput",
    quota_exhausted: "noCapacity",
    already_registered: "alreadyRegistered",
    account_limit: "accountLimit",
    duplicate_submission: "duplicateSubmission",
    provider_unavailable: "providerUnavailable",
  };
  return t(codes[error.code] || "requestError");
}
export function scheduleView(schedule) {
  const platforms = schedule?.platforms || {};
  if (!Object.keys(platforms).length)
    return `<p class="muted">${t("estimateUnknown")}</p>`;
  return `<div class="schedule-list">${Object.entries(platforms)
    .map(
      ([name, p]) =>
        `<div><span>${esc(platformName(name))}<small>${t("results", { count: number(p.sourceCount) })}</small></span><strong>${Number.isFinite(p.estimatedDays) && p.estimatedDays > 0 ? t("estimateDays", { days: new Intl.NumberFormat(getLocale(), { maximumFractionDigits: 1 }).format(p.estimatedDays) }) : t(p.state === "insufficient_daily_budget" ? "noCapacity" : "estimateUnknown")}</strong></div>`,
    )
    .join("")}</div>`;
}
function impactView() {
  if (!lastImpact) return "";
  return `<section class="impact-panel"><h3>${t("impact")}</h3><div class="impact-grid"><div><h4>${t("before")}</h4>${scheduleView(lastImpact.before)}</div><div><h4>${t("after")}</h4>${scheduleView(lastImpact.after)}</div></div><p class="small muted">${t("estimateNote")}</p></section>`;
}
export function capacityPanel() {
  return `<section class="capacity-panel"><p class="eyebrow">${t("capacity")}</p><div class="capacity-figures"><div><strong>${community ? number(community.crawlSchedule?.pool?.usableAccountCount ?? community.activeAccounts) : "—"}</strong><span>${t("activeAccounts")}</span></div><div><strong>${money(community?.crawlSchedule?.pool ? community.crawlSchedule.pool.remainingUsd : community?.budgetRemainingUsd)}</strong><span>${t("remainingBudget")}</span></div></div><p class="small">${t("quotaNote")}</p><hr><h3>${t("estimatedCycle")}</h3>${scheduleView(community?.crawlSchedule)}<p class="small">${t("estimateNote")}</p></section>`;
}
function feedback(formId) {
  return formFeedback?.formId === formId ? t(formFeedback.key) : !session ? t("sessionError") : "";
}
export function accountPanel() {
  const error = new URLSearchParams(globalThis.location?.search || '').get('auth_error');
  const message = error ? t(error === 'cancelled' ? 'loginCancelled' : 'loginFailed') : '';
  const user = session?.account;
  return `<section id="google-account" class="form-panel account-panel" aria-label="${t('accountTitle')}">
    <div><h2>${t('accountTitle')}</h2>${user ? `<p>${esc(user.name)} <span class="muted">${esc(user.email)}</span></p><p class="small muted">${t('accountSynced')}</p>` : `<p>${t('loginHint')}</p>`}</div>
    ${user ? `<button type="button" class="button" data-google-auth="logout">${t('signOut')}</button>` : session?.googleLoginEnabled ? `<button type="button" class="button" data-google-auth="login">${t('googleSignIn')}</button>` : `<p class="small muted">${t(session ? 'loginUnavailable' : 'loading')}</p>`}
    <p id="login-message" class="form-message" role="status" aria-live="polite">${message}</p></section>`;
}
export async function handleGoogleAuth(button, rerender) {
  if (button.disabled) return;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  try {
    if (button.dataset.googleAuth === 'logout') {
      await api('/auth/logout', {method: 'POST', headers: {'X-CSRF-Token': session?.csrfToken || ''}});
      session = null;
      await refreshCommunity();
      rerender();
    } else {
      const query = new URLSearchParams(location.search);
      query.set('lang', getLocale());
      query.delete('auth_error');
      const result = await api('/auth/google/start', {method: 'POST', body: JSON.stringify({returnTo: location.pathname + '?' + query})});
      window.location.assign(result.url);
    }
  } catch {
    const message = document.querySelector('#login-message');
    if (message) message.textContent = t('loginFailed');
    else toast(t('loginFailed'));
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}
function contributionRows() {
  const rows = session?.contributions || [];
  return rows.length
    ? rows
        .map(
          (c) =>
            `<article class="owned-contribution" data-contribution-id="${esc(c.id)}"><div class="owned-heading"><h3>${esc(c.name)}</h3><span class="status-pill">${t(c.status === "revoked" ? "withdrawn" : ["active", "withdrawn", "exhausted", "invalid", "paused"].includes(c.status) ? c.status : "unavailable")}</span></div><dl><div><dt>${t("budget")}</dt><dd>${money(c.budgetUsd)}</dd></div><div><dt>${t("spent")}</dt><dd>${money(c.spentUsd)}</dd></div><div><dt>${t("reserved")}</dt><dd>${money(c.reservedUsd)}</dd></div><div><dt>${t("budgetRemaining")}</dt><dd>${money(c.budgetRemainingUsd)}</dd></div></dl>${!["revoked", "withdrawn"].includes(c.status) ? `<button class="button button-danger" data-withdraw="${esc(c.id)}">${t("withdraw")}</button>` : ""}</article>`,
        )
        .join("")
    : `<p class="muted">${t("noContributions")}</p>`;
}
export function contributeView() {
  return `${pageHeading("contribute", "contributeBody")}${accountPanel()}<div class="contribution-layout"><div><form id="contribution-form" class="form-panel"><h2>${t("newContribution")}</h2><label for="contribution-name">${t("contributionName")}</label><input id="contribution-name" name="name" required maxlength="40" placeholder="${t("namePlaceholder")}" autocomplete="nickname"><label for="contribution-token">${t("apiToken")}</label><input id="contribution-token" name="token" type="password" required minlength="20" maxlength="512" autocomplete="off" autocapitalize="none" spellcheck="false" aria-describedby="token-hint"><p id="token-hint" class="field-hint">${t("tokenHint")} ${link("https://console.apify.com/settings/integrations", t("tokenLink"), "text-link")}</p><label for="contribution-budget">${t("budget")}</label><div class="currency-input"><span>US$</span><input id="contribution-budget" name="budgetUsd" type="number" inputmode="decimal" min="0.01" max="100" step="0.01" required placeholder="1.00" aria-describedby="budget-hint"></div><p id="budget-hint" class="field-hint">${t("budgetHint")}</p><label class="consent-label"><input name="consent" type="checkbox" required><span>${t("consent")}</span></label><div id="form-message" class="form-message" role="status" aria-live="polite" tabindex="-1">${feedback("contribution-form")}</div><button class="button button-primary" type="submit" ${!session ? "disabled" : ""}>${t("contributionSubmit")}${icon("arrow")}</button><p class="field-hint">${link("/privacy/", t("privacy"), "text-link")}</p></form>${impactView()}<section class="ownership-section"><h2>${t("myContributions")}</h2><p class="small muted">${t("ownershipHint")}</p><div id="withdraw-message" class="form-message" role="status" aria-live="polite" tabindex="-1"></div><div id="owned-contributions">${contributionRows()}</div></section></div><aside>${capacityPanel()}<div class="sidebar-note"><h3>${t("faqWithdrawQ")}</h3><p>${t("faqWithdrawA")}</p>${link("/about/", t("faq"), "text-link")}</div></aside></div>`;
}
const allCountryCodes =
  "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split(
    " ",
  );
export function submitView(catalog) {
  const context = submissionContext();
  const codes = [
    ...new Set([
      ...allCountryCodes,
      ...catalog.countries
        .map((c) => c.code)
        .filter((c) => /^[A-Z]{2}$/.test(c)),
    ]),
  ].sort((a, b) => countryName(a).localeCompare(countryName(b), getLocale()));
  return `${pageHeading("submit", "submitBody")}${accountPanel()}<div class="contribution-layout"><div><form id="submission-form" class="form-panel"><h2>${t("submit")}</h2><label for="submission-url">${t("publicUrl")}</label><input id="submission-url" name="url" type="url" required maxlength="2000" placeholder="https://" autocomplete="url" value="${esc(context.url)}"><label for="submission-country">${t("country")}</label><select name="countryCode" id="submission-country"><option value="">${t("unknownCountry")}</option>${codes.map((code) => `<option value="${code}" ${code === context.countryCode ? "selected" : ""}>${esc(countryName(code))}</option>`).join("")}</select><label for="submission-note">${t("note")}</label><textarea id="submission-note" name="note" maxlength="2000" rows="5" placeholder="${t("notePlaceholder")}">${esc(contextNote(context.name))}</textarea><div id="form-message" class="form-message" role="status" aria-live="polite" tabindex="-1">${feedback("submission-form")}</div><button class="button button-primary" type="submit" ${!session ? "disabled" : ""}>${t("submitAction")}${icon("arrow")}</button></form><section class="ownership-section"><h2>${t("mySubmissions")}</h2>${(session?.submissions || []).length ? (session.submissions || []).map((s) => `<article class="submission-row"><div>${link(s.url, esc(s.url), "submission-url")}<p class="small muted">${date(s.createdAt)} · ${esc(countryName(s.countryCode))}</p>${s.note ? `<p>${esc(s.note)}</p>` : ""}</div><span class="tag">${t(s.status === "accepted" ? "approved" : s.status === "reviewing" ? "reviewing" : ["pending", "approved", "rejected"].includes(s.status) ? s.status : "pending")}</span></article>`).join("") : `<p class="muted">${t("noSubmissions")}</p>`}</section></div><aside class="submission-aside"><div class="sidebar-note">${icon("globe")}<h2>${t("countryNote")}</h2><p>${t("originalLanguage")}</p><hr><h3>${t("faqDataQ")}</h3><p>${t("faqDataA")}</p></div></aside></div>`;
}
export async function handleForm(form, rerender) {
  if (form.dataset.submitting) return;
  form.dataset.submitting = "true";
  form.setAttribute("aria-busy", "true");
  const languageSelect = document.querySelector("#language-select");
  if (languageSelect) languageSelect.disabled = true;
  formFeedback = null;
  form.querySelectorAll("[aria-invalid]").forEach(field => {
    field.removeAttribute("aria-invalid");
    const descriptions = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(id => id && id !== "form-message");
    if (descriptions.length) field.setAttribute("aria-describedby", descriptions.join(" "));
    else field.removeAttribute("aria-describedby");
  });
  const kind =
    form.id === "contribution-form" ? "contributions" : "submissions";
  const button = form.querySelector("button[type=submit]");
  const message = form.querySelector("#form-message");
  const fields = new FormData(form);
  const body =
    kind === "contributions"
      ? {
          name: String(fields.get("name") || "").trim(),
          token: String(fields.get("token") || "").trim(),
          budgetUsd: Number(fields.get("budgetUsd")),
          consent: fields.get("consent") === "on",
        }
      : {
          url: String(fields.get("url") || "").trim(),
          note: String(fields.get("note") || "").trim(),
          countryCode: String(fields.get("countryCode") || ""),
        };
  button.disabled = true;
  button.textContent = t("busy");
  message.textContent = "";
  message.classList.remove("is-error");
  try {
    const result = await api("/api/v1/" + kind, {
      method: "POST",
      body: JSON.stringify(body),
    });
    lastImpact = result.crawlImpact || null;
    form.reset();
    await refreshCommunity();
    formFeedback = { formId: form.id, key: kind === "contributions" ? "contributionSuccess" : "submitSuccess" };
    rerender();
    document.querySelector("#form-message")?.focus();
  } catch (error) {
    if (kind === "contributions") form.querySelector("[name=token]").value = "";
    message.textContent = errorMessage(error);
    message.classList.add("is-error");
    const fieldName = { invalid_token: "token", invalid_name: "name", invalid_budget: "budgetUsd", consent_required: "consent", invalid_url: "url" }[error.code];
    const field = fieldName ? form.elements.namedItem(fieldName) : null;
    if (field) {
      field.setAttribute("aria-invalid", "true");
      field.setAttribute("aria-describedby", [field.getAttribute("aria-describedby"), "form-message"].filter(Boolean).join(" "));
      field.focus();
    } else message.focus();
    button.disabled = false;
    button.textContent = t(
      kind === "contributions" ? "contributionSubmit" : "submitAction",
    );
  } finally {
    const languageSelect = document.querySelector("#language-select");
    if (languageSelect) languageSelect.disabled = false;
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    if ("token" in body) body.token = "";
  }
}
async function confirmWithdrawal(name) {
  const dialog = document.querySelector("#confirm-dialog");
  dialog.setAttribute("aria-labelledby", "withdraw-dialog-title");
  dialog.setAttribute("aria-describedby", "withdraw-dialog-description withdraw-dialog-effect");
  dialog.innerHTML = `<form method="dialog"><div class="dialog-icon">${icon("info")}</div><h2 id="withdraw-dialog-title">${t("confirmation")}: ${esc(name)}</h2><p id="withdraw-dialog-description">${t("withdrawConfirm")}</p><p id="withdraw-dialog-effect" class="small muted">${t("faqWithdrawA")}</p><div class="dialog-actions"><button class="button button-outline" value="cancel" autofocus>${t("cancel")}</button><button class="button button-danger" value="confirm">${t("withdraw")}</button></div></form>`;
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) =>
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "confirm"),
      { once: true },
    ),
  );
}
export async function withdraw(id, rerender) {
  if (pendingWithdrawals.has(id) || document.querySelector("#confirm-dialog")?.open) return;
  const contribution = session?.contributions?.find(row => row.id === id);
  pendingWithdrawals.add(id);
  const button = [...document.querySelectorAll("[data-withdraw]")].find(node => node.dataset.withdraw === id);
  try {
    if (!(await confirmWithdrawal(contribution?.name || t("myContributions")))) return;
    if (button) { button.disabled = true; button.textContent = t("busy"); }
    const result = await api("/api/v1/contributions/" + encodeURIComponent(id), {
      method: "DELETE", headers: { "X-CSRF-Token": session?.csrfToken || "" },
    });
    lastImpact = result.crawlImpact || null;
    await refreshCommunity();
    rerender();
    const message = document.querySelector("#withdraw-message");
    if (message) { message.textContent = t("withdrawSuccess"); message.focus(); }
    else toast(t("withdrawSuccess"));
  } catch (error) {
    const message = document.querySelector("#withdraw-message");
    if (message) { message.textContent = errorMessage(error); message.classList.add("is-error"); message.focus(); }
    else toast(errorMessage(error));
  } finally {
    pendingWithdrawals.delete(id);
    if (button?.isConnected) { button.disabled = false; button.textContent = t("withdraw"); }
  }
}
