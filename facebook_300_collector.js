/**
 * Facebook Zenith Triage - Universal Full-Grid 500+ Live Collector & Stealth Purge Suite
 * Scrapes true existing friends up to 500 items, avoids sidebar/LeftRail scroll confusion,
 * provides multi-lingual support (English & Urdu), Unicode NFD owner protection, and ultra-safe unfriend execution.
 */

(async function() {
  const old = document.getElementById('zenith-suite-overlay');
  if (old) old.remove();

  const hud = document.createElement('div');
  hud.id = 'zenith-suite-overlay';
  hud.style.cssText = `
    position: fixed; top: 16px; right: 16px; width: 600px; max-height: 92vh;
    background: rgba(9, 13, 22, 0.98); color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    border: 1.5px solid rgba(0, 242, 254, 0.5); border-radius: 22px;
    box-shadow: 0 25px 80px rgba(0, 0, 0, 0.98), 0 0 50px rgba(0, 242, 254, 0.25);
    z-index: 99999999; display: flex; flex-direction: column; overflow: hidden;
    backdrop-filter: blur(28px); -webkit-backdrop-filter: blur(28px);
  `;

  let items = new Map();
  let isScanning = false;
  let shouldStopScan = false;
  let isPurging = false;
  let shouldStopPurge = false;
  let targetCount = 500;

  const currentUrl = window.location.href;
  let activeTab = 'friends';
  if (currentUrl.includes('/groups')) activeTab = 'groups';
  else if (currentUrl.includes('/pages') || currentUrl.includes('category=liked')) activeTab = 'pages';

  hud.innerHTML = `
    <!-- Header -->
    <div style="padding: 16px 20px; background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <div id="zhud-live-dot" style="width: 12px; height: 12px; border-radius: 50%; background: #00f2fe; box-shadow: 0 0 12px #00f2fe;"></div>
        <div>
          <div style="font-size: 16px; font-weight: 900; background: linear-gradient(135deg, #00f2fe, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Facebook Zenith Triage</div>
          <div style="font-size: 11px; color: #94a3b8;">500-Item Full Grid Collector & Stealth Removal Suite (EN/UR)</div>
        </div>
      </div>
      <div style="display: flex; gap: 8px;">
        <button id="zhud-minimize" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: #94a3b8; border-radius: 8px; width: 32px; height: 32px; cursor: pointer; font-size: 16px;">_</button>
        <button id="zhud-close" style="background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #f87171; border-radius: 8px; width: 32px; height: 32px; cursor: pointer; font-size: 18px;">&times;</button>
      </div>
    </div>

    <!-- Category Tabs -->
    <div style="padding: 10px 16px; background: rgba(0,0,0,0.35); display: flex; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06);">
      <button id="zhud-tab-friends" style="flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; background: ${activeTab === 'friends' ? 'linear-gradient(135deg, #00f2fe, #1877f2)' : 'rgba(255,255,255,0.05)'}; color: #fff;">👥 Friends Grid</button>
      <button id="zhud-tab-groups" style="flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; background: ${activeTab === 'groups' ? 'linear-gradient(135deg, #00f2fe, #1877f2)' : 'rgba(255,255,255,0.05)'}; color: #fff;">👥 Joined Groups</button>
      <button id="zhud-tab-pages" style="flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; background: ${activeTab === 'pages' ? 'linear-gradient(135deg, #00f2fe, #1877f2)' : 'rgba(255,255,255,0.05)'}; color: #fff;">📄 Liked Pages</button>
    </div>

    <!-- Metrics Cards -->
    <div style="padding: 12px 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; background: rgba(0,0,0,0.25);">
      <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(0,242,254,0.25); border-radius: 12px; padding: 10px; text-align: center;">
        <div style="font-size: 10px; color: #94a3b8; text-transform: uppercase; font-weight: 700;">Discovered</div>
        <div id="zhud-cnt-total" style="font-size: 22px; font-weight: 900; color: #00f2fe;">0</div>
      </div>
      <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 12px; padding: 10px; text-align: center;">
        <div style="font-size: 10px; color: #fca5a5; text-transform: uppercase; font-weight: 700;">Slated to Remove</div>
        <div id="zhud-cnt-remove" style="font-size: 22px; font-weight: 900; color: #ef4444;">0</div>
      </div>
      <div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: 12px; padding: 10px; text-align: center;">
        <div style="font-size: 10px; color: #6ee7b7; text-transform: uppercase; font-weight: 700;">Kept (Safe)</div>
        <div id="zhud-cnt-kept" style="font-size: 22px; font-weight: 900; color: #10b981;">0</div>
      </div>
    </div>

    <!-- Scanning Progress Indicator -->
    <div id="zhud-scan-bar" style="height: 4px; background: rgba(255,255,255,0.05); width: 100%; overflow: hidden;">
      <div id="zhud-scan-fill" style="height: 100%; width: 0%; background: linear-gradient(90deg, #00f2fe, #6366f1); transition: width 0.2s;"></div>
    </div>

    <!-- Controls -->
    <div style="padding: 12px 16px; background: rgba(0,0,0,0.4); border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 8px;">
      <div style="display: flex; gap: 8px;">
        <input id="zhud-search" type="text" placeholder="🔍 Filter items to keep..." style="flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 9px 14px; color: #fff; font-size: 13px; outline: none;" />
        <button id="zhud-btn-scan" style="padding: 9px 16px; border-radius: 10px; font-size: 12px; font-weight: 800; background: linear-gradient(135deg, #0ea5e9, #0284c7); color: #fff; border: none; cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 4px 15px rgba(14,165,233,0.4);">
          ⚡ Auto-Scroll (Max 500)
        </button>
        <button id="zhud-btn-stop-scan" style="display: none; padding: 9px 14px; border-radius: 10px; font-size: 12px; font-weight: 800; background: #e11d48; color: #fff; border: none; cursor: pointer;">
          ⏹️ Stop Scan
        </button>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; flex-wrap: wrap; gap: 6px;">
        <div style="display: flex; gap: 8px; align-items: center;">
          <a href="javascript:void(0)" id="zhud-sel-all" style="color: #38bdf8; text-decoration: none; font-weight: 700;">Select All</a>
          <span style="color: #475569;">|</span>
          <a href="javascript:void(0)" id="zhud-uncheck-all" style="color: #34d399; text-decoration: none; font-weight: 700;">Keep All</a>
          <span style="color: #475569;">|</span>
          <a href="javascript:void(0)" id="zhud-invert" style="color: #cbd5e1; text-decoration: none;">Invert</a>
        </div>
        <div style="display: flex; gap: 6px;">
          <button id="zhud-btn-copy-json" style="padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; background: rgba(56,189,248,0.15); border: 1px solid rgba(56,189,248,0.3); color: #38bdf8; cursor: pointer;">📋 Copy JSON</button>
          <button id="zhud-btn-download-json" style="padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #34d399; cursor: pointer;">📥 Save JSON</button>
        </div>
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 11px;">
        <span id="zhud-status" style="color: #38bdf8; font-weight: 600;">Ready to scan active list</span>
      </div>
    </div>

    <!-- Items Grid List -->
    <div id="zhud-list" style="padding: 12px 16px; overflow-y: auto; max-height: 330px; display: flex; flex-direction: column; gap: 8px; background: rgba(0,0,0,0.2);">
      <div style="text-align: center; padding: 40px 10px; color: #64748b; font-size: 13px;">
        Scanning friends list... Loading items.
      </div>
    </div>

    <!-- Purge Footer -->
    <div style="padding: 14px 18px; background: rgba(0,0,0,0.65); border-top: 1px solid rgba(255,255,255,0.08); display: flex; flex-direction: column; gap: 10px;">
      <div id="zhud-progress-wrap" style="display: none; flex-direction: column; gap: 4px;">
        <div style="display: flex; justify-content: space-between; font-size: 11px;">
          <span id="zhud-prog-text" style="color: #00f2fe; font-weight: 700;">Removing item 0/0...</span>
          <span id="zhud-prog-pct" style="color: #f87171; font-weight: 800;">0%</span>
        </div>
        <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 999px; overflow: hidden;">
          <div id="zhud-prog-fill" style="height: 100%; width: 0%; background: linear-gradient(90deg, #ef4444, #f43f5e); transition: width 0.3s;"></div>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
        <button id="zhud-load-more" style="padding: 11px 16px; border-radius: 10px; font-size: 12px; font-weight: 700; background: rgba(255,255,255,0.06); color: #fff; border: 1px solid rgba(255,255,255,0.15); cursor: pointer;">+100 More</button>
        <button id="zhud-btn-purge" style="flex: 1; padding: 12px 20px; border-radius: 12px; font-size: 13px; font-weight: 900; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; cursor: pointer; box-shadow: 0 4px 25px rgba(239, 68, 68, 0.6); display: flex; justify-content: center; align-items: center; gap: 8px;">
          🔥 Execute Ultra-Safe Removal (5–9s Stealth)
        </button>
        <button id="zhud-btn-stop" style="display: none; padding: 12px 18px; border-radius: 12px; font-size: 12px; font-weight: 800; background: #334155; color: #fff; border: none; cursor: pointer;">Stop</button>
      </div>
    </div>
  `;

  document.body.appendChild(hud);

  document.getElementById('zhud-close').onclick = () => hud.remove();
  let isMin = false;
  document.getElementById('zhud-minimize').onclick = () => {
    isMin = !isMin;
    const bodyChildren = Array.from(hud.children).slice(1);
    bodyChildren.forEach(c => c.style.display = isMin ? 'none' : '');
    hud.style.width = isMin ? '260px' : '600px';
  };

  document.getElementById('zhud-tab-friends').onclick = () => {
    if (!window.location.href.includes('/friends')) {
      window.location.href = 'https://www.facebook.com/me/friends';
    } else {
      activeTab = 'friends';
      renderUI();
    }
  };
  document.getElementById('zhud-tab-groups').onclick = () => {
    if (!window.location.href.includes('/groups/joins')) {
      window.location.href = 'https://www.facebook.com/groups/joins';
    } else {
      activeTab = 'groups';
      renderUI();
    }
  };
  document.getElementById('zhud-tab-pages').onclick = () => {
    if (!window.location.href.includes('/pages')) {
      window.location.href = 'https://www.facebook.com/pages/?category=liked';
    } else {
      activeTab = 'pages';
      renderUI();
    }
  };

  const getExportJson = () => {
    const list = Array.from(items.values());
    const friends = activeTab === 'friends' ? list : [];
    const groups = activeTab === 'groups' ? list : [];
    const pages = activeTab === 'pages' ? list : [];
    return JSON.stringify({
      friends: friends,
      groups: groups,
      pages: pages,
      last_scan_time: new Date().toISOString().replace('T', ' ').substring(0, 19)
    }, null, 2);
  };

  document.getElementById('zhud-btn-copy-json').onclick = () => {
    const jsonStr = getExportJson();
    navigator.clipboard.writeText(jsonStr).then(() => {
      const statusEl = document.getElementById('zhud-status');
      if (statusEl) statusEl.textContent = '✅ Copied to Clipboard! Ready to paste into Dashboard.';
    }).catch(() => {
      prompt('Copy this JSON:', jsonStr);
    });
  };

  document.getElementById('zhud-btn-download-json').onclick = () => {
    const jsonStr = getExportJson();
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'scanned_data.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    const statusEl = document.getElementById('zhud-status');
    if (statusEl) statusEl.textContent = '📥 Saved scanned_data.json to Downloads!';
  };

  // --- Normalization & Protection Helpers ---

  function normalizeUnicode(str) {
    if (!str) return '';
    return String(str)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim();
  }

  function isProtectedOwner(name, url = '') {
    if (!name) return false;
    const norm = normalizeUnicode(name);
    const urlNorm = normalizeUnicode(url);
    // Never touch your own account: add your name / profile-handle stems here.
    const protectedStems = ['your_name', 'your_username'];
    return protectedStems.some(stem => norm.includes(stem) || urlNorm.includes(stem));
  }

  function isForbiddenButton(el) {
    if (!el) return true;
    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
    const title = (el.getAttribute('title') || '').toLowerCase();
    const combined = `${txt} ${aria} ${title}`;

    const badWords = [
      'add friend', 'add to story', 'follow', 'message', 'send request', 'request sent',
      'cancel request', 'دوست شامل کریں', 'درخواست بھیجیں', 'پیغام', 'فالو کریں', 'شامل کریں', 'add'
    ];
    return badWords.some(w => combined.includes(w));
  }

  function isFriendActionMenuButton(el) {
    if (!el || isForbiddenButton(el)) return false;
    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
    const hasPopup = el.getAttribute('aria-haspopup') === 'menu';

    const goodKeywords = [
      'friends', 'friend', 'edit friendship', 'manage friendship', 'more', 'options', 'see options',
      'actions for', 'دوست', 'مزید', 'اختیارات', 'دوستی'
    ];

    if (goodKeywords.some(w => aria.includes(w))) return true;
    if (['friends', 'friend', 'دوست', 'more', 'مزید'].includes(txt)) return true;
    if (hasPopup && !isForbiddenButton(el)) return true;

    return false;
  }

  function scrapeAllVisibleCards() {
    const genericExclusions = [
      'home', 'friends', 'watch', 'marketplace', 'groups', 'gaming', 'menu', 'facebook',
      'custom lists', 'birthdays', 'friend requests', 'suggestions', 'all friends',
      'photos', 'videos', 'about', 'terms', 'privacy policy', 'privacy center', 'reels',
      'posts', 'more', 'manage', 'search', 'edit profile', 'add to story', 'see all',
      'dashboard', 'professional dashboard', 'following', 'followers', 'events', 'saved',
      'memories', 'feeds', 'ad manager', 'ads manager', 'meta business suite', 'fundraisers',
      'climate science centre', 'orders and payments', 'recent ad activity', 'play games',
      'gaming video', 'live videos', 'messenger', 'notifications', 'settings & privacy',
      'help & support', 'display & accessibility', 'give feedback', 'log out', 'search friends',
      'select people\'s names to preview their profile', 'tv programmes', 'tv programs', 'books',
      'read', 'watched', 'apps and games', 'games', 'music', 'movies', 'films', 'sports',
      'athletes', 'teams', 'likes', 'check-ins', 'no watched to show', 'no read to show'
    ];

    const badUrlPatterns = [
      '/notifications', '/login_alerts', '/posts/', '/following', '/followers',
      '/professional_dashboard', '/events', '/saved', '/help/', '/policies/',
      '/memories', '/feeds', '/adsmanager', '/settings', '/messages',
      '/media_', '/photos', '/videos', '/about', '/likes', '/books', '/music', '/tv', '/games',
      'category=', 'l.php'
    ];

    // Priority: Target cards in main area to exclude left navigation sidebar
    const mainArea = document.querySelector('div[role="main"]') || document.body;
    const cardElements = Array.from(mainArea.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[data-pagelet*="Profile"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-suite-overlay'));

    for (const card of cardElements) {
      const link = card.querySelector('a[role="link"], a[href*="facebook.com/"], a[href^="/"]');
      if (!link) continue;

      const href = (link.href || '').split('?')[0].split('&')[0];
      if (!href || badUrlPatterns.some(k => (link.href || '').includes(k))) continue;

      const rawText = (card.innerText || link.innerText || '').trim();
      if (!rawText) continue;

      const lines = rawText.split('\n').map(s => s.trim()).filter(Boolean);
      const name = lines[0] || '';
      if (name.length < 2 || isProtectedOwner(name, href) || genericExclusions.some(k => name.toLowerCase() === k || name.toLowerCase().startsWith(k))) continue;

      if (activeTab === 'friends') {
        const cardText = rawText.toLowerCase();
        if (cardText.includes('add friend') || cardText.includes('دوست شامل کریں') ||
            cardText.includes('friend request') || cardText.includes('درخواست بھیجی') ||
            cardText.includes('people you may know') || cardText.includes('آپ شاید جانتے ہیں')) {
          continue;
        }
      }

      if (!items.has(name)) {
        let avatar = '';
        const img = card.querySelector('img') || link.querySelector('img');
        if (img && img.src && !img.src.includes('data:image/svg')) {
          avatar = img.src;
        }

        let subText = '';
        const mutualMatch = rawText.match(/\d+\s+mutual friend[s]?/i) || rawText.match(/\d+\s+مشترکہ دوست/i);
        if (mutualMatch) subText = mutualMatch[0];

        items.set(name, {
          id: href || name,
          name: name,
          url: href,
          avatar: avatar,
          subText: subText,
          card: card,
          type: activeTab === 'friends' ? 'friend' : (activeTab === 'groups' ? 'group' : 'page'),
          selected: true
        });
      }
    }
  }

  function renderUI() {
    const list = document.getElementById('zhud-list');
    const query = document.getElementById('zhud-search').value.toLowerCase().trim();
    const all = Array.from(items.values());
    const filtered = all.filter(x => !query || x.name.toLowerCase().includes(query) || (x.url && x.url.toLowerCase().includes(query)));

    const removeCount = all.filter(x => x.selected).length;
    const keptCount = all.length - removeCount;

    document.getElementById('zhud-cnt-total').textContent = all.length;
    document.getElementById('zhud-cnt-remove').textContent = removeCount;
    document.getElementById('zhud-cnt-kept').textContent = keptCount;

    if (filtered.length === 0) {
      list.innerHTML = `
        <div style="text-align: center; padding: 40px 10px; color: #64748b; font-size: 13px;">
          ${query ? 'No matching items found for your filter.' : 'No items found. Click "⚡ Auto-Scroll (Max 500)" to scan!'}
        </div>
      `;
      return;
    }

    list.innerHTML = filtered.map((item) => {
      const avatarSrc = (item.avatar && typeof item.avatar === 'string' && item.avatar.startsWith('http'))
        ? item.avatar
        : 'https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif';

      return `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; border-radius: 12px; background: ${item.selected ? 'rgba(239,68,68,0.06)' : 'rgba(16,185,129,0.06)'}; border: 1px solid ${item.selected ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)'}; gap: 10px; min-width: 0;">
          <div style="display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; overflow: hidden;">
            <img src="${avatarSrc}" style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 1px solid rgba(255,255,255,0.15); flex-shrink: 0;" onerror="this.onerror=null;this.src='https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif';" />
            <div style="min-width: 0; flex: 1; overflow: hidden;">
              <div style="font-size: 13px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
              <div style="font-size: 11px; color: #94a3b8; display: flex; align-items: center; gap: 6px;">
                <span>${escapeHtml(item.subText || (activeTab === 'friends' ? 'Friend' : (activeTab === 'groups' ? 'Group' : 'Page')))}</span>
                <span>&bull;</span>
                <a href="${item.url || '#'}" target="_blank" style="color: #38bdf8; text-decoration: none;">View Profile</a>
              </div>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
            <span style="font-size: 10px; font-weight: 800; padding: 3px 7px; border-radius: 6px; background: ${item.selected ? '#ef4444' : '#10b981'}; color: #fff;">${item.selected ? 'REMOVE' : 'KEEP'}</span>
            <input type="checkbox" class="zhud-chk" data-name="${escapeHtml(item.name)}" ${item.selected ? 'checked' : ''} style="width: 18px; height: 18px; cursor: pointer; accent-color: #ef4444;" />
          </div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.zhud-chk').forEach(chk => {
      chk.onchange = (e) => {
        const n = e.target.getAttribute('data-name');
        const it = items.get(n);
        if (it) {
          it.selected = e.target.checked;
          renderUI();
        }
      };
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  document.getElementById('zhud-search').oninput = renderUI;

  document.getElementById('zhud-sel-all').onclick = () => {
    items.forEach(v => v.selected = true);
    renderUI();
  };
  document.getElementById('zhud-uncheck-all').onclick = () => {
    items.forEach(v => v.selected = false);
    renderUI();
  };
  document.getElementById('zhud-invert').onclick = () => {
    items.forEach(v => v.selected = !v.selected);
    renderUI();
  };

  /**
   * INTELLIGENT MAIN GRID SCROLLER (EXCLUDING LEFT NAVIGATION RAIL)
   */
  async function autoScrollTo(target = 500) {
    if (isScanning) return;
    isScanning = true;
    shouldStopScan = false;

    const btn = document.getElementById('zhud-btn-scan');
    const stopScanBtn = document.getElementById('zhud-btn-stop-scan');
    const status = document.getElementById('zhud-status');
    const fill = document.getElementById('zhud-scan-fill');

    btn.style.display = 'none';
    stopScanBtn.style.display = 'block';

    let noNewCount = 0;
    const maxLoops = 90;

    for (let loop = 0; loop < maxLoops; loop++) {
      if (shouldStopScan) {
        status.textContent = '⏹️ Scan paused by user.';
        break;
      }
      if (items.size >= target) {
        status.textContent = `🎯 Reached target limit of ${target} items!`;
        break;
      }

      status.textContent = `Scanning: Discovered ${items.size} / ${target} items...`;
      const pct = Math.min(100, Math.round((items.size / target) * 100));
      fill.style.width = `${pct}%`;

      // Scroll document and main container
      const mainArea = document.querySelector('div[role="main"]');
      if (mainArea) {
        try { mainArea.scrollBy({ top: 1200, behavior: 'smooth' }); } catch(e) {}
      }
      window.scrollBy({ top: 1200, behavior: 'smooth' });

      await new Promise(r => setTimeout(r, 500));

      const prevSize = items.size;
      scrapeAllVisibleCards();

      if (items.size !== prevSize) {
        noNewCount = 0;
        renderUI();
      } else {
        noNewCount++;
        if (noNewCount >= 6) {
          status.textContent = `✅ Full list reached: ${items.size} items loaded.`;
          break;
        }
      }
    }

    scrapeAllVisibleCards();
    renderUI();
    isScanning = false;
    btn.style.display = 'block';
    stopScanBtn.style.display = 'none';
    btn.textContent = `⚡ Auto-Scroll (Max 500)`;
    status.textContent = `✅ Complete: Loaded ${items.size} items!`;

    // Sync with local backend
    try {
      const payload = {};
      payload[activeTab] = Array.from(items.values());
      await fetch('http://127.0.0.1:8766/api/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch(e) {}
  }

  document.getElementById('zhud-btn-scan').onclick = () => autoScrollTo(500);
  document.getElementById('zhud-btn-stop-scan').onclick = () => {
    shouldStopScan = true;
    document.getElementById('zhud-status').textContent = 'Stopping scan...';
  };
  document.getElementById('zhud-load-more').onclick = () => {
    targetCount = items.size + 100;
    autoScrollTo(targetCount);
  };

  /**
   * SYNTHETIC 7-STAGE POINTER EVENT DISPATCHER (REACT 18 / RELAY RESILIENT)
   */
  function safeSimulatedClick(el) {
    if (!el) return false;
    try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(e) {}
    try { el.focus(); } catch(e) {}
    try {
      el.dispatchEvent(new PointerEvent('pointerover', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new PointerEvent('pointerenter', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, buttons: 1, view: window }));
      el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0, buttons: 1, view: window }));
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, buttons: 0, view: window }));
      el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, button: 0, view: window }));
      el.click();
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, view: window }));
      return true;
    } catch(e) {
      try { el.click(); return true; } catch(err) { return false; }
    }
  }

  function escapeModal() {
    try {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    } catch(e) {}
  }

  async function executeUnfriendFriend(name, url) {
    const mainArea = document.querySelector('div[role="main"]') || document.body;
    const allCards = Array.from(mainArea.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-suite-overlay'));
    let targetCard = allCards.find(c => {
      const txt = (c.innerText || '');
      return txt.includes(name) && !txt.toLowerCase().includes('people you may know') && !txt.toLowerCase().includes('suggestions') && !txt.toLowerCase().includes('آپ شاید جانتے ہیں');
    });

    if (!targetCard) {
      const searchInputs = Array.from(document.querySelectorAll('input[type="search"], input[placeholder*="Search"], input[placeholder*="تلاش"], input[aria-label*="Search"], input[aria-label*="تلاش"]')).filter(inp => !inp.closest('#zenith-suite-overlay'));
      const searchInput = searchInputs[0];
      if (searchInput) {
        try {
          searchInput.focus();
          searchInput.value = '';
          searchInput.dispatchEvent(new Event('input', { bubbles: true }));
          await new Promise(r => setTimeout(r, 250));

          searchInput.value = name;
          searchInput.dispatchEvent(new Event('input', { bubbles: true }));
          searchInput.dispatchEvent(new Event('change', { bubbles: true }));
          await new Promise(r => setTimeout(r, 1600));

          const freshCards = Array.from(document.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-suite-overlay'));
          targetCard = freshCards.find(c => (c.innerText || '').includes(name));
        } catch(e) {}
      }
    }

    if (!targetCard) return false;

    const cardText = (targetCard.innerText || '').toLowerCase();
    if (cardText.includes('add friend') || cardText.includes('دوست شامل کریں') || cardText.includes('friend request sent') || cardText.includes('درخواست بھیجی گئی')) {
      return true;
    }

    const cardButtons = Array.from(targetCard.querySelectorAll('div[role="button"], button')).filter(btn => !isForbiddenButton(btn));
    const actionBtn = cardButtons.find(btn => isFriendActionMenuButton(btn)) || targetCard.querySelector('div[aria-label*="Actions for"], div[aria-haspopup="menu"], div[role="button"][aria-label*="More"], div[role="button"][aria-label*="مزید"]');

    if (!actionBtn) return false;

    if (safeSimulatedClick(actionBtn)) {
      await new Promise(r => setTimeout(r, 1200));

      const menuItems = Array.from(document.querySelectorAll('div[role="menuitem"], div[role="button"], span'));
      const unfriendOpt = menuItems.find(el => {
        const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
        return t.includes('unfriend') || t.includes('remove friend') || t.includes('دوستی ختم') || t.includes('فرینڈ لسٹ سے ہٹائیں');
      });

      if (!unfriendOpt) {
        escapeModal();
        return false;
      }

      if (safeSimulatedClick(unfriendOpt)) {
        await new Promise(r => setTimeout(r, 1200));

        const dialogBtns = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"], div[role="dialog"] button, div[aria-label="Confirm"], div[aria-label="Unfriend"], div[aria-label="تصدیق"]'));
        const confirmBtn = dialogBtns.find(el => {
          const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
          const isCancel = t.includes('cancel') || t.includes('منسوخ');
          if (isCancel) return false;
          return t.includes('confirm') || t.includes('unfriend') || t.includes('remove') || t.includes('yes') || t.includes('تصدیق') || t.includes('ختم');
        });

        if (confirmBtn && safeSimulatedClick(confirmBtn)) {
          await new Promise(r => setTimeout(r, 1600));
          return true;
        } else {
          escapeModal();
        }
      } else {
        escapeModal();
      }
    }

    return false;
  }

  async function executeLeaveGroup(name, url) {
    const allCards = Array.from(document.querySelectorAll('div[role="listitem"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-suite-overlay'));
    const targetCard = allCards.find(c => (c.innerText || '').includes(name));

    if (targetCard) {
      const cardButtons = Array.from(targetCard.querySelectorAll('div[role="button"], button')).filter(btn => !isForbiddenButton(btn));
      const actionBtn = cardButtons.find(btn => {
        const t = (btn.innerText || btn.getAttribute('aria-label') || '').toLowerCase();
        return t.includes('joined') || t.includes('more') || t.includes('options') || t.includes('شامل ہیں') || t.includes('مزید') || btn.getAttribute('aria-haspopup') === 'menu';
      });

      if (actionBtn && safeSimulatedClick(actionBtn)) {
        await new Promise(r => setTimeout(r, 1200));

        const menuItems = Array.from(document.querySelectorAll('div[role="menuitem"], div[role="button"], span'));
        const leaveOpt = menuItems.find(el => {
          const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
          return t.includes('leave group') || t.includes('گروپ چھوڑیں') || t.includes('leave');
        });

        if (leaveOpt && safeSimulatedClick(leaveOpt)) {
          await new Promise(r => setTimeout(r, 1200));
          const dialogBtns = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"], div[role="dialog"] button, div[aria-label="Leave Group"], div[aria-label="Leave group"]'));
          const confirmBtn = dialogBtns.find(el => {
            const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
            return !t.includes('cancel') && (t.includes('leave') || t.includes('confirm') || t.includes('چھوڑیں') || t.includes('تصدیق'));
          }) || dialogBtns[dialogBtns.length - 1];

          if (confirmBtn && safeSimulatedClick(confirmBtn)) {
            await new Promise(r => setTimeout(r, 1600));
            return true;
          } else {
            escapeModal();
          }
        } else {
          escapeModal();
        }
      }
    }
    return false;
  }

  async function executeUnfollowPage(name, url) {
    const allCards = Array.from(document.querySelectorAll('div[role="listitem"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-suite-overlay'));
    const targetCard = allCards.find(c => (c.innerText || '').includes(name));

    if (targetCard) {
      const cardButtons = Array.from(targetCard.querySelectorAll('div[role="button"], button')).filter(btn => !isForbiddenButton(btn));
      const actionBtn = cardButtons.find(btn => {
        const t = (btn.innerText || btn.getAttribute('aria-label') || '').toLowerCase();
        return t.includes('following') || t.includes('liked') || t.includes('more') || t.includes('فالو کر رہے ہیں') || t.includes('پسند کیا') || btn.getAttribute('aria-haspopup') === 'menu';
      });

      if (actionBtn && safeSimulatedClick(actionBtn)) {
        await new Promise(r => setTimeout(r, 1200));

        const menuItems = Array.from(document.querySelectorAll('div[role="menuitem"], div[role="button"], span'));
        const unfollowOpt = menuItems.find(el => {
          const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
          return t.includes('unfollow') || t.includes('unlike') || t.includes('ان فالو') || t.includes('ان لائک');
        });

        if (unfollowOpt && safeSimulatedClick(unfollowOpt)) {
          await new Promise(r => setTimeout(r, 1500));
          return true;
        } else {
          escapeModal();
        }
      }
    }
    return false;
  }

  async function executeSingleItemRemoval(it) {
    const name = it.name || '';
    const url = it.url || '';

    if (isProtectedOwner(name, url)) {
      return true;
    }

    if (it.type === 'friend') {
      return await executeUnfriendFriend(name, url);
    } else if (it.type === 'group') {
      return await executeLeaveGroup(name, url);
    } else if (it.type === 'page') {
      return await executeUnfollowPage(name, url);
    }
    return false;
  }

  document.getElementById('zhud-btn-purge').onclick = async () => {
    const toRemove = Array.from(items.values()).filter(x => x.selected);
    if (!toRemove.length) return alert("No items checked for removal! Check the items you want to remove.");

    if (!confirm(`⚠️ ARE YOU SURE?\n\nYou are about to REMOVE ${toRemove.length} checked items directly from your Facebook account with safe 5–9s human stealth pacing.`)) return;

    isPurging = true;
    shouldStopPurge = false;

    const progWrap = document.getElementById('zhud-progress-wrap');
    const progText = document.getElementById('zhud-prog-text');
    const progPct = document.getElementById('zhud-prog-pct');
    const progFill = document.getElementById('zhud-prog-fill');
    const purgeBtn = document.getElementById('zhud-btn-purge');
    const stopBtn = document.getElementById('zhud-btn-stop');

    progWrap.style.display = 'flex';
    purgeBtn.style.display = 'none';
    stopBtn.style.display = 'block';

    let successCount = 0;
    for (let i = 0; i < toRemove.length; i++) {
      if (shouldStopPurge) break;
      const it = toRemove[i];
      const pct = Math.round(((i + 1) / toRemove.length) * 100);

      progText.textContent = `(${i + 1}/${toRemove.length}) Removing: ${it.name}...`;
      progPct.textContent = `${pct}%`;
      progFill.style.width = `${pct}%`;

      const success = await executeSingleItemRemoval(it);
      if (success) {
        successCount++;
        items.delete(it.name);
      }

      renderUI();

      // Stealth delay (5.0s – 9.0s)
      if (i < toRemove.length - 1 && !shouldStopPurge) {
        const delay = 5000 + Math.random() * 4000;
        progText.textContent = `Sleeping ${(delay/1000).toFixed(1)}s (anti-ban stealth)...`;
        await new Promise(r => setTimeout(r, delay));
      }

      // Anti-ban cooling break every 15 items
      if ((i + 1) % 15 === 0 && i < toRemove.length - 1 && !shouldStopPurge) {
        progText.textContent = `🛡️ Anti-ban cooling break (18s)...`;
        await new Promise(r => setTimeout(r, 18000));
      }
    }

    isPurging = false;
    purgeBtn.style.display = 'block';
    stopBtn.style.display = 'none';
    progText.textContent = shouldStopPurge ? 'Purge stopped by user.' : `🎉 Finished: Removed ${successCount}/${toRemove.length} items!`;
  };

  document.getElementById('zhud-btn-stop').onclick = () => {
    shouldStopPurge = true;
    document.getElementById('zhud-prog-text').textContent = 'Stopping after current item...';
  };

  // Initial Instant Scan & Auto-Scroll
  scrapeAllVisibleCards();
  renderUI();
  await autoScrollTo(500);
})();
