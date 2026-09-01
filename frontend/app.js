/**
 * Facebook Zenith Cleaner - client controller (v2.0)
 *
 * Fixes vs v1:
 *  - the status poller no longer re-renders the whole grid every 2s (it used to
 *    wipe your scroll position and fight in-flight checkbox clicks)
 *  - selection changes use one bulk request instead of up to 300 parallel POSTs
 *  - the markdown checklist is built locally, so it is never stale
 *  - one delegated listener instead of re-binding a listener per card
 *  - purge is driven off ids resolved server-side; errors surface in the UI
 */

'use strict';

const state = {
  friends: [],
  groups: [],
  pages: [],
  activeTab: 'friends',
  searchQuery: '',
  pageSize: 300,
  currentPage: 1,
  isScanning: false,
  isPurging: false,
  sessionOpen: false,
  authenticated: false,
  progressTimer: null,
  searchTimer: null,
  dirty: true,
};

const $ = (id) => document.getElementById(id);

const el = {
  authBadge: $('auth-status-badge'),
  authText: $('auth-status-text'),
  btnOpenBrowser: $('btn-open-browser'),
  btnCloseBrowser: $('btn-close-browser'),
  btnScanCategory: $('btn-scan-category'),
  scanCategoryLabel: $('scan-category-label'),
  btnScanAll: $('btn-scan-all'),
  scanAllLabel: $('scan-all-label'),
  btnExportCsv: $('btn-export-csv'),
  btnOpenImport: $('btn-open-import'),

  errorBanner: $('error-banner'),
  errorText: $('error-banner-text'),
  btnDismissError: $('btn-dismiss-error'),
  toastHost: $('toast-host'),

  scanBanner: $('scan-active-banner'),
  scanBannerTitle: $('scan-banner-title'),
  scanBannerDesc: $('scan-banner-desc'),
  btnStopScan: $('btn-stop-scan-dashboard'),

  resumeBanner: $('resume-banner'),
  resumeBannerDesc: $('resume-banner-desc'),
  btnResumePurge: $('btn-resume-purge'),
  btnDiscardPurge: $('btn-discard-purge'),

  countFriends: $('count-friends'),
  countGroups: $('count-groups'),
  countPages: $('count-pages'),
  countFriendsSel: $('count-friends-selected'),
  countGroupsSel: $('count-groups-selected'),
  countPagesSel: $('count-pages-selected'),
  countSelected: $('count-selected'),
  countKept: $('count-kept'),
  footerRemoveCount: $('footer-remove-count'),

  badgeFriends: $('badge-friends'),
  badgeGroups: $('badge-groups'),
  badgePages: $('badge-pages'),

  searchInput: $('search-input'),
  tabSelectionSummary: $('tab-selection-summary'),

  btnSelectPage: $('btn-select-page'),
  btnDeselectPage: $('btn-deselect-page'),
  btnInvertPage: $('btn-invert-page'),
  btnSelectAll: $('btn-select-all'),
  btnDeselectAll: $('btn-deselect-all'),
  btnCategoryPurge: $('btn-category-purge'),

  paginationBar: $('pagination-bar'),
  paginationBarBottom: $('pagination-bar-bottom'),
  paginationSummary: $('pagination-summary'),
  paginationSummaryBottom: $('pagination-summary-bottom'),
  pageIndicator: $('page-indicator'),
  pageIndicatorBottom: $('page-indicator-bottom'),
  pageSizeSelect: $('page-size-select'),

  markdownViewer: $('markdown-viewer'),
  btnCopyMarkdown: $('btn-copy-markdown'),

  btnPurgeTabFooter: $('btn-purge-tab-footer'),
  footerTabPurgeLabel: $('footer-tab-purge-label'),
  btnTriggerPurge: $('btn-trigger-purge'),

  purgeModal: $('purge-modal'),
  modalHeading: $('modal-heading'),
  modalSubStatus: $('modal-sub-status'),
  btnStopPurge: $('btn-stop-purge'),
  btnCloseModal: $('btn-close-modal'),
  modalProgressLabel: $('modal-progress-label'),
  modalPercentage: $('modal-percentage'),
  modalProgressFill: $('modal-progress-fill'),
  modalSuccessCount: $('modal-success-count'),
  modalFailCount: $('modal-fail-count'),
  modalElapsed: $('modal-elapsed-time'),
  modalCurrentItem: $('modal-current-item'),
  modalLog: $('modal-log-terminal'),
};

const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');
const pageSizeLabels = document.querySelectorAll('.page-size-label');

const CAT_LABEL = { friends: 'Friends', groups: 'Groups', pages: 'Pages', markdown: 'Tab' };
const AVATAR_FALLBACK =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52" viewBox="0 0 52 52">' +
      '<rect width="52" height="52" rx="26" fill="#1e2637"/>' +
      '<circle cx="26" cy="20" r="8" fill="#3b4a63"/>' +
      '<path d="M10 46c0-8.8 7.2-16 16-16s16 7.2 16 16z" fill="#3b4a63"/></svg>'
  );

// --------------------------------------------------------------------------
// networking
// --------------------------------------------------------------------------

async function api(path, options) {
  const res = await fetch(path, options);
  const text = await res.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch (e) {
    body = { raw: text };
  }
  if (!res.ok) {
    throw new Error(body.detail || body.message || `${res.status} ${res.statusText}`);
  }
  return body;
}

const post = (path, payload) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });

// --------------------------------------------------------------------------
// notifications
// --------------------------------------------------------------------------

function toast(message, kind = 'info', ms = 4000) {
  if (!el.toastHost) return;
  const node = document.createElement('div');
  node.className = `toast toast-${kind}`;
  node.textContent = message;
  el.toastHost.appendChild(node);
  requestAnimationFrame(() => node.classList.add('toast-in'));
  setTimeout(() => {
    node.classList.remove('toast-in');
    setTimeout(() => node.remove(), 300);
  }, ms);
}

let lastShownError = '';
function showError(message) {
  if (!el.errorBanner) return;
  if (!message) {
    el.errorBanner.classList.add('hidden');
    lastShownError = '';
    return;
  }
  if (message === lastShownError) return;
  lastShownError = message;
  el.errorText.textContent = message;
  el.errorBanner.classList.remove('hidden');
}

// --------------------------------------------------------------------------
// boot
// --------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  refreshData();
  refreshAuth();
  pollStatus();
  setInterval(pollStatus, 2000);
});

function bindEvents() {
  tabButtons.forEach((btn) =>
    btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')))
  );

  if (el.searchInput) {
    el.searchInput.addEventListener('input', (e) => {
      const value = e.target.value.toLowerCase().trim();
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => {
        state.searchQuery = value;
        state.currentPage = 1;
        render();
      }, 140);
    });
  }

  if (el.pageSizeSelect) {
    el.pageSizeSelect.addEventListener('change', (e) => {
      state.pageSize = parseInt(e.target.value, 10) || 300;
      state.currentPage = 1;
      pageSizeLabels.forEach((n) => {
        n.textContent = state.pageSize >= 100000 ? 'All' : state.pageSize;
      });
      render();
    });
  }

  const goFirst = () => { state.currentPage = 1; render(true); };
  const goPrev = () => { if (state.currentPage > 1) { state.currentPage--; render(true); } };
  const goNext = () => { if (state.currentPage < totalPages()) { state.currentPage++; render(true); } };
  const goLast = () => { state.currentPage = totalPages(); render(true); };

  [['btn-first-page', goFirst], ['btn-prev-page', goPrev], ['btn-next-page', goNext], ['btn-last-page', goLast],
   ['btn-first-page-b', goFirst], ['btn-prev-page-b', goPrev], ['btn-next-page-b', goNext], ['btn-last-page-b', goLast]]
    .forEach(([id, fn]) => { const b = $(id); if (b) b.addEventListener('click', fn); });

  if (el.btnOpenBrowser) el.btnOpenBrowser.addEventListener('click', openBrowser);
  if (el.btnCloseBrowser) el.btnCloseBrowser.addEventListener('click', closeBrowser);
  if (el.btnScanCategory) el.btnScanCategory.addEventListener('click', () => startScan(
    state.activeTab === 'markdown' ? 'all' : state.activeTab));
  if (el.btnScanAll) el.btnScanAll.addEventListener('click', () => startScan('all'));
  if (el.btnStopScan) el.btnStopScan.addEventListener('click', stopScan);
  if (el.btnResumePurge) el.btnResumePurge.addEventListener('click', resumePurge);
  if (el.btnDiscardPurge) el.btnDiscardPurge.addEventListener('click', discardPurge);
  if (el.btnDismissError) el.btnDismissError.addEventListener('click', () => showError(''));

  if (el.btnSelectPage) el.btnSelectPage.addEventListener('click', () => setPageSelection(true));
  if (el.btnDeselectPage) el.btnDeselectPage.addEventListener('click', () => setPageSelection(false));
  if (el.btnInvertPage) el.btnInvertPage.addEventListener('click', invertPageSelection);
  if (el.btnSelectAll) el.btnSelectAll.addEventListener('click', () => setTabSelection(true));
  if (el.btnDeselectAll) el.btnDeselectAll.addEventListener('click', () => setTabSelection(false));

  // Per-category Scan / Delete buttons on the metric cards.
  const metricsGrid = document.querySelector('.metrics-grid');
  if (metricsGrid) {
    metricsGrid.addEventListener('click', (e) => {
      const scanBtn = e.target.closest('.metric-btn-scan');
      if (scanBtn) {
        const cat = scanBtn.getAttribute('data-cat');
        switchTab(cat);                 // jump to what we're scanning, immediate feedback
        startScan(cat);
        return;
      }
      const delBtn = e.target.closest('.metric-btn-del');
      if (delBtn) {
        const cat = delBtn.getAttribute('data-cat');
        switchTab(cat);           // show what's about to be removed
        purgeCategory(cat);
      }
    });
  }

  if (el.btnCategoryPurge) el.btnCategoryPurge.addEventListener('click', () => purgeCategory(state.activeTab));
  if (el.btnPurgeTabFooter) el.btnPurgeTabFooter.addEventListener('click', () => purgeCategory(state.activeTab));
  if (el.btnTriggerPurge) el.btnTriggerPurge.addEventListener('click', purgeEverything);
  if (el.btnStopPurge) el.btnStopPurge.addEventListener('click', stopPurge);
  if (el.btnCloseModal) el.btnCloseModal.addEventListener('click', () => el.purgeModal.classList.add('hidden'));

  if (el.btnExportCsv) el.btnExportCsv.addEventListener('click', exportCsv);
  if (el.btnCopyMarkdown) el.btnCopyMarkdown.addEventListener('click', copyMarkdown);

  bindImportModal();

  // One delegated handler for every card in every tab.
  document.querySelectorAll('.items-grid').forEach((grid) => {
    grid.addEventListener('change', onCardToggle);
    // Broken Facebook CDN URLs fall back to the inline placeholder. Capture
    // phase, because 'error' from an <img> does not bubble.
    grid.addEventListener('error', (e) => {
      const img = e.target;
      if (img && img.tagName === 'IMG' && img.src !== AVATAR_FALLBACK) img.src = AVATAR_FALLBACK;
    }, true);
    grid.addEventListener('click', (e) => {
      if (e.target.closest('a') || e.target.closest('.custom-checkbox')) return;
      const card = e.target.closest('.item-card');
      if (!card) return;
      const box = card.querySelector('.item-checkbox');
      if (box) { box.checked = !box.checked; box.dispatchEvent(new Event('change', { bubbles: true })); }
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && el.purgeModal && !el.purgeModal.classList.contains('hidden')
        && !state.isPurging) {
      el.purgeModal.classList.add('hidden');
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
      e.preventDefault();
      if (el.searchInput) el.searchInput.focus();
    }
  });
}

function bindImportModal() {
  const modal = $('import-modal');
  const textarea = $('import-textarea');
  const fileInput = $('import-file-input');
  const statusText = $('import-status-text');
  const btnSubmit = $('btn-submit-import');

  if (el.btnOpenImport) el.btnOpenImport.addEventListener('click', () => {
    if (modal) modal.classList.remove('hidden');
    if (textarea) textarea.focus();
  });
  const close = () => modal && modal.classList.add('hidden');
  const btnClose = $('btn-close-import');
  if (btnClose) btnClose.addEventListener('click', close);
  if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) close(); });

  const btnBrowse = $('btn-browse-file');
  if (btnBrowse && fileInput) {
    btnBrowse.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        textarea.value = ev.target.result;
        if (statusText) statusText.textContent = `Loaded ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
      };
      reader.readAsText(file);
    });
  }

  // Drag & drop was advertised in the UI but never wired up.
  if (textarea) {
    ['dragover', 'dragenter'].forEach((evt) =>
      textarea.addEventListener(evt, (e) => { e.preventDefault(); textarea.classList.add('drop-active'); }));
    ['dragleave', 'drop'].forEach((evt) =>
      textarea.addEventListener(evt, () => textarea.classList.remove('drop-active')));
    textarea.addEventListener('drop', (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        textarea.value = ev.target.result;
        if (statusText) statusText.textContent = `Loaded ${file.name}`;
      };
      reader.readAsText(file);
    });
  }

  if (btnSubmit) {
    btnSubmit.addEventListener('click', async () => {
      const raw = (textarea.value || '').trim();
      if (!raw) { toast('Paste JSON or choose a file first.', 'warning'); return; }
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        toast(`Invalid JSON: ${err.message}`, 'error', 6000);
        return;
      }
      btnSubmit.disabled = true;
      btnSubmit.textContent = 'Importing...';
      try {
        const result = await post('/api/import', parsed);
        toast(`Imported: ${result.counts.friends} friends, ${result.counts.groups} groups, ${result.counts.pages} pages.`, 'success');
        close();
        await refreshData();
      } catch (err) {
        toast(`Import failed: ${err.message}`, 'error', 6000);
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = 'Load Into Dashboard';
      }
    });
  }
}

// --------------------------------------------------------------------------
// session / scan
// --------------------------------------------------------------------------

async function openBrowser() {
  el.btnOpenBrowser.disabled = true;
  el.authText.textContent = 'Opening browser...';
  try {
    const res = await post('/api/browser/open');
    if (res.success) {
      toast('Browser window opened. Log into Facebook if prompted.', 'info', 6000);
      showError('');
    } else {
      showError(res.message || 'Could not open the browser.');
    }
  } catch (e) {
    showError(e.message);
  } finally {
    el.btnOpenBrowser.disabled = false;
    setTimeout(refreshAuth, 2500);
  }
}

async function closeBrowser() {
  try {
    const res = await post('/api/browser/close');
    toast(res.message, res.success ? 'info' : 'warning');
    refreshAuth();
  } catch (e) {
    showError(e.message);
  }
}

async function startScan(category) {
  if (state.isScanning) return;
  try {
    const res = await post(`/api/scan/${category}`);
    if (res.success) {
      state.isScanning = true;
      showError('');
      toast(`Scanning ${category}...`, 'info');
    } else {
      showError(res.message);
    }
  } catch (e) {
    showError(e.message);
  }
}

async function stopScan() {
  el.btnStopScan.disabled = true;
  try {
    await post('/api/scan/stop');
  } catch (e) {
    showError(e.message);
  } finally {
    setTimeout(() => { el.btnStopScan.disabled = false; }, 1500);
  }
}

async function refreshAuth() {
  try {
    const data = await api('/api/auth/check');
    state.authenticated = !!data.authenticated;
    state.sessionOpen = !!data.sessionOpen;
    if (data.authenticated) {
      el.authBadge.className = 'status-pill status-connected';
      el.authText.textContent = data.userName && data.userName !== 'Active Session'
        ? `Signed in: ${data.userName}` : 'Facebook session active';
    } else {
      el.authBadge.className = 'status-pill status-disconnected';
      el.authText.textContent = data.sessionOpen ? 'Log in inside the browser window' : 'Browser closed';
    }
  } catch (e) {
    el.authBadge.className = 'status-pill status-disconnected';
    el.authText.textContent = 'Server offline';
  }
}

async function refreshData() {
  try {
    const data = await api('/api/data');
    state.friends = data.friends || [];
    state.groups = data.groups || [];
    state.pages = data.pages || [];
    render(true);
  } catch (e) {
    showError(`Could not load data: ${e.message}`);
  }
}

let lastCountsKey = '';
let wasScanning = false;

async function pollStatus() {
  let data;
  try {
    data = await api('/api/status');
  } catch (e) {
    el.authBadge.className = 'status-pill status-disconnected';
    el.authText.textContent = 'Server offline - is the app still running?';
    return;
  }

  state.isScanning = data.isScanning;
  state.isPurging = data.isPurging;
  state.sessionOpen = !!(data.session && data.session.open);

  if (data.lastError) showError(data.lastError);

  // scan banner + button state
  const info = data.scanInfo || {};
  if (data.isScanning) {
    el.btnScanAll.disabled = true;
    el.btnScanCategory.disabled = true;
    el.scanAllLabel.textContent = 'Scanning...';
    el.scanCategoryLabel.textContent = 'Scanning...';
    el.scanBanner.classList.remove('hidden');
    if (info.stage === 'waiting_login') {
      el.scanBannerTitle.textContent = 'Facebook login required';
      el.scanBannerDesc.textContent = 'Log into Facebook in the open browser window - extraction resumes automatically.';
    } else {
      el.scanBannerTitle.textContent = 'Scan in progress';
      el.scanBannerDesc.textContent = info.message || 'Extracting items...';
    }
  } else {
    el.btnScanAll.disabled = false;
    el.btnScanCategory.disabled = false;
    el.scanAllLabel.textContent = 'Scan All';
    el.scanCategoryLabel.textContent = `Scan ${CAT_LABEL[state.activeTab] || 'Tab'} Only`;
    el.scanBanner.classList.add('hidden');
  }

  if (el.btnCloseBrowser) {
    el.btnCloseBrowser.classList.toggle('hidden', !state.sessionOpen);
  }

  // Per-category Scan/Delete buttons: lock everything while a scan or purge runs,
  // and mark the category currently being scanned so it's obvious what's live.
  const busy = data.isScanning || data.isPurging;
  const scanningCat = data.isScanning ? (info.category || '') : '';
  paintCategoryButtons(data.selected || {}, busy);
  document.querySelectorAll('.metric-btn-scan').forEach((b) => {
    const cat = b.getAttribute('data-cat');
    const live = data.isScanning && (scanningCat === cat || scanningCat === 'all');
    b.classList.toggle('is-busy', live);
    b.textContent = live ? '⟳ Scanning…' : `⟳ Scan ${CAT_LABEL[cat]}`;
  });

  // No two browser jobs can run at once, so lock every action that needs the
  // browser while a scan OR a purge is live -- clicking them only earned a
  // server rejection before.
  el.btnScanAll.disabled = busy;
  el.btnScanCategory.disabled = busy;
  [el.btnCategoryPurge, el.btnPurgeTabFooter, el.btnTriggerPurge].forEach((b) => {
    if (b) b.disabled = busy;
  });
  if (el.btnResumePurge) el.btnResumePurge.disabled = busy;

  // Interrupted-purge resume banner (only when idle).
  const resumable = data.resumablePurge || {};
  if (el.resumeBanner) {
    const show = !!resumable.available && !data.isPurging && !data.isScanning;
    el.resumeBanner.classList.toggle('hidden', !show);
    if (show && el.resumeBannerDesc) {
      el.resumeBannerDesc.textContent =
        `${resumable.count} item(s) remain from an interrupted run. Continue from exactly where it left off.`;
    }
  }

  // Pull the item lists only when the server-side counts actually changed --
  // re-fetching every tick used to blow away scroll position mid-triage.
  const key = JSON.stringify(data.counts) + '|' + (data.lastScanTime || '');
  if (key !== lastCountsKey) {
    lastCountsKey = key;
    await refreshData();
  }

  if (wasScanning && !data.isScanning) {
    await refreshAuth();
    await refreshData();
    toast(`Scan finished - ${data.counts.total} item(s) loaded.`, 'success');
  }
  wasScanning = data.isScanning;

  if (data.isPurging) {
    el.purgeModal.classList.remove('hidden');
    updatePurgeModal(data.purgeProgress);
    if (!state.progressTimer) startProgressPolling();
  }
}

// --------------------------------------------------------------------------
// list rendering
// --------------------------------------------------------------------------

function activeList() {
  return state[state.activeTab] || [];
}

function filteredList() {
  const list = activeList();
  if (!state.searchQuery) return list;
  const q = state.searchQuery;
  return list.filter(
    (i) => (i.name || '').toLowerCase().includes(q) || (i.url || '').toLowerCase().includes(q)
  );
}

function totalPages() {
  return Math.max(1, Math.ceil(filteredList().length / state.pageSize));
}

function pageItems() {
  const filtered = filteredList();
  const start = (state.currentPage - 1) * state.pageSize;
  return filtered.slice(start, start + state.pageSize);
}

function escapeHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function render(resetScroll) {
  updateMetrics();
  invalidateMarkdown();

  if (state.activeTab === 'markdown') return;

  const container = $(`list-${state.activeTab}`);
  if (!container) return;

  const list = activeList();
  const filtered = filteredList();
  const pages = totalPages();
  if (state.currentPage > pages) state.currentPage = pages;
  if (state.currentPage < 1) state.currentPage = 1;

  const items = pageItems();
  const start = items.length === 0 ? 0 : (state.currentPage - 1) * state.pageSize + 1;
  const end = items.length === 0 ? 0 : Math.min(start + items.length - 1, filtered.length);

  const selectedInTab = list.filter((x) => x.selected !== false).length;
  const selectedOnPage = items.filter((x) => x.selected !== false).length;

  el.tabSelectionSummary.textContent =
    `${list.length} in tab (${selectedInTab} to remove) - showing ${start}-${end} (${selectedOnPage} checked here)`;

  const summary = `Showing ${start}-${end} of ${filtered.length}`;
  el.paginationSummary.textContent = summary;
  if (el.paginationSummaryBottom) el.paginationSummaryBottom.textContent = summary;
  const pageStr = `Page ${state.currentPage} of ${pages}`;
  el.pageIndicator.textContent = pageStr;
  if (el.pageIndicatorBottom) el.pageIndicatorBottom.textContent = pageStr;

  const first = state.currentPage <= 1;
  const last = state.currentPage >= pages;
  ['btn-first-page', 'btn-prev-page', 'btn-first-page-b', 'btn-prev-page-b']
    .forEach((id) => { const b = $(id); if (b) b.disabled = first; });
  ['btn-next-page', 'btn-last-page', 'btn-next-page-b', 'btn-last-page-b']
    .forEach((id) => { const b = $(id); if (b) b.disabled = last; });

  if (items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${state.activeTab === 'pages' ? '&#128196;' : '&#128101;'}</div>
        <h3>No ${CAT_LABEL[state.activeTab]} to show</h3>
        <p>${state.searchQuery ? 'Nothing matches your search.' : 'Open the browser, log in, then run a scan.'}</p>
      </div>`;
    return;
  }

  container.innerHTML = items.map(cardHtml).join('');
  if (resetScroll) container.scrollTop = 0;
}

function cardHtml(item) {
  const selected = item.selected !== false;
  const name = escapeHtml(item.name || 'Unknown');
  const id = escapeHtml(item.id || item.url || '');
  const url = escapeHtml(item.url || '#');
  // Only emit a src when there is a real one. Repeating the fallback data-URI
  // (plus an inline onerror) across 300 cards added ~120KB of attribute text and
  // 300 handler compilations to every page flip.
  const avatar = item.avatar && String(item.avatar).startsWith('http')
    ? ` src="${escapeHtml(item.avatar)}"` : '';
  const sub = item.subText ? `<div class="item-sub">${escapeHtml(item.subText)}</div>` : '';

  return `
    <div class="item-card ${selected ? 'is-selected' : 'is-kept'}" data-id="${id}">
      <div class="item-main-info">
        <img class="item-avatar" alt="" loading="lazy" decoding="async"${avatar}>
        <div class="item-text">
          <div class="item-name" title="${name}">${name}</div>
          ${sub}
          <a class="item-link" href="${url}" target="_blank" rel="noopener noreferrer">
            <span>View on Facebook</span>
          </a>
        </div>
      </div>
      <div class="toggle-wrapper">
        <span class="toggle-label ${selected ? 'label-remove' : 'label-keep'}">${selected ? 'REMOVE' : 'KEEP'}</span>
        <label class="custom-checkbox">
          <input type="checkbox" class="item-checkbox" data-id="${id}"
                 data-type="${escapeHtml(item.type || 'friend')}" ${selected ? 'checked' : ''}>
          <span class="checkbox-mark"></span>
        </label>
      </div>
    </div>`;
}

function paintCard(card, selected) {
  card.classList.toggle('is-selected', selected);
  card.classList.toggle('is-kept', !selected);
  const label = card.querySelector('.toggle-label');
  if (label) {
    label.className = `toggle-label ${selected ? 'label-remove' : 'label-keep'}`;
    label.textContent = selected ? 'REMOVE' : 'KEEP';
  }
}

async function onCardToggle(e) {
  const box = e.target.closest('.item-checkbox');
  if (!box) return;

  const id = box.getAttribute('data-id');
  const type = box.getAttribute('data-type');
  const checked = box.checked;

  const item = activeList().find((x) => x.id === id || x.url === id);
  if (item) item.selected = checked;

  const card = box.closest('.item-card');
  if (card) paintCard(card, checked);

  updateMetrics();
  invalidateMarkdown();

  try {
    await post('/api/items/toggle', { item_id: id, item_type: type, selected: checked });
  } catch (err) {
    // Roll the UI back so the screen never claims a state the server rejected.
    if (item) item.selected = !checked;
    box.checked = !checked;
    if (card) paintCard(card, !checked);
    updateMetrics();
    showError(`Could not save that change: ${err.message}`);
  }
}

function switchTab(tab) {
  if (!tab) return;
  state.activeTab = tab;
  state.currentPage = 1;

  tabButtons.forEach((b) => b.classList.toggle('active', b.getAttribute('data-tab') === tab));
  tabPanels.forEach((p) => p.classList.toggle('active', p.id === `panel-${tab}`));

  const label = CAT_LABEL[tab] || 'Tab';
  if (el.scanCategoryLabel && !state.isScanning) el.scanCategoryLabel.textContent = `Scan ${label} Only`;
  if (el.footerTabPurgeLabel) el.footerTabPurgeLabel.textContent = `Purge Checked ${label}`;
  if (el.btnCategoryPurge) el.btnCategoryPurge.innerHTML = `<span>Purge Checked ${label}</span>`;

  const isMarkdown = tab === 'markdown';
  el.paginationBar.classList.toggle('hidden', isMarkdown);
  el.paginationBarBottom.classList.toggle('hidden', isMarkdown);
  [el.btnSelectPage, el.btnDeselectPage, el.btnInvertPage, el.btnSelectAll, el.btnDeselectAll, el.btnCategoryPurge]
    .forEach((b) => { if (b) b.disabled = isMarkdown; });

  render(true);
}

function updateMetrics() {
  const counts = {
    friends: state.friends.length,
    groups: state.groups.length,
    pages: state.pages.length,
  };
  const sel = {
    friends: state.friends.filter((x) => x.selected !== false).length,
    groups: state.groups.filter((x) => x.selected !== false).length,
    pages: state.pages.filter((x) => x.selected !== false).length,
  };
  const totalAll = counts.friends + counts.groups + counts.pages;
  const totalSel = sel.friends + sel.groups + sel.pages;

  el.countFriends.textContent = counts.friends.toLocaleString();
  el.countGroups.textContent = counts.groups.toLocaleString();
  el.countPages.textContent = counts.pages.toLocaleString();
  el.countFriendsSel.textContent = sel.friends;
  el.countGroupsSel.textContent = sel.groups;
  el.countPagesSel.textContent = sel.pages;
  el.badgeFriends.textContent = counts.friends;
  el.badgeGroups.textContent = counts.groups;
  el.badgePages.textContent = counts.pages;
  el.countSelected.textContent = totalSel.toLocaleString();
  el.countKept.textContent = (totalAll - totalSel).toLocaleString();
  el.footerRemoveCount.textContent = totalSel.toLocaleString();

  paintCategoryButtons(sel, state.isScanning || state.isPurging);
}

// Delete buttons show exactly how many are checked in that category and disable
// when there's nothing to remove -- so each category is acted on independently.
function paintCategoryButtons(sel, busy) {
  ['friends', 'groups', 'pages'].forEach((cat) => {
    const n = sel[cat] || 0;
    document.querySelectorAll(`.metric-btn-del[data-cat="${cat}"]`).forEach((b) => {
      b.textContent = n > 0 ? `🗑 Delete ${n} Checked` : '🗑 Delete Checked';
      b.disabled = busy || n === 0;
    });
    document.querySelectorAll(`.metric-btn-scan[data-cat="${cat}"]`).forEach((b) => {
      b.disabled = busy;
    });
  });
}

// Regenerating ~1400 lines on every toggle and page-flip was the single biggest
// render cost; only build it when the Markdown tab is actually on screen.
let markdownStale = true;

function invalidateMarkdown() {
  markdownStale = true;
  if (state.activeTab === 'markdown') updateMarkdown();
}

function updateMarkdown() {
  if (!el.markdownViewer) return;
  if (!markdownStale && state.activeTab !== 'markdown') return;
  markdownStale = false;
  const section = (title, rows) => {
    const lines = ['---', '', `## ${title} (${rows.length})`, ''];
    rows.forEach((r) => {
      lines.push(`- [${r.selected !== false ? 'x' : ' '}] [${r.name || 'Unknown'}](${r.url || '#'})`);
    });
    lines.push('');
    return lines;
  };
  el.markdownViewer.value = [
    '# Facebook Zenith Cleaner - Triage Checklist',
    `**Generated:** ${new Date().toLocaleString()}`,
    '',
    '> `[x]` = slated for REMOVAL  |  `[ ]` = KEEP',
    '',
    ...section('Friends', state.friends),
    ...section('Groups', state.groups),
    ...section('Pages', state.pages),
  ].join('\n');
}

// --------------------------------------------------------------------------
// batch selection
// --------------------------------------------------------------------------

async function setPageSelection(selected) {
  if (state.activeTab === 'markdown') return;
  const items = pageItems();
  if (!items.length) return;
  items.forEach((i) => { i.selected = selected; });
  render();
  try {
    await post('/api/items/toggle-bulk', {
      item_type: state.activeTab,
      item_ids: items.map((i) => i.id),
      selected,
    });
  } catch (e) {
    showError(e.message);
    await refreshData();
  }
}

async function invertPageSelection() {
  if (state.activeTab === 'markdown') return;
  const items = pageItems();
  if (!items.length) return;
  items.forEach((i) => { i.selected = i.selected === false; });
  render();
  try {
    await post('/api/items/invert', {
      item_type: state.activeTab,
      item_ids: items.map((i) => i.id),
    });
  } catch (e) {
    showError(e.message);
    await refreshData();
  }
}

async function setTabSelection(selected) {
  if (state.activeTab === 'markdown') return;
  activeList().forEach((i) => { i.selected = selected; });
  render();
  try {
    await post('/api/items/batch-toggle', { item_type: state.activeTab, selected });
  } catch (e) {
    showError(e.message);
    await refreshData();
  }
}

// --------------------------------------------------------------------------
// purge
// --------------------------------------------------------------------------

function purgeCategory(category) {
  if (category === 'markdown') { toast('Pick a Friends, Groups or Pages tab first.', 'warning'); return; }
  const list = state[category] || [];
  const queued = list.filter((x) => x.selected !== false);
  if (!queued.length) { toast(`Nothing checked in ${CAT_LABEL[category]}.`, 'warning'); return; }

  const label = CAT_LABEL[category];
  if (!confirm(
    `Remove ${queued.length} checked ${label} from your Facebook account?\n\n` +
    `Pacing: 5-9s between items, plus a cooling break every 15.\n` +
    `This cannot be undone.`
  )) return;

  el.modalHeading.textContent = `Removing ${queued.length} ${label}`;
  runPurge({ category });
}

function purgeEverything() {
  const queued = [
    ...state.friends.filter((x) => x.selected !== false),
    ...state.groups.filter((x) => x.selected !== false),
    ...state.pages.filter((x) => x.selected !== false),
  ];
  if (!queued.length) { toast('Nothing is checked for removal.', 'warning'); return; }

  if (!confirm(
    `Remove ${queued.length} item(s) across all tabs from your Facebook account?\n\n` +
    `Pacing: 5-9s between items, plus a cooling break every 15.\n` +
    `This cannot be undone.`
  )) return;

  el.modalHeading.textContent = `Removing ${queued.length} items (all tabs)`;
  runPurge({ category: 'all' });
}

async function runPurge(payload) {
  el.purgeModal.classList.remove('hidden');
  el.btnCloseModal.classList.add('hidden');
  el.btnStopPurge.disabled = false;
  el.modalLog.innerHTML = '<div class="log-entry log-info">Starting...</div>';

  try {
    const res = await post('/api/purge/start', payload);
    if (res.success) {
      startProgressPolling();
    } else {
      el.purgeModal.classList.add('hidden');
      toast(res.message, 'warning', 6000);
    }
  } catch (e) {
    el.purgeModal.classList.add('hidden');
    showError(e.message);
  }
}

async function discardPurge() {
  if (!confirm('Cancel the parked removal queue?\n\nThis removes NOTHING from Facebook — it only clears the pending job so the app goes back to normal.')) return;
  el.btnDiscardPurge.disabled = true;
  try {
    const res = await post('/api/purge/discard');
    toast(res.message || 'Queue cleared.', 'info');
    if (el.resumeBanner) el.resumeBanner.classList.add('hidden');
  } catch (e) {
    showError(e.message);
  } finally {
    el.btnDiscardPurge.disabled = false;
  }
}

async function resumePurge() {
  el.btnResumePurge.disabled = true;
  el.modalHeading.textContent = 'Resuming interrupted purge';
  el.purgeModal.classList.remove('hidden');
  el.btnCloseModal.classList.add('hidden');
  el.btnStopPurge.disabled = false;
  el.modalLog.innerHTML = '<div class="log-entry log-info">Resuming...</div>';
  try {
    const res = await post('/api/purge/resume');
    if (res.success) {
      if (el.resumeBanner) el.resumeBanner.classList.add('hidden');
      startProgressPolling();
    } else {
      el.purgeModal.classList.add('hidden');
      toast(res.message, 'warning', 6000);
    }
  } catch (e) {
    el.purgeModal.classList.add('hidden');
    showError(e.message);
  } finally {
    el.btnResumePurge.disabled = false;
  }
}

function startProgressPolling() {
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = setInterval(async () => {
    try {
      const p = await api('/api/purge/progress');
      updatePurgeModal(p);
      if (!p.is_running) {
        clearInterval(state.progressTimer);
        state.progressTimer = null;
        el.btnCloseModal.classList.remove('hidden');
        el.btnStopPurge.disabled = true;
        await refreshData();
        if (p.blocked) {
          const left = Math.max(0, (p.total_items || 0) - (p.processed_items || 0));
          toast(`⛔ Facebook security check hit - purge stopped with ${left} left to protect your account. ` +
            `Clear the check in the browser window, then click "Resume Purge".`, 'error', 12000);
        } else if (p.resumable) {
          const left = Math.max(0, (p.total_items || 0) - (p.processed_items || 0));
          toast(`Paused - ${left} item(s) still to remove. Click "Resume Purge" to finish.`, 'warning', 8000);
        } else {
          toast(`Done: ${p.successful_items} removed, ${p.failed_items} failed.`,
            p.failed_items ? 'warning' : 'success', 7000);
        }
      }
    } catch (e) {
      clearInterval(state.progressTimer);
      state.progressTimer = null;
    }
  }, 1200);
}

function updatePurgeModal(p) {
  if (!p) return;
  const total = p.total_items || 0;
  const done = p.processed_items || 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;

  el.modalProgressLabel.textContent = `Item ${done} of ${total}`;
  el.modalPercentage.textContent = `${pct}%`;
  el.modalProgressFill.style.width = `${pct}%`;
  el.modalSuccessCount.textContent = p.successful_items || 0;
  el.modalFailCount.textContent = p.failed_items || 0;
  el.modalElapsed.textContent = formatDuration(p.elapsed_seconds || 0);
  el.modalCurrentItem.textContent = p.current_action || 'Working...';
  if (el.modalSubStatus) {
    el.modalSubStatus.textContent = p.blocked
      ? '⛔ Facebook asked for a security check. Clear it in the browser window, then click Resume.'
      : (p.paused
        ? '⏸️ Paused - waiting for the internet. Resumes automatically, no items lost.'
        : (p.is_running
          ? 'Human-paced removal with anti-ban cooling breaks.'
          : 'Finished. Review the log below.'));
  }

  if (Array.isArray(p.log) && p.log.length) {
    el.modalLog.innerHTML = p.log
      .map((entry) => `<div class="log-entry log-${escapeHtml(entry.status || 'info')}">` +
        `[${escapeHtml(entry.time || '')}] ${escapeHtml(entry.text || '')}</div>`)
      .join('');
  }
}

function formatDuration(sec) {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return `${m}m ${s}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

async function stopPurge() {
  if (!confirm('Stop the purge after the current item?')) return;
  el.btnStopPurge.disabled = true;
  try {
    await post('/api/purge/stop');
    toast('Stopping after the current item...', 'info');
  } catch (e) {
    showError(e.message);
    el.btnStopPurge.disabled = false;
  }
}

// --------------------------------------------------------------------------
// export helpers
// --------------------------------------------------------------------------

async function exportCsv() {
  try {
    const res = await fetch('/api/export/csv');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `facebook_triage_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    toast('CSV exported.', 'success');
  } catch (e) {
    showError(`Export failed: ${e.message}`);
  }
}

async function copyMarkdown() {
  const text = el.markdownViewer.value;
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    el.markdownViewer.select();
    document.execCommand('copy');
  }
  el.btnCopyMarkdown.textContent = 'Copied';
  setTimeout(() => { el.btnCopyMarkdown.textContent = 'Copy to Clipboard'; }, 1800);
}
