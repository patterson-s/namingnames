'use strict';

// ── Tab navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('nav a').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const tab = link.dataset.tab;
    document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
    document.querySelectorAll('.tab-section').forEach(s => s.classList.remove('active'));
    link.classList.add('active');
    document.getElementById(`tab-${tab}`)?.classList.add('active');
  });
});

// ── State ─────────────────────────────────────────────────────────────────────

let allCountries = [];
let selectedIso  = null;
let currentSpanData = null;   // data-* for the hovered span

// ── Country list ──────────────────────────────────────────────────────────────

async function loadCountries() {
  const res = await fetch('/api/countries');
  allCountries = await res.json();
  renderCountryList(allCountries);
}

function renderCountryList(countries) {
  const ul = document.getElementById('country-list');
  ul.innerHTML = '';
  countries.forEach(c => {
    const li = document.createElement('li');
    li.dataset.iso = c.iso3;
    li.innerHTML = `
      <span class="iso-badge">${c.iso3}</span>
      <span class="country-name">${c.name}</span>
      <span class="count-chip">${c.n_speeches}</span>
    `;
    li.addEventListener('click', () => selectCountry(c.iso3, li));
    ul.appendChild(li);
  });
}

document.getElementById('country-search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  const filtered = allCountries.filter(c =>
    c.name.toLowerCase().includes(q) || c.iso3.toLowerCase().includes(q)
  );
  renderCountryList(filtered);
});

async function selectCountry(iso3, li) {
  try {
    selectedIso = iso3;
    document.querySelectorAll('#country-list li').forEach(el => el.classList.remove('selected'));
    li.classList.add('selected');

    clearSpeech();

    const yearPanel = document.getElementById('year-panel');
    const yearList  = document.getElementById('year-list');
    const yearLabel = document.getElementById('year-panel-label');

    yearPanel.classList.remove('hidden');
    yearLabel.textContent = iso3;
    yearList.innerHTML = '<li style="color:var(--gray-400);font-family:var(--font-mono);font-size:11px;padding:.5rem .75rem">Loading…</li>';

    const res = await fetch(`/api/countries/${iso3.trim()}/years`);
    if (!res.ok) {
      yearList.innerHTML = '<li style="color:var(--gray-400);font-family:var(--font-mono);font-size:11px;padding:.5rem .75rem">No speeches loaded yet</li>';
      return;
    }
    const years = await res.json();

    yearList.innerHTML = '';
    years.forEach(y => {
      const row = document.createElement('li');
      row.textContent = y.year;
      row.dataset.docId = y.doc_id;
      row.addEventListener('click', () => selectYear(y.doc_id, y.year, row));
      yearList.appendChild(row);
    });
  } catch (err) {
    console.error('selectCountry error:', err);
    document.getElementById('year-list').innerHTML =
      `<li style="color:#ef4444;font-size:11px;padding:.5rem .75rem">Error: ${err.message}</li>`;
  }
}

// ── Year / speech loading ──────────────────────────────────────────────────────

async function selectYear(docId, year, li) {
  document.querySelectorAll('#year-list li').forEach(el => el.classList.remove('selected'));
  li.classList.add('selected');

  const body = document.getElementById('speech-body');
  body.innerHTML = '<div class="loading-text">Loading speech…</div>';
  document.getElementById('speech-title').textContent = `${selectedIso} · ${year}`;
  clearInfoPanel();

  const res  = await fetch(`/api/speech/${docId}`);
  if (!res.ok) {
    body.innerHTML = '<div class="loading-text" style="color:#ef4444">Failed to load speech.</div>';
    return;
  }
  const data = await res.json();
  renderSpeech(data);
}

function clearSpeech() {
  document.getElementById('speech-title').textContent = 'Select a country and year';
  document.getElementById('speech-body').innerHTML =
    '<div class="empty-state"><div class="empty-icon">⟵</div><div>Select a year to load a speech</div></div>';
  clearInfoPanel();
}

// ── Speech rendering ───────────────────────────────────────────────────────────

/**
 * Render the speech text with entity spans and context words.
 *
 * Strategy:
 *  1. Build a sorted, non-overlapping list of span annotations.
 *  2. Walk the full text, emitting plain segments as word-wrapped spans
 *     (for context fade) and entity segments as colored entity spans.
 *  3. Each chunk region gets its words wrapped in .ctx-word spans keyed
 *     by chunk_start so hover can find them quickly.
 */
function renderSpeech(data) {
  const body = document.getElementById('speech-body');
  const text = data.text;

  if (!text) {
    body.innerHTML = '<div class="loading-text">No text available.</div>';
    return;
  }

  // Build chunk region map: chunk_start -> chunk_end (for context word marking)
  const chunkRegions = [];
  data.spans.forEach(sp => {
    if (sp.chunk_start != null && sp.chunk_end != null) {
      // Avoid duplicates
      if (!chunkRegions.find(r => r.start === sp.chunk_start)) {
        chunkRegions.push({ start: sp.chunk_start, end: Math.min(sp.chunk_end, text.length) });
      }
    }
  });
  chunkRegions.sort((a, b) => a.start - b.start);

  // Build sorted, non-overlapping span list
  const spans = [...data.spans].sort((a, b) => a.start - b.start);
  const clean = [];
  let cursor = 0;
  spans.forEach(sp => {
    if (sp.start < cursor) return;   // overlaps previous, skip
    if (sp.end > text.length) return;
    clean.push(sp);
    cursor = sp.end;
  });

  // Walk text and build HTML fragments
  const fragments = [];
  let pos = 0;

  function isInChunk(charPos) {
    return chunkRegions.find(r => charPos >= r.start && charPos < r.end) || null;
  }

  function emitPlainText(from, to) {
    if (from >= to) return;
    const segment = text.slice(from, to);
    // Split into words, wrapping words that fall in chunk regions with ctx-word spans
    let i = from;
    // Simple word-boundary split using regex on the segment
    const wordRegex = /(\S+)(\s*)/g;
    let match;
    let html = '';
    wordRegex.lastIndex = 0;
    while ((match = wordRegex.exec(segment)) !== null) {
      const wordStart = from + match.index;
      const word  = match[1];
      const space = match[2];
      const chunk = isInChunk(wordStart);
      if (chunk) {
        const wordIdx = computeWordIndex(text, chunk.start, wordStart);
        html += `<span class="ctx-word" data-chunk="${chunk.start}" data-widx="${wordIdx}">${escHtml(word)}</span>${escHtml(space)}`;
      } else {
        html += escHtml(word) + escHtml(space);
      }
    }
    fragments.push(html);
  }

  clean.forEach(sp => {
    emitPlainText(pos, sp.start);

    const cls    = spanClass(sp);
    const style  = spanStyle(sp);
    const entity = escHtml(text.slice(sp.start, sp.end));

    const dataAttrs = [
      `data-target="${sp.target}"`,
      `data-target-name="${escAttr(sp.target_name)}"`,
      `data-gpe="${escAttr(sp.gpe_entity)}"`,
      `data-cls="${sp.classification_clean ?? ''}"`,
      `data-prop="${sp.prop_antagonistic ?? ''}"`,
      `data-n-ment="${sp.n_chunks_mentioning ?? ''}"`,
      `data-n-ant="${sp.n_antagonistic ?? ''}"`,
      `data-reasoning="${escAttr(sp.reasoning ?? '')}"`,
      `data-chunk-start="${sp.chunk_start ?? ''}"`,
      `data-chunk-end="${sp.chunk_end ?? ''}"`,
      `data-estart="${sp.start}"`,
      `data-eend="${sp.end}"`,
    ].join(' ');

    fragments.push(`<span class="entity-span ${cls}" style="${style}" ${dataAttrs}>${entity}</span>`);
    pos = sp.end;
  });

  emitPlainText(pos, text.length);

  body.innerHTML = fragments.join('');
  attachHoverListeners();
}

function spanClass(sp) {
  if (sp.classification_clean === 1) return 'entity-span-antagonistic';
  if (sp.classification_clean === 0) return 'entity-span-neutral';
  return 'entity-span-unclassified';
}

function spanStyle(sp) {
  if (sp.classification_clean === 1) {
    const prop = sp.prop_antagonistic ?? 0.5;
    const alpha = (0.15 + prop * 0.40).toFixed(2);
    const textColor = prop >= 0.75 ? '#7f1d1d' : prop >= 0.4 ? '#991b1b' : '#b91c1c';
    return `background:rgba(220,38,38,${alpha});color:${textColor};`;
  }
  if (sp.classification_clean === 0) {
    return 'background:rgba(37,99,235,0.12);color:#1e40af;';
  }
  return 'background:rgba(156,163,175,0.18);color:#374151;';
}

/**
 * Compute word index within a chunk region (for context fade math).
 * Simple: count whitespace-separated tokens from chunk_start up to wordStart.
 */
function computeWordIndex(fullText, chunkStart, wordStart) {
  const before = fullText.slice(chunkStart, wordStart);
  return before.split(/\s+/).filter(Boolean).length;
}

// ── Hover: context fade ────────────────────────────────────────────────────────

const MAX_FADE_WORDS = 18;

function attachHoverListeners() {
  const body = document.getElementById('speech-body');

  body.addEventListener('mouseover', e => {
    const span = e.target.closest('.entity-span');
    if (!span) return;

    const chunkKey = span.dataset.chunkStart;
    if (!chunkKey) return;

    // Fade context words in this chunk
    const ctxWords = body.querySelectorAll(`.ctx-word[data-chunk="${chunkKey}"]`);
    const entityStart = parseInt(span.dataset.estart, 10);

    // Find the word index of the entity itself
    const bodyEl = body;
    const fullText = bodyEl.innerText;  // approximate; good enough for distance
    const entityWidxApprox = computeWordIndex(
      document.getElementById('speech-body').textContent,
      parseInt(chunkKey, 10),
      entityStart
    );

    ctxWords.forEach(w => {
      const widx = parseInt(w.dataset.widx, 10);
      const dist = Math.abs(widx - entityWidxApprox);
      const opacity = Math.max(0.06, 1 - dist / MAX_FADE_WORDS);
      w.style.opacity = opacity.toFixed(2);
    });

    updateInfoPanel(span);
  });

  body.addEventListener('mouseout', e => {
    const span = e.target.closest('.entity-span');
    if (!span) return;
    const chunkKey = span.dataset.chunkStart;
    if (chunkKey) {
      body.querySelectorAll(`.ctx-word[data-chunk="${chunkKey}"]`).forEach(w => {
        w.style.opacity = '';
      });
    }
    clearInfoPanel();
  });
}

// ── Info panel ─────────────────────────────────────────────────────────────────

function updateInfoPanel(span) {
  const d = span.dataset;
  const cls     = d.cls === '1' ? 'antagonistic' : d.cls === '0' ? 'neutral' : 'unclassified';
  const label   = cls === 'antagonistic' ? 'Antagonistic' : cls === 'neutral' ? 'Neutral' : 'Unclassified';
  const prop    = parseFloat(d.prop) || 0;
  const nMent   = d.nMent || '—';
  const nAnt    = d.nAnt  || '—';

  document.getElementById('info-placeholder').style.display = 'none';

  const content = document.getElementById('info-content');
  content.classList.remove('hidden');

  document.getElementById('info-iso').textContent         = d.target;
  document.getElementById('info-target-name').textContent = d.targetName || d.target;

  const badge = document.getElementById('info-badge');
  badge.textContent  = label;
  badge.className    = `info-badge ${cls}`;

  document.getElementById('info-stats').textContent =
    cls === 'unclassified'
      ? 'No classification available'
      : `${nAnt} of ${nMent} passages antagonistic · ${Math.round(prop * 100)}% intensity`;

  document.getElementById('info-entity').textContent = `"${d.gpe}"`;

  const reasoning = document.getElementById('info-reasoning');
  const raw = d.reasoning || '';
  reasoning.innerHTML = raw
    ? `<div class="info-reasoning-label">Reasoning</div>${escHtml(raw.slice(0, 500))}${raw.length > 500 ? '…' : ''}`
    : `<div class="info-reasoning-label">Reasoning</div><span style="color:var(--gray-400)">No reasoning available</span>`;
}

function clearInfoPanel() {
  document.getElementById('info-placeholder').style.display = '';
  document.getElementById('info-content').classList.add('hidden');
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  return String(str)
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadCountries();
