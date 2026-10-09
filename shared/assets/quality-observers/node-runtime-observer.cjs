#!/usr/bin/env node
'use strict';
// Optional, dependency-only CommonJS observation example. No static parser.
// node THIS_FILE PROJECT CONFIG_REL FACTS_REL RAW_REL
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const VERSION = '1.0.0';
const METHOD = 'node-require-cache-module-children-after-selected-runner';

// JSON.parse alone silently accepts duplicate keys. Reject them at every depth.
function strictJSON(text) {
  let pos = 0;
  const ws = () => { while (/\s/.test(text[pos] || '') && pos < text.length) pos++; };
  const bad = message => { throw new Error(`${message} at JSON offset ${pos}`); };
  function string() {
    const start = pos++;
    while (pos < text.length) {
      if (text[pos] === '\\') { pos += 2; continue; }
      if (text[pos++] === '"') return JSON.parse(text.slice(start, pos));
    }
    bad('unterminated string');
  }
  function value() {
    ws();
    if (text[pos] === '"') return string();
    if (text[pos] === '{') {
      pos++; ws(); const result = Object.create(null);
      if (text[pos] === '}') { pos++; return result; }
      while (true) {
        ws(); if (text[pos] !== '"') bad('expected object key');
        const key = string(); ws();
        if (Object.hasOwn(result, key)) bad(`duplicate JSON key: ${key}`);
        if (text[pos++] !== ':') bad('expected colon');
        result[key] = value(); ws(); const next = text[pos++];
        if (next === '}') return result;
        if (next !== ',') bad('expected object separator');
      }
    }
    if (text[pos] === '[') {
      pos++; ws(); const result = [];
      if (text[pos] === ']') { pos++; return result; }
      while (true) {
        result.push(value()); ws(); const next = text[pos++];
        if (next === ']') return result;
        if (next !== ',') bad('expected array separator');
      }
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(pos));
    if (!token) bad('invalid JSON value');
    pos += token[0].length;
    const result = JSON.parse(token[0]);
    if (typeof result === 'number' && !Number.isFinite(result)) bad('non-finite number');
    return result;
  }
  const result = value(); ws();
  if (pos !== text.length) bad('trailing JSON input');
  return result;
}

function fields(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`);
  for (const key of Object.keys(value)) if (!keys.includes(key)) throw new Error(`${label}: unsupported field ${key}`);
}
function nonempty(value, label) {
  if (typeof value !== 'string' || !value.trim() || value.includes('\0')) throw new Error(`${label} must be a nonempty string`);
  return value;
}
const identity = value => process.platform === 'win32' ? value.toLowerCase() : value;
function inside(root, file) {
  const rel = path.relative(root, file);
  if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) throw new Error(`path escapes project: ${file}`);
  return file;
}
function relative(root, raw, mustExist = true) {
  nonempty(raw, 'path');
  if (path.isAbsolute(raw) || raw.includes(':') || raw.includes('\\') || /[\x00-\x1f]/.test(raw) ||
      raw.split('/').some(x => !x || x === '.' || x === '..' || x.endsWith('.') || x.endsWith(' '))) {
    throw new Error(`expected normalized project-relative path: ${raw}`);
  }
  let file = inside(root, path.resolve(root, raw));
  if (mustExist) {
    file = inside(root, fs.realpathSync(file));
    if (!fs.statSync(file).isFile()) throw new Error(`input is not a regular file: ${raw}`);
  } else {
    // Check existing ancestors too: an output directory may be a symlink.
    let parent = path.dirname(file);
    while (!fs.existsSync(parent)) parent = path.dirname(parent);
    inside(root, fs.realpathSync(parent));
    if (fs.existsSync(file)) {
      file = inside(root, fs.realpathSync(file));
      const stat = fs.statSync(file);
      if (!stat.isFile()) throw new Error(`output is not a regular file: ${raw}`);
      // realpath cannot identify distinct names for one inode. Refuse every
      // shared-inode output before any write, even links outside this scope.
      if (stat.nlink > 1) throw new Error(`existing output has multiple hard links: ${raw}`);
    }
  }
  return file;
}
function load(root, configRel) {
  const configFile = relative(root, configRel);
  const config = strictJSON(fs.readFileSync(configFile, 'utf8'));
  fields(config, ['schema_version', 'source_id', 'modules', 'runner', 'inputs', 'timeout_ms'], 'config');
  if (config.schema_version !== 1) throw new Error('unsupported config.schema_version');
  nonempty(config.source_id, 'source_id');
  if (!Array.isArray(config.modules) || !config.modules.length) throw new Error('modules must be nonempty');
  const ids = new Set(); const files = new Set();
  const modules = config.modules.map(item => {
    fields(item, ['id', 'file'], 'module'); nonempty(item.id, 'module.id');
    const file = relative(root, item.file);
    if (ids.has(item.id) || files.has(identity(file))) throw new Error('duplicate module ID/file');
    ids.add(item.id); files.add(identity(file));
    return { id: item.id, file, relative: item.file };
  });
  const runner = relative(root, config.runner);
  if (files.has(identity(runner))) throw new Error('runner must be separate from observed modules');
  if (!Array.isArray(config.inputs) || !config.inputs.length) throw new Error('inputs must be nonempty');
  const inputs = new Map(); const inputFiles = new Set();
  for (const raw of config.inputs) {
    const file = relative(root, raw);
    if (inputFiles.has(identity(file))) throw new Error(`duplicate input: ${raw}`);
    inputFiles.add(identity(file)); inputs.set(raw, file);
  }
  for (const file of [...modules.map(item => item.file), runner]) {
    if (!inputFiles.has(identity(file))) throw new Error(`required module/runner omitted from inputs: ${file}`);
  }
  if (inputFiles.has(identity(configFile))) throw new Error('config is bound automatically; do not repeat it in inputs');
  inputs.set(configRel, configFile);
  const timeout = config.timeout_ms === undefined ? 10000 : config.timeout_ms;
  if (!Number.isInteger(timeout) || timeout < 1 || timeout > 300000) throw new Error('timeout_ms must be an integer in [1,300000]');
  return { config, configFile, modules, runner, inputs, timeout };
}
function hashes(inputs) {
  return Object.fromEntries([...inputs].sort(([a], [b]) => a.localeCompare(b)).map(([rel, file]) =>
    [rel, crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]));
}
function write(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

function outputs(root, factsRel, rawRel, inputs) {
  const factsFile = relative(root, factsRel, false); const rawFile = relative(root, rawRel, false);
  if (identity(factsFile) === identity(rawFile)) throw new Error('facts/raw outputs must differ');
  for (const file of inputs.values()) {
    if ([factsFile, rawFile].some(out => identity(out) === identity(file))) throw new Error('outputs must not overwrite selected inputs');
  }
  return { factsFile, rawFile };
}

async function worker(root, configRel, output) {
  const selected = load(root, configRel);
  const before = new Set(Object.keys(require.cache));
  let scenarioError = null;
  try {
    const run = require(selected.runner);
    if (typeof run !== 'function') throw new Error('runner must export one scenario function');
    await run();
  } catch (error) {
    scenarioError = String(error && error.stack || error);
    console.error(scenarioError);
  }
  const idByFile = new Map(selected.modules.map(item => [identity(item.file), item.id]));
  const observed = []; const edges = []; const unlisted = [];
  for (const file of Object.keys(require.cache).filter(file => !before.has(file)).sort()) {
    const entry = require.cache[file];
    const id = idByFile.get(identity(file));
    observed.push({ file, module: id || null, children: entry.children.map(child => child.filename).sort() });
    if (!id && identity(file) !== identity(selected.runner)) unlisted.push(file);
    if (id) for (const child of entry.children) {
      const childID = idByFile.get(identity(child.filename));
      if (childID) edges.push({ from: id, to: childID });
    }
  }
  const loaded = observed.filter(item => item.module !== null).map(item => item.module).sort();
  write(output, { method: METHOD, loaded, observed, edges, unlisted, scenario_error: scenarioError });
  if (scenarioError) process.exitCode = 1;
}

function collect(root, configRel, factsRel, rawRel) {
  const selected = load(root, configRel);
  let outputFiles = outputs(root, factsRel, rawRel, selected.inputs);
  const inputHashes = hashes(selected.inputs);
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'taskarch-node-observer-'));
  const snapshotFile = path.join(temporary, 'snapshot.json');
  const command = [process.execPath, __filename, '--worker', root, configRel, snapshotFile];
  let execution; let snapshot = null; const errors = [];
  try {
    execution = spawnSync(command[0], command.slice(1), {
      cwd: root, shell: false, input: '', timeout: selected.timeout, maxBuffer: 16 * 1024 * 1024,
      env: { ...process.env, NODE_OPTIONS: '', NODE_PATH: '' }, encoding: 'utf8', windowsHide: true,
    });
    if (fs.existsSync(snapshotFile)) snapshot = strictJSON(fs.readFileSync(snapshotFile, 'utf8'));
  } finally {
    if (fs.existsSync(snapshotFile)) fs.unlinkSync(snapshotFile);
    fs.rmdirSync(temporary);
  }
  if (execution.error) errors.push(`worker error: ${execution.error.message}`);
  if (execution.status !== 0) errors.push(`selected scenario did not succeed: exit=${execution.status}; signal=${execution.signal}`);
  if (!snapshot) errors.push('worker produced no completed cache observation');
  if (snapshot && snapshot.scenario_error) errors.push(`scenario error: ${snapshot.scenario_error}`);
  if (snapshot) {
    for (const item of selected.modules) if (!snapshot.loaded.includes(item.id)) errors.push(`module not loaded by selected scenario: ${item.id}`);
    for (const file of snapshot.unlisted) errors.push(`unlisted cache module loaded by selected scenario: ${file}`);
  }
  let after = {};
  try { after = hashes(selected.inputs); } catch (error) { errors.push(`input snapshot failed: ${error.message}`); }
  if (JSON.stringify(inputHashes) !== JSON.stringify(after)) errors.push('selected inputs changed during scenario execution');
  // The selected runner may create/replace files. Revalidate both outputs
  // together after it finishes, before either old report is overwritten.
  outputFiles = outputs(root, factsRel, rawRel, selected.inputs);
  const complete = errors.length === 0;
  const raw = {
    schema_version: 1, observer: { name: 'node-runtime-observer', version: VERSION, node: process.version },
    method: METHOD, command, cwd: root, timeout_ms: selected.timeout, input_hashes: inputHashes,
    input_hashes_after: after, returncode: execution.status, signal: execution.signal,
    stdin: '', stdout: execution.stdout || '', stderr: execution.stderr || '',
    complete, errors, excluded: [], snapshot,
    boundaries: [
      'One explicitly selected scenario; only CommonJS require.cache/module.children after it finishes.',
      'Not a complete static import/call graph; unexecuted branches, ESM imports and built-in modules are not represented.',
      'No interface, complexity, coverage or CRAP measurements are produced.',
      'The runner is a test entrypoint outside the selected business-module graph; this is not an OS sandbox.',
    ],
  };
  const source = {
    id: selected.config.source_id, origin: 'observed',
    tool: { name: 'node-runtime-observer', version: `${VERSION}; Node ${process.version}`,
      adapter_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex') },
    capabilities: ['dependencies:runtime-load'], scope: snapshot ? snapshot.loaded : [],
    complete, errors, excluded: [], input_hashes: inputHashes,
    method: METHOD, raw_report: rawRel, scenario: selected.config.runner,
  };
  const seen = new Set();
  const dependencies = (snapshot ? snapshot.edges : []).filter(edge => {
    const key = JSON.stringify(edge); if (seen.has(key)) return false; seen.add(key); return true;
  }).map(edge => ({ ...edge, kind: 'runtime-load', source: source.id, location: { raw_report: rawRel } }));
  const facts = { schema_version: 1, modules: selected.modules.map(item => item.id), sources: [source],
    dependencies, metrics: [], decisions: [] };
  write(outputFiles.rawFile, raw); write(outputFiles.factsFile, facts);
  console.log(JSON.stringify({ status: complete ? 'pass' : 'unknown', code: complete ? 0 : 2,
    facts: factsRel, raw: rawRel, method: METHOD, errors }));
  return complete ? 0 : 2;
}

(async () => {
  try {
    const args = process.argv.slice(2);
    if (args[0] === '--worker' && args.length === 4) {
      await worker(fs.realpathSync(args[1]), args[2], args[3]);
    } else if (args.length === 4) {
      process.exitCode = collect(fs.realpathSync(args[0]), args[1], args[2], args[3]);
    } else throw new Error('usage: node node-runtime-observer.cjs PROJECT CONFIG_REL FACTS_REL RAW_REL');
  } catch (error) {
    console.log(JSON.stringify({ status: 'unknown', code: 2, errors: [String(error && error.message || error)] }));
    process.exitCode = 2;
  }
})();
