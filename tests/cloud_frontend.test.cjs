const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tag = tag; this.events = {}; this.children = []; }
  addEventListener(name, callback) { this.events[name] = callback; }
  setAttribute() {}
  append(...nodes) { this.children.push(...nodes); }
  showModal() { this.open = true; }
  close() { this.open = false; }
  remove() { this.removed = true; }
}
const calls = [], navigation = [], windowEvents = {}, documentEvents = {};
let authenticated = true, csrf = 'initial-test-csrf';
const elements = {'cloud-logout': new Element('button'), notification: new Element('div')};
const document = {
  body: new Element('body'),
  getElementById: (id) => elements[id],
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => ({text}),
  addEventListener: (name, callback) => { documentEvents[name] = callback; },
};
const origin = 'https://openstream-py.vercel.app';
const window = {
  location: {origin, href: origin + '/', replace: (url) => navigation.push(url), assign: (url) => navigation.push(url)},
  addEventListener: (name, callback) => { windowEvents[name] = callback; },
  fetch: async (input, options = {}) => {
    const url = new URL(input, origin);
    calls.push({url: url.href, options});
    if (url.pathname === '/auth/session') return new Response(JSON.stringify({authenticated, csrf}));
    if (url.pathname === '/auth/logout') { authenticated = false; return new Response('{}'); }
    return new Response('{}', {status: authenticated ? 200 : 401});
  },
};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, '../src/openstream/cloud/static/cloud.js'), 'utf8'), {window, document, URL, Request, Headers, Promise});
(async () => {
  await new Promise(setImmediate);
  await window.fetch('/api/runs', {method: 'POST', body: '{}'});
  assert.equal(calls.at(-1).options.headers.get('X-CSRF-Token'), csrf);
  assert.equal(calls.at(-1).options.credentials, 'same-origin');
  await window.fetch('https://example.com/check', {method: 'POST', body: '{}'});
  assert.equal(calls.at(-1).options.headers, undefined);
  authenticated = false;
  assert.equal((await window.fetch('/api/runs')).status, 401);
  const dialog = document.body.children.at(-1);
  assert.equal(dialog.tag, 'dialog'); assert.equal(dialog.open, true);
  const count = calls.length;
  let completed = false;
  const pending = window.fetch('/api/runs').then(() => { completed = true; });
  await new Promise(setImmediate);
  assert.equal(completed, false); assert.equal(calls.length, count);
  authenticated = true; csrf = 'rotated-test-csrf';
  await windowEvents.focus(); await pending;
  assert.equal(completed, true); assert.equal(dialog.removed, true);
  await window.fetch('/api/validate', {method: 'POST', body: '{}'});
  assert.equal(calls.at(-1).options.headers.get('X-CSRF-Token'), csrf);
  const href = origin + '/files/' + 'a'.repeat(32) + '/results.zip';
  let prevented = false;
  await documentEvents.click({target: {closest: () => ({href})}, preventDefault: () => { prevented = true; }});
  assert.equal(prevented, true); assert.equal(navigation.at(-1), href);
  await elements['cloud-logout'].events.click();
  assert.equal(navigation.at(-1), '/login');
})().catch((error) => { console.error(error); process.exitCode = 1; });
