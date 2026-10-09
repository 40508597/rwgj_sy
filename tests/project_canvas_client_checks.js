'use strict';

// Execute production inline JavaScript, not a rewritten client implementation.
// The DOM covers state/event contracts only. rAF never draws; 0ms timers are
// advanced explicitly to expose asynchronous expansion cancellation races.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const [contract, mainPath, emptyPath, regroupedPath, manifestPath] = process.argv.slice(2);
const fixturePaths = manifestPath ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {};
const HUGE_LITERAL = '9007199254740993123456789';
const plain = value => JSON.parse(JSON.stringify(value));

class FakeElement {
  constructor(tagName = 'div', id = '', owner = null) {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.ownerDocument = owner;
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = new Map();
    this.innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.hidden = false;
    this.scrollTop = 0;
    this.clientWidth = 1100;
    this.clientHeight = 700;
    this.files = [];
    this.classes = new Set();
    this.classList = {
      add: (...values) => values.forEach(value => this.classes.add(value)),
      remove: (...values) => values.forEach(value => this.classes.delete(value)),
      toggle: value => this.classes.has(value)
        ? (this.classes.delete(value), false) : (this.classes.add(value), true),
    };
  }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }
  dispatch(type, fields = {}) {
    const event = {
      target: this, currentTarget: this, key: '', shiftKey: false,
      ctrlKey: false, metaKey: false, altKey: false, button: 0, prevented: false,
      preventDefault() { this.prevented = true; }, ...fields,
    };
    for (const listener of this.listeners.get(type) || []) listener(event);
    return event;
  }
  closest(selector) {
    if (selector === 'button') return this.tagName === 'BUTTON' ? this : null;
    if (selector === '[data-nid]') return this.dataset.nid === undefined ? null : this;
    if (selector === '[data-target]') return this.dataset.target === undefined ? null : this;
    if (selector === '[data-pointer]') return this.dataset.pointer === undefined ? null : this;
    return null;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  querySelectorAll() { return []; }
  getBoundingClientRect() {
    return this.boundingRect || {left: 0, top: 0, width: this.clientWidth, height: this.clientHeight};
  }
  setPointerCapture() {}
  focus() { if (this.ownerDocument) this.ownerDocument.activeElement = this; }
  select() {}
  click() { if (this.onclick) return this.onclick({target: this}); }
}

function loadClient(path) {
  const html = fs.readFileSync(path, 'utf8');
  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)];
  const data = scripts.find(match => /\bid=["']project-data["']/.test(match[1]));
  assert.ok(data, 'render_project_view must embed project-data');
  const programs = scripts.filter(match => !/\btype=["']application\/json["']/.test(match[1]));
  assert.ok(programs.length, 'the fixture must contain the real inline client');

  const elements = new Map();
  const document = {
    title: '', activeElement: null,
    getElementById: id => elements.get(id) || null,
    querySelector: selector => selector === 'aside' ? aside
      : selector.startsWith('#') ? elements.get(selector.slice(1)) || null : null,
    querySelectorAll: () => [],
    createElement: tag => new FakeElement(tag, '', document),
  };
  document.body = new FakeElement('body', '', document);
  const aside = new FakeElement('aside', '', document);
  const markup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, '');
  for (const match of markup.matchAll(/<([\w:-]+)\b([^>]*\bid=["']([^"']+)["'][^>]*)>/g)) {
    const element = new FakeElement(match[1], match[3], document);
    element.checked = /(?:^|\s)checked(?:\s|>|$)/.test(match[2]);
    element.hidden = /(?:^|\s)hidden(?:\s|>|$)/.test(match[2]);
    elements.set(element.id, element);
  }
  const embedded = new FakeElement('script', 'project-data', document);
  embedded.textContent = data[2];
  elements.set(embedded.id, embedded);
  document.activeElement = elements.get('canvas');

  const timers = new Map(), frames = new Map(), storage = new Map();
  let serial = 0;
  const window = {addEventListener() {}};
  const context = vm.createContext({
    document, window, console,
    requestAnimationFrame: callback => {const id = ++serial; frames.set(id, callback); return id;},
    setTimeout: (callback, delay = 0) => {const id = ++serial; timers.set(id, {callback, delay}); return id;},
    clearTimeout: id => timers.delete(id),
    localStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
    navigator: {clipboard: {writeText: async () => {}}},
    Blob, URL,
  });
  vm.runInContext(programs.map(match => match[2]).join('\n'), context,
                  {filename: path, timeout: 10000});
  const api = vm.runInContext(`({
    data: D, nodes: N, printable, stableKey, snapshot, restoreState,
    search, resultPage, locate, ancestors, drawMap, sourceIdentity,
    state: () => ({selected, selectedInstance, viewRoot, scale, pan:{...pan},
      bounds:{...bounds}, searchPage, fullTask,
      taskGeneration, lastSearch, positions, expanded:[...expanded],
      longOpen:[...longOpen], relatedOpen:[...relatedOpen]}),
    expandedKeys: () => [...expanded].map(stableKey).sort(),
    current: () => positionMap.get(selectedInstance)
  })`, context);

  const element = id => {
    assert.ok(elements.has(id), 'production markup element missing: ' + id);
    return elements.get(id);
  };
  const button = id => new FakeElement('button', id, document);
  const node = (nid, iid) => {
    const target = new FakeElement('g', '', document);
    Object.assign(target.dataset, {nid: String(nid), iid});
    return target;
  };
  function pointer(pointer) {
    const nid = api.nodes.findIndex(n => n.p === pointer);
    assert.notEqual(nid, -1, 'fixture field not found: ' + pointer);
    return nid;
  }
  function query(value) {
    element('query').value = value;
    element('query').dispatch('input');
    return plain(api.state().lastSearch);
  }
  async function advanceOneYield() {
    const item = [...timers].find(([, timer]) => timer.delay === 0);
    if (!item) return false;
    timers.delete(item[0]);
    item[1].callback();
    await Promise.resolve();
    return true;
  }
  async function drainYields() {
    for (let limit = 0; limit < 30; limit++) {
      if (!await advanceOneYield()) return;
    }
    assert.fail('batch did not finish/cancel within the fixture timer budget');
  }
  return {api, element, button, node, pointer, query, advanceOneYield, drainYields, frames};
}

function assertSearchIncludes(client, text, nid) {
  assert.ok(client.query(text).some(result => result.nid === nid),
            'search must reach the original value ' + text);
}

function chooseResult(client, nid, match = -1) {
  const button = client.button('');
  Object.assign(button.dataset, {result: String(nid), match: String(match)});
  client.element('results').onclick({target: button});
}

function selectAndOpen(client, nid) {
  client.api.locate(nid, {history: false});
  client.element('toggle').onclick();
}

function relationAliases(client) {
  const {api} = client, {A, B, C} = api.data.entities;
  const state = plain(api.snapshot()), open = new Set(state.expanded);
  for (const id of [A, C]) {
    for (const ancestor of api.ancestors(id)) open.add(api.stableKey(ancestor));
  }
  state.expanded = [...open];
  state.relatedOpen = [api.stableKey(A), api.stableKey(C)];
  assert.equal(api.restoreState(state), true);
  const aliases = api.state().positions.filter(p => p.nid === B && p.alias);
  const underA = aliases.find(p => p.parent.nid === A);
  const underC = aliases.find(p => p.parent.nid === C);
  assert.ok(underA && underC, 'fixture needs references to the same module under A and C');
  return {A, B, C, underA, underC};
}

function scalarLiterals() {
  const client = loadClient(mainPath), {api} = client;
  const zero = client.pointer('/zero'), huge = client.pointer('/huge');
  assert.equal(api.printable(api.nodes[zero]), '0');
  assert.equal(api.nodes[huge].number_literal, HUGE_LITERAL);
  assert.equal(api.printable(api.nodes[huge]), HUGE_LITERAL,
               'display must use the exact Python literal, not rounded JSON.parse storage');
  assert.notEqual(String(api.nodes[huge].v), HUGE_LITERAL,
                  'fixture must expose an integer that IEEE-754 cannot preserve');
  assertSearchIncludes(client, '0', zero);
  assertSearchIncludes(client, HUGE_LITERAL, huge);
  const zeroEntity = api.data.entities['0'];
  assert.notEqual(zeroEntity, undefined, 'zero module identity must remain registered');
  api.locate(zeroEntity, {history: false});
  assert.equal(api.snapshot().selected, 'entity:0');
  assert.ok(client.frames.size > 0, 'drawing should be queued, not invoked by the fake DOM');
}

function containerContent() {
  const empty = loadClient(emptyPath), root = empty.api.nodes[0];
  assert.equal(root.empty, true);
  assert.ok(root.c.length > 0, 'the original empty object must have a synthetic reading child');
  assert.equal(root.raw_c.length, 0);
  assert.equal(empty.api.printable(root), '空对象 {}');
  assertSearchIncludes(empty, '{}', 0);

  const client = loadClient(regroupedPath);
  const arrayId = client.pointer('/模块拓扑/节点'), rawArray = client.api.nodes[arrayId];
  assert.equal(rawArray.empty, false);
  assert.equal(rawArray.raw_c.length, 2);
  assert.equal(rawArray.c.length, 0, 'canonical records should have moved into reading groups');
  assert.ok(!client.api.printable(rawArray).includes('空列表'),
            'a regrouped array with original members must not claim to be empty');
  assert.match(client.api.printable(rawArray), /2/);
  const originalEmptyArrayId = client.pointer('/模块详情');
  const originalEmptyArray = client.api.nodes[originalEmptyArrayId];
  assert.equal(originalEmptyArray.empty, true);
  assert.ok(originalEmptyArray.c.length > 0);
  assert.equal(client.api.printable(originalEmptyArray), '空列表 []');
  assertSearchIncludes(client, '[]', originalEmptyArrayId);
  assert.ok(!client.query('空列表').some(result => result.nid === arrayId));
}

function keyboard() {
  const client = loadClient(mainPath), {api} = client;
  const target = api.data.entities.A;
  api.locate(target, {history: false});
  assert.ok(api.state().scale > .4, 'Enter must test readable-scale toggle rather than LOD focus');
  assert.ok(!api.state().expanded.includes(target));
  const event = client.element('canvas').dispatch('keydown', {key: 'Enter'});
  assert.equal(event.prevented, true);
  assert.equal(api.state().selected, target);
  assert.ok(api.state().expanded.includes(target),
            'Enter with the canvas itself as target must expand the selected object');
  assert.ok(api.nodes[target].c.some(child => api.state().positions.some(p => p.nid === child)));
  client.element('canvas').dispatch('keydown', {key: 'Enter'});
  assert.ok(!api.state().expanded.includes(target));
  const zero = client.pointer('/zero');
  api.locate(zero, {history: false});
  client.element('canvas').dispatch('keydown', {key: ' '});
  assert.ok(api.state().longOpen.includes(zero), 'canvas Space must also activate a scalar');
}

function searchState() {
  const client = loadClient(mainPath), {api} = client;
  assert.equal(client.query('paging-needle').length, 37);
  client.element('results').onclick({target: client.button('search-next')});
  assert.equal(api.state().searchPage, 1);
  const expectedIds = plain(api.state().lastSearch.slice(15, 30).map(result => result.nid));
  for (const nid of expectedIds) {
    assert.ok(client.element('results').innerHTML.includes('data-result="' + nid + '"'));
  }
  client.element('results').hidden = true;
  client.element('show-results').hidden = false;
  const saved = plain(api.snapshot());
  client.query('no-matching-value');
  assert.equal(api.state().searchPage, 0);
  assert.equal(api.restoreState(saved), true);
  assert.equal(client.element('query').value, 'paging-needle');
  assert.equal(api.state().searchPage, 1, 'restoring a query must not reset its saved result page');
  assert.match(client.element('search-summary').textContent, /2\s*\/\s*3/);
  assert.equal(client.element('results').hidden, true);
  assert.equal(client.element('show-results').hidden, false);
  assert.deepEqual(plain(api.state().lastSearch.slice(15, 30).map(result => result.nid)), expectedIds);
  for (const nid of expectedIds) {
    assert.ok(client.element('results').innerHTML.includes('data-result="' + nid + '"'));
  }
}

function aliasInstance() {
  const client = loadClient(mainPath), {api} = client;
  const {A, B, C} = api.data.entities;
  const state = plain(api.snapshot());
  const open = new Set(state.expanded);
  for (const id of [A, C]) {
    for (const ancestor of api.ancestors(id)) open.add(api.stableKey(ancestor));
  }
  state.expanded = [...open];
  state.relatedOpen = [api.stableKey(A), api.stableKey(C)];
  assert.equal(api.restoreState(state), true);
  const aliases = api.state().positions.filter(p => p.nid === B && p.alias);
  const underA = aliases.find(p => p.parent.nid === A);
  const underC = aliases.find(p => p.parent.nid === C);
  assert.ok(underA && underC, 'fixture needs two references to the same canonical module');
  assert.notEqual(underA.iid, underC.iid);
  client.element('canvas').dispatch('click', {target: client.node(B, underC.iid)});
  const saved = plain(api.snapshot());
  assert.equal(saved.alias, true);
  assert.ok(saved.instancePath.some(([key]) => key === api.stableKey(C)));
  client.element('canvas').dispatch('click', {target: client.node(B, underA.iid)});
  assert.equal(api.current().parent.nid, A);
  assert.equal(api.restoreState(saved), true);
  assert.equal(api.state().selectedInstance, underC.iid,
               'restore must match instancePath rather than choose the first alias');
  assert.equal(api.current().parent.nid, C);
  assert.deepEqual(plain(api.snapshot().instancePath), saved.instancePath);
}

async function batchCancellation() {
  const client = loadClient(mainPath), {api} = client;
  assert.ok(api.nodes.length > 3000, 'the async contract needs multiple 1500-node chunks');
  const before = plain(api.expandedKeys());
  const generation = api.state().taskGeneration;
  const pending = client.element('all').onclick();
  assert.equal(api.state().fullTask, true);
  assert.equal(client.element('all').disabled, true);
  assert.deepEqual(plain(api.expandedKeys()), before,
                   'an unfinished batch must not mutate the committed expansion set');
  client.element('back').onclick();
  assert.ok(api.state().taskGeneration > generation);
  assert.equal(api.state().fullTask, false);
  assert.deepEqual(plain(api.expandedKeys()), before);
  api.locate(api.data.entities.A, {history: false});
  client.element('toggle').onclick();
  const afterManualEdit = plain(api.expandedKeys());
  assert.ok(afterManualEdit.includes(api.stableKey(api.data.entities.A)));
  await client.drainYields();
  await pending;
  assert.deepEqual(plain(api.expandedKeys()), afterManualEdit,
                   'the cancelled pending set must not overwrite later user expansion');
  assert.equal(client.element('all').disabled, false);

  // Resume a stale callback while a new batch is active. The older generation
  // must neither publish its pending set nor clear the newer task's busy state.
  const restarted = loadClient(mainPath), active = restarted.api;
  const oldRun = restarted.element('all').onclick();
  restarted.element('reset').onclick();
  const resetKeys = plain(active.expandedKeys());
  assert.deepEqual(resetKeys, [active.stableKey(0)]);
  const newRun = restarted.element('all').onclick();
  const newGeneration = active.state().taskGeneration;
  assert.equal(active.state().fullTask, true);
  assert.equal(await restarted.advanceOneYield(), true);
  await oldRun;
  assert.equal(active.state().taskGeneration, newGeneration);
  assert.equal(active.state().fullTask, true, 'stale completion must not clear the new busy task');
  assert.equal(restarted.element('all').disabled, true);
  assert.deepEqual(plain(active.expandedKeys()), resetKeys);
  restarted.element('reset').onclick();
  assert.ok(active.state().taskGeneration > newGeneration);
  await restarted.drainYields();
  await newRun;
  assert.deepEqual(plain(active.expandedKeys()), resetKeys,
                   'reset must survive later callbacks from both cancelled batches');
  assert.equal(active.state().fullTask, false);
  assert.equal(restarted.element('all').disabled, false);
}

function branchScope() {
  const client = loadClient(mainPath), {api} = client;
  const {A, C} = api.data.entities;
  selectAndOpen(client, A);
  selectAndOpen(client, C);
  const globalExpanded = plain(api.expandedKeys());
  client.element('scope').onclick();
  assert.equal(api.state().viewRoot, C);
  assert.equal(api.state().positions[0].nid, C);
  assert.ok(!api.state().positions.some(p => p.nid === A));
  assert.ok(api.state().positions.every(p => api.ancestors(p.nid).includes(C)));
  assert.deepEqual(plain(api.expandedKeys()), globalExpanded,
                   'scoping changes the view without discarding global expansion');
  assert.match(client.element('scope-name').textContent, /Module C/);
  client.element('overview').onclick();
  assert.equal(api.state().viewRoot, 0);
  assert.ok(api.state().positions.some(p => p.nid === A));
  assert.deepEqual(plain(api.expandedKeys()), globalExpanded);
  client.element('back').onclick();
  assert.equal(api.state().viewRoot, C);
  assert.equal(api.state().selected, C);
  assert.deepEqual(plain(api.expandedKeys()), globalExpanded);
}

function scopedSearchBack() {
  const client = loadClient(mainPath), {api} = client;
  selectAndOpen(client, api.data.entities.A);
  client.element('scope').onclick();
  const before = plain(api.snapshot());
  const target = client.pointer('/paging_records/18');
  const found = client.query('paging-needle-18').find(result => result.nid === target);
  assert.ok(found, 'global search must include fields outside the scoped branch');
  chooseResult(client, target, found.index);
  assert.equal(api.state().selected, target);
  assert.equal(api.state().viewRoot, target,
               'an outside search result becomes a visible local view');
  assert.equal(api.current().nid, target);
  assert.ok(api.state().longOpen.includes(target));
  assert.equal(client.element('results').hidden, true);
  client.element('back').onclick();
  assert.equal(api.state().viewRoot, api.data.entities.A);
  assert.equal(api.state().selected, api.data.entities.A);
  assert.deepEqual(plain(api.snapshot().expanded), before.expanded);
  assert.deepEqual(plain(api.snapshot().longOpen), before.longOpen);
  assert.deepEqual(plain(api.snapshot().instancePath), before.instancePath);
}

function scopedAliasSnapshot() {
  const client = loadClient(mainPath), {api} = client;
  const {B, C} = relationAliases(client);
  api.locate(C, {history: false});
  client.element('scope').onclick();
  const alias = api.state().positions.find(p => p.nid === B && p.alias);
  assert.ok(alias, 'the scoped C branch must still render its reference to B');
  client.element('canvas').dispatch('click', {target: client.node(B, alias.iid)});
  const saved = plain(api.snapshot());
  assert.equal(saved.alias, true);
  assert.equal(saved.viewRoot, api.stableKey(C));
  assert.equal(saved.instancePath[0][0], api.stableKey(C));
  assert.ok(client.element('breadcrumb').innerHTML.includes('data-iid="' + alias.iid + '"'),
            'the alias breadcrumb must point to this actual reference instance');
  client.element('overview').onclick();
  client.element('back').onclick();
  assert.equal(api.state().viewRoot, C);
  assert.equal(api.current().alias, true);
  assert.equal(api.current().parent.nid, C,
               'Back from overview must restore the scoped reference instance');
  client.element('overview').onclick();
  assert.equal(api.restoreState(saved), true);
  assert.equal(api.state().viewRoot, C,
               'a valid scoped alias must not fall back to the full project');
  assert.equal(api.current().alias, true);
  assert.equal(api.current().parent.nid, C);
  assert.deepEqual(plain(api.snapshot().instancePath), saved.instancePath);
  const aliasCrumb = client.button('');
  Object.assign(aliasCrumb.dataset, {nid: String(B), iid: api.current().iid});
  client.element('breadcrumb').onclick({target: aliasCrumb});
  assert.equal(api.state().viewRoot, C);
  assert.equal(api.current().alias, true,
               'clicking the current breadcrumb must retain the reference context');
  assert.equal(api.current().parent.nid, C);
}

function removedAliasFallback() {
  const original = loadClient(mainPath), {api} = original;
  const {B, underC} = relationAliases(original);
  original.element('canvas').dispatch('click', {target: original.node(B, underC.iid)});
  const saved = plain(api.snapshot());
  assert.equal(saved.alias, true);
  assert.equal(api.state().viewRoot, 0);
  const updated = loadClient(fixturePaths.main_without_c_relation);
  assert.equal(updated.api.restoreState(saved, true), true);
  assert.equal(updated.api.state().selected, updated.api.data.entities.B);
  assert.equal(updated.api.current().alias, false,
               'a removed C reference must not silently restore the surviving reference under A');
  assert.match(updated.element('notice').textContent, /引用位置已不存在.*原对象/);
}

function keyboardSelection() {
  const client = loadClient(mainPath), {api} = client;
  const A = api.data.entities.A;
  api.locate(A, {history: false});
  assert.ok(!api.state().expanded.includes(A));
  const right = client.element('canvas').dispatch('keydown', {key: 'ArrowRight', altKey: true});
  assert.equal(right.prevented, true);
  assert.ok(api.state().expanded.includes(A));
  assert.equal(api.current().parent.nid, A,
               'Alt Right expands the parent and selects its first visible child');
  const firstChild = api.state().selected;
  client.element('canvas').dispatch('keydown', {key: 'ArrowDown', altKey: true});
  assert.notEqual(api.state().selected, firstChild);
  client.element('canvas').dispatch('keydown', {key: 'ArrowUp', altKey: true});
  assert.equal(api.state().selected, firstChild);
  client.element('canvas').dispatch('keydown', {key: 'ArrowLeft', altKey: true});
  assert.equal(api.state().selected, A);
  client.element('scope').onclick();
  assert.equal(api.state().viewRoot, A);
  const expandedBeforeHome = plain(api.expandedKeys());
  const home = client.element('canvas').dispatch('keydown', {key: 'Home'});
  assert.equal(home.prevented, true);
  assert.equal(api.state().viewRoot, 0);
  assert.equal(api.state().selected, 0);
  assert.deepEqual(plain(api.expandedKeys()), expandedBeforeHome,
                   'Home returns to overview without collapsing existing branches');
  const panBefore = plain(api.state().pan);
  client.element('canvas').dispatch('keydown', {key: 'ArrowRight'});
  assert.equal(api.state().selected, 0, 'plain arrows pan instead of selecting a node');
  assert.equal(api.state().pan.x, panBefore.x - 72);
  assert.equal(api.state().pan.y, panBefore.y);
}

function minimapCssCoordinates() {
  const client = loadClient(mainPath), {api} = client;
  selectAndOpen(client, api.data.entities.A);
  api.drawMap();
  const map = client.element('map');
  assert.equal(map.getAttribute('viewBox'), '0 0 160 100');
  assert.equal(map.getAttribute('preserveAspectRatio'), 'none');
  const logical = {x: 113, y: 37};
  map.boundingRect = {left: 17, top: 23, width: 160, height: 100};
  map.onclick({clientX: 17 + logical.x, clientY: 23 + logical.y});
  const firstPan = plain(api.state().pan);
  map.boundingRect = {left: 71, top: 9, width: 125, height: 85};
  map.onclick({clientX: 71 + logical.x * 125 / 160,
               clientY: 9 + logical.y * 85 / 100});
  const secondPan = plain(api.state().pan);
  assert.ok(Math.abs(firstPan.x - secondPan.x) < 1e-8,
            'desktop and mobile minimap sizes must locate the same logical x');
  assert.ok(Math.abs(firstPan.y - secondPan.y) < 1e-8,
            'CSS aspect ratio changes must not shift the logical y');
  const beforeInvalid = plain(api.state().pan);
  map.boundingRect = {left: 0, top: 0, width: 0, height: 85};
  map.onclick({clientX: 0, clientY: 0});
  assert.deepEqual(plain(api.state().pan), beforeInvalid,
                   'an unmeasurable minimap must not publish NaN navigation');
}

function relationDirection() {
  const client = loadClient(mainPath), {api} = client;
  api.locate(api.data.entities.A, {history: false});
  const outgoing = client.element('related-list').innerHTML;
  assert.ok(outgoing.includes('Module A → Module B'));
  assert.ok(outgoing.includes('依赖：箭头指向被依赖方'));
  assert.ok(outgoing.includes('data-pointer="/模块详情/A/上游依赖/0"'),
            'the direction explanation must retain the actual declaration pointer');
  api.locate(api.data.entities.B, {history: false});
  const incoming = client.element('related-list').innerHTML;
  assert.ok(incoming.includes('Module A → Module B'));
  assert.ok(incoming.includes('Module C → Module B'));
  assert.ok(!incoming.includes('Module B → Module A'),
            'selecting the target must not reverse the underlying declaration');
  assert.ok(incoming.includes('依赖：箭头指向被依赖方'));
}

function stableArrayRestore() {
  const original = loadClient(fixturePaths.records_original);
  const target = original.pointer('/records/0/body/note');
  selectAndOpen(original, target);
  const saved = plain(original.api.snapshot());
  const updated = loadClient(fixturePaths.records_reordered);
  const moved = updated.pointer('/records/1/body/note');
  assert.notEqual(moved, target, 'the test must change the actual field node index');
  assert.equal(updated.api.stableKey(moved), saved.selected);
  assert.equal(updated.api.restoreState(saved, true), true);
  assert.equal(updated.api.state().selected, moved,
               'a unique explicit ID must restore its record after array reordering');
  assert.equal(updated.api.printable(updated.api.nodes[moved]), 'stable record A note');
  assert.ok(updated.api.state().longOpen.includes(moved));
  assert.ok(updated.api.ancestors(moved).slice(1).every(id => updated.api.state().expanded.includes(id)),
            'the moved record must be reachable through its restored reading ancestors');
  assert.equal(updated.api.nodes[moved].restore_safe, true);
  assert.ok(!Object.hasOwn(updated.api.data.entities, 'reading-A'),
            'reading IDs must not be promoted into business entities');
}

function unsafeChangedRestore() {
  const original = loadClient(fixturePaths.records_original);
  const target = original.pointer('/anonymous/0/body/note');
  selectAndOpen(original, target);
  assert.equal(original.api.nodes[target].restore_safe, false);
  const saved = plain(original.api.snapshot());
  const updated = loadClient(fixturePaths.records_changed);
  const positionalCollision = updated.pointer('/anonymous/0/body/note');
  assert.equal(updated.api.stableKey(positionalCollision), saved.selected,
               'the fixture must expose the dangerous same-index/different-record collision');
  assert.notEqual(updated.api.printable(updated.api.nodes[positionalCollision]),
                  original.api.printable(original.api.nodes[target]));
  assert.equal(updated.api.restoreState(saved, true), true);
  assert.equal(updated.api.state().selected, 0,
               'an updated anonymous record cannot inherit another record\'s selection');
  assert.ok(!updated.api.state().longOpen.includes(positionalCollision));
  assert.match(updated.element('notice').textContent, /跳过/);
}

function unsafeUnchangedRestore() {
  const original = loadClient(fixturePaths.records_original);
  const target = original.pointer('/anonymous/0/body/note');
  selectAndOpen(original, target);
  const saved = plain(original.api.snapshot());
  assert.equal(original.api.nodes[target].restore_safe, false);
  const key = original.api.stableKey(target);
  assert.equal(typeof saved.guards?.[key], 'string',
               'anonymous reading state must carry its original record guard');
  const updated = loadClient(fixturePaths.records_unrelated);
  const same = updated.pointer('/anonymous/0/body/note');
  assert.notEqual(updated.api.snapshot().contentFingerprint, saved.contentFingerprint,
                  'an independent architecture change must trigger update restoration');
  assert.equal(updated.api.nodes[same].restore_guard, saved.guards[key]);
  assert.equal(updated.api.restoreState(saved, true), true);
  assert.equal(updated.api.state().selected, same,
               'an unchanged anonymous record can resume despite unrelated source changes');
  assert.ok(updated.api.state().longOpen.includes(same));
  const legacy = {...saved};
  delete legacy.guards;
  assert.equal(updated.api.restoreState(legacy, true), true);
  assert.equal(updated.api.state().selected, 0,
               'old snapshots without a guard must safely skip unstable positions on update');
}

function physicalIdentityRestore() {
  const original = loadClient(fixturePaths.physical_original);
  const mapping = original.api.data.physical_mappings.find(m =>
    m.source.endsWith('/slices/a.json') && m.pointer === '/vendor/item/note');
  assert.ok(mapping, 'the fixture must include a supplemental physical-file field');
  const target = mapping.node;
  selectAndOpen(original, target);
  const saved = plain(original.api.snapshot());
  assert.match(saved.selected, /^physical:/);
  const migrated = loadClient(fixturePaths.physical_migrated);
  const newMapping = migrated.api.data.physical_mappings.find(m =>
    m.source.endsWith('/slices/a.json') && m.pointer === '/vendor/item/note');
  assert.ok(newMapping);
  assert.notEqual(newMapping.source_index, mapping.source_index,
                 'physical source order must actually differ between snapshots');
  assert.notEqual(newMapping.source, mapping.source);
  assert.equal(migrated.api.sourceIdentity(newMapping.source),
               original.api.sourceIdentity(mapping.source));
  assert.equal(migrated.api.stableKey(newMapping.node), saved.selected,
               'a copied project and reordered source list must keep relative field identity');
  assert.equal(migrated.api.restoreState(saved, true), true);
  assert.equal(migrated.api.state().selected, newMapping.node);
  assert.equal(migrated.api.printable(migrated.api.nodes[newMapping.node]), 'portable physical note');
  assert.ok(migrated.api.state().longOpen.includes(newMapping.node));
}

const contracts = {
  scalar_literals: scalarLiterals,
  container_content: containerContent,
  keyboard,
  search_state: searchState,
  alias_instance: aliasInstance,
  batch_cancellation: batchCancellation,
  branch_scope: branchScope,
  scoped_search_back: scopedSearchBack,
  scoped_alias_snapshot: scopedAliasSnapshot,
  removed_alias_fallback: removedAliasFallback,
  keyboard_selection: keyboardSelection,
  minimap_css_coordinates: minimapCssCoordinates,
  relation_direction: relationDirection,
  stable_array_restore: stableArrayRestore,
  unsafe_changed_restore: unsafeChangedRestore,
  unsafe_unchanged_restore: unsafeUnchangedRestore,
  physical_identity_restore: physicalIdentityRestore,
};

(async () => {
  assert.ok(contracts[contract], 'unknown client contract: ' + contract);
  await contracts[contract]();
  process.stdout.write('PASS ' + contract + '\n');
})().catch(error => {
  process.stderr.write((error.stack || String(error)) + '\n');
  process.exitCode = 1;
});
