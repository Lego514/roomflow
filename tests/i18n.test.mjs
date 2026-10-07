import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { validateExperiment } from '../src/experiment.mjs';
import { normalizeConfig } from '../src/simulator.mjs';

const dynamicSource = fs.readFileSync(new URL('../public/dynamic-i18n.js', import.meta.url), 'utf8');
const staticSource = fs.readFileSync(new URL('../public/i18n.js', import.meta.url), 'utf8');
const pageSource = fs.readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');

// Only the DOM surface consumed by the static translator is modeled here.
// Browser tests own rendering; this fixture uses the actual page's text,
// attributes, form values, and export links rather than copying its catalogue.
function domFixture(html) {
  class TextNode {
    constructor(text) { this.textContent = text; this.parentElement = null; }
    replaceWith(fragment) {
      const parent = this.parentElement;
      const replacement = fragment.fragment ? fragment.children : [fragment];
      const index = parent.children.indexOf(this);
      parent.children.splice(index, 1, ...replacement);
      for (const child of replacement) child.parentElement = parent;
    }
  }
  class Element {
    constructor(tag, attributes = {}) {
      this.tagName = tag.toUpperCase(); this.attributes = {}; this.dataset = {};
      this.children = []; this.parentElement = null; this.listeners = new Map();
      for (const [key, value] of Object.entries(attributes)) this.setAttribute(key, value);
    }
    getAttribute(key) {
      if (key.startsWith('data-')) return this.dataset[key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] ?? null;
      return this.attributes[key] ?? null;
    }
    setAttribute(key, value) {
      if (key.startsWith('data-')) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
      else this.attributes[key] = String(value);
    }
    append(...children) { for (const child of children) { this.children.push(child); child.parentElement = this; } }
    get textContent() { return this.children.map(child => child.textContent).join(''); }
    set textContent(value) { const text = new TextNode(String(value)); text.parentElement = this; this.children = [text]; }
    closest(selector) {
      for (let element = this; element; element = element.parentElement) {
        if (selector.split(',').some(part => matches(element, part))) return element;
      }
      return null;
    }
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    get value() {
      if (this.explicitValue !== undefined) return this.explicitValue;
      if (this.tagName === 'SELECT') {
        const options = this.children.filter(child => child.tagName === 'OPTION');
        return (options.find(option => option.getAttribute('selected') !== null) ?? options[0])?.getAttribute('value') ?? '';
      }
      return this.getAttribute('value') ?? '';
    }
    set value(value) { this.explicitValue = String(value); }
  }
  function matches(element, selector) {
    const attribute = selector.match(/^\[([^\]]+)\]$/);
    return attribute ? element.getAttribute(attribute[1]) !== null : element.tagName === selector.toUpperCase();
  }
  const root = new Element('document');
  const stack = [root];
  const voidTags = new Set(['META', 'LINK', 'INPUT', 'BR', 'HR', 'IMG']);
  for (const token of html.match(/<[^>]*>|[^<]+/g)) {
    if (token.startsWith('<!')) continue;
    if (token.startsWith('</')) { stack.pop(); continue; }
    if (token.startsWith('<')) {
      const name = token.match(/^<([\w-]+)/)?.[1];
      if (!name) continue;
      const attributes = {};
      const attributeSource = token.slice(name.length + 1).replace(/\/?\s*>$/, '');
      for (const match of attributeSource.matchAll(/([^\s=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s]+)))?/g)) {
        attributes[match[1]] = match[2] ?? match[3] ?? match[4] ?? '';
      }
      const element = new Element(name, attributes);
      stack.at(-1).append(element);
      if (!voidTags.has(element.tagName) && !token.endsWith('/>')) stack.push(element);
    } else stack.at(-1).append(new TextNode(token));
  }
  function elements(node = root) { return node.children.flatMap(child => child instanceof Element ? [child, ...elements(child)] : []); }
  function textNodes(node) { return node.children.flatMap(child => child instanceof TextNode ? [child] : textNodes(child)); }
  const all = elements();
  const events = [];
  const document = {
    body: all.find(element => element.tagName === 'BODY'), documentElement: all.find(element => element.tagName === 'HTML'),
    readyState: 'complete', title: '',
    createTreeWalker: (node) => { const texts = textNodes(node); let index = 0; return {nextNode: () => texts[index++] ?? null}; },
    createElement: tag => new Element(tag), createTextNode: text => new TextNode(text),
    createDocumentFragment: () => ({fragment:true, children:[], append(child) { this.children.push(child); }}),
    querySelectorAll: selector => elements().filter(element => selector.split(',').some(part => matches(element, part))),
    getElementById: id => elements().find(element => element.getAttribute('id') === id) ?? null,
    addEventListener: () => {}, dispatchEvent: event => { events.push(event); return true; },
  };
  return {document, events, elements, textNodes};
}

function runtime({stored = null, storageUnavailable = false, withStatic = true} = {}) {
  const dom = domFixture(pageSource);
  const saved = new Map(stored === null ? [] : [['roomflow-language', stored]]);
  const window = {};
  const context = vm.createContext({window, document:dom.document, NodeFilter:{SHOW_TEXT:4},
    CustomEvent:class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    localStorage:{
      getItem(key) { if (storageUnavailable) throw new Error('Storage blocked'); return saved.get(key) ?? null; },
      setItem(key, value) { if (storageUnavailable) throw new Error('Storage blocked'); saved.set(key, value); },
    },
  });
  vm.runInContext(dynamicSource, context, {filename:'dynamic-i18n.js'});
  if (withStatic) vm.runInContext(staticSource, context, {filename:'i18n.js'});
  return {window, saved, ...dom};
}

function thrownMessage(callback) { try { callback(); } catch (error) { return error.message; } throw new Error('Expected real validator to reject input'); }
const numberTokens = value => value.match(/\d+(?:\.\d+)?|—/g);

test('API validation and nested failures translate while preserving exact OS diagnostics', () => {
  const {window} = runtime({withStatic:false});
  const translate = window.RoomFlowDynamicLocalizeError;
  const parameterized = thrownMessage(() => validateExperiment({durationSeconds:0}));
  assert.match(translate(parameterized, 'zh-Hant'), /實驗總時間.*5 到 180.*整數/);
  assert.equal(translate(parameterized, 'en'), parameterized);
  const finite = thrownMessage(() => normalizeConfig({downMbps:NaN}));
  assert.match(translate(finite, 'zh-Hant'), /下行頻寬.*0\.5 到 100.*有限數值/);
  assert.equal(translate(finite, 'en'), finite);

  const detail = "ENOSPC: no space left on device, open 'C:\\測試\\session.json.tmp'\nerrno=-28; <raw diagnostic>";
  const source = `Strategy could not be applied: Strategy readback did not match the requested mode. Metadata could not be persisted: ${detail}`;
  const localized = translate(source, 'zh-Hant');
  assert.match(localized, /^無法套用策略：讀回的策略與要求的模式不一致。 無法保存實驗狀態：/);
  assert.ok(localized.endsWith(detail));
  assert.equal(translate(source, 'en'), source);
  assert.equal(translate(detail, 'zh-Hant'), detail);
  assert.match(translate('Apply failed and rollback requires attention: Strategy readback did not match the requested mode.', 'zh-Hant'), /套用失敗.*回復原策略.*讀回/);
});

test('kernel findings preserve measurements, missing-data markers, and unresolved caveats', () => {
  const {window} = runtime({withStatic:false});
  const translate = window.RoomFlowDynamicTranslate;
  const findings = Object.freeze([
    '雙向壅塞的 p95 RTT 平均：FIFO 290.33 ms、SQM — ms、會議優先 62.37 ms。',
    '會議優先相對 SQM 的 p95 平均增加 1.09 ms；請同時查看三次測量範圍，這不是統計顯著性或通話體感的結論。',
    '存在無有效 RTT 的實驗，無法比較會議優先與 SQM 的 p95 增益。',
    '這批測量後段出現持續的 RTT、丟包與吞吐量波動，包含沒有室友背景流量的情境；原始結果全部保留。資料已核對，但異常原因尚未確定，不能將這批平均值解讀成真實家庭網路的效能保證。',
    '另存的 11 次診斷補測仍出現延遲與丟包；目前沒有足夠證據證明會議分類比一般 SQM 有穩定額外收益。',
  ]);
  const evidence = Object.freeze({engine:'linux-kernel', findings, summary:Object.freeze([{rttP95MeanMs:null, meetingUpLossMeanPct:0}])});
  const exportBefore = JSON.stringify(evidence);
  const english = findings.map(value => translate(value, 'en'));
  for (let index = 0; index < 2; index++) assert.deepEqual(numberTokens(english[index]), numberTokens(findings[index]));
  assert.match(english[1], /increased.*1\.09.*does not establish statistical significance/);
  assert.match(english[2], /no valid RTT.*cannot be calculated/);
  assert.match(english[3], /cause remains unresolved.*not a performance guarantee/);
  assert.match(english[4], /11.*not enough evidence.*reliable additional benefit/);
  assert.equal(translate('—', 'en'), '—');
  assert.equal(translate('0.00', 'en'), '0.00');
  assert.deepEqual(findings.map(value => translate(value, 'zh-Hant')), [...findings]);
  assert.equal(JSON.stringify(evidence), exportBefore, 'display translation must not rewrite the evidence/export payload');
});

test('blocked storage keeps a Chinese default while language changes and events still work', () => {
  const r = runtime({storageUnavailable:true});
  assert.equal(r.window.RoomFlowI18n.language, 'zh-Hant');
  assert.equal(r.document.documentElement.lang, 'zh-Hant');
  r.window.RoomFlowI18n.setLanguage('en');
  assert.equal(r.document.documentElement.lang, 'en');
  assert.match(r.document.title, /Meeting Mode Lab/);
  assert.equal(r.events.at(-1).type, 'roomflow:languagechange');
  assert.equal(r.events.at(-1).detail.locale, 'en-US');
  r.window.RoomFlowI18n.setLanguage('unsupported');
  assert.equal(r.document.documentElement.lang, 'zh-Hant');
  assert.equal(r.events.at(-1).detail.locale, 'zh-TW');
});

test('stored language, selector changes, and restart persistence remain consistent', () => {
  const r = runtime({stored:'en'});
  assert.equal(r.window.RoomFlowI18n.language, 'en');
  const selector = r.document.getElementById('ui-language');
  assert.equal(selector.value, 'en');
  selector.listeners.get('change')({target:{value:'zh-Hant'}});
  assert.equal(r.saved.get('roomflow-language'), 'zh-Hant');
  assert.equal(r.document.documentElement.lang, 'zh-Hant');
  selector.listeners.get('change')({target:{value:'en'}});
  assert.equal(r.saved.get('roomflow-language'), 'en');
  assert.equal(runtime({stored:r.saved.get('roomflow-language')}).document.documentElement.lang, 'en');
});

test('actual static page keys resolve and switching preserves form and export identifiers', () => {
  const before = domFixture(pageSource);
  const identities = r => r.elements().filter(element => ['INPUT','SELECT','OPTION','A'].includes(element.tagName))
    .map(element => [element.tagName, ...['id','name','value','selected','checked','href'].map(attribute => element.getAttribute(attribute))]);
  const r = runtime();
  assert.deepEqual(identities(r), identities(before));
  r.window.RoomFlowI18n.setLanguage('en');
  const keys = r.document.querySelectorAll('[data-i18n]').map(element => element.dataset.i18n);
  assert.ok(keys.length > 100, 'the real page must be bound, not a small copied translation fixture');
  for (const key of keys) assert.notEqual(r.window.RoomFlowI18n.t(key), key, `Missing static key: ${key}`);
  const untranslated = r.textNodes(r.document.body).filter(node => /\p{Script=Han}/u.test(node.textContent) && node.textContent.trim() !== '繁體中文');
  assert.deepEqual(untranslated.map(node => node.textContent.trim()), [], 'all static Chinese copy needs an English display binding');
  for (const element of r.document.querySelectorAll('[aria-label],[title],[placeholder]')) {
    for (const attribute of ['aria-label','title','placeholder']) {
      const value = element.getAttribute(attribute);
      if (value !== null && value !== '中文 / English') assert.ok(!/\p{Script=Han}/u.test(value), `Untranslated ${attribute}: ${value}`);
    }
  }
  assert.deepEqual(identities(r), identities(before));
  r.window.RoomFlowI18n.setLanguage('zh-Hant');
  assert.deepEqual(identities(r), identities(before));
  assert.equal(r.window.RoomFlowI18n.translateText(null), null);
  assert.equal(r.window.RoomFlowI18n.translateText(0), 0);
});
