/**
 * Facebook Zenith In-Tab Cleaner - Zero-Setup Floating Triage & Purge Engine
 * Injects a floating 4K Glassmorphic Triage Overlay directly on https://www.facebook.com.
 * Multi-lingual (English & Urdu), Unicode NFD owner protected, with 5–9s stealth pacing.
 */

(function() {
  if (document.getElementById('zenith-in-tab-overlay')) {
    document.getElementById('zenith-in-tab-overlay').remove();
  }

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

  const overlay = document.createElement('div');
  overlay.id = 'zenith-in-tab-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    width: 480px;
    max-height: 90vh;
    background: rgba(10, 14, 23, 0.96);
    backdrop-filter: blur(22px);
    -webkit-backdrop-filter: blur(22px);
    border: 1.5px solid rgba(0, 242, 254, 0.4);
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.9), 0 0 30px rgba(0, 242, 254, 0.2);
    z-index: 9999999;
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: zenithFadeIn 0.3s ease-out;
  `;

  let items = [];
  let isRunning = false;

  overlay.innerHTML = `
    <style>
      @keyframes zenithFadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
      .zenith-header { padding: 16px 20px; background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; }
      .zenith-title { font-size: 15px; font-weight: 800; color: #fff; display: flex; align-items: center; gap: 8px; }
      .zenith-badge { font-size: 11px; background: linear-gradient(135deg, #00f2fe, #1877f2); color: #000; padding: 2px 8px; border-radius: 999px; font-weight: 700; }
      .zenith-close { background: transparent; border: none; color: #94a3b8; font-size: 18px; cursor: pointer; }
      .zenith-body { padding: 14px 18px; overflow-y: auto; max-height: 380px; display: flex; flex-direction: column; gap: 8px; }
      .zenith-item { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
      .zenith-item-info { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; overflow: hidden; }
      .zenith-avatar { width: 34px; height: 34px; border-radius: 50%; object-fit: cover; background: #334155; flex-shrink: 0; }
      .zenith-name { font-size: 13px; font-weight: 600; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .zenith-footer { padding: 14px 18px; background: rgba(0,0,0,0.4); border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; gap: 10px; }
      .zenith-btn { padding: 10px 18px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; transition: all 0.2s; }
      .zenith-btn-scan { background: rgba(255,255,255,0.08); color: #fff; }
      .zenith-btn-purge { background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; box-shadow: 0 4px 15px rgba(239,68,68,0.4); flex: 1; }
      .zenith-btn-purge:hover { transform: scale(1.02); }
      .zenith-checkbox { width: 18px; height: 18px; accent-color: #ef4444; cursor: pointer; flex-shrink: 0; }
    </style>

    <div class="zenith-header">
      <div class="zenith-title">
        <span>⚡ Facebook Zenith Triage</span>
        <span class="zenith-badge" id="z-count-badge">0 Items</span>
      </div>
      <button class="zenith-close" id="z-close-btn">&times;</button>
    </div>

    <div style="padding: 10px 18px; display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; border-bottom: 1px solid rgba(255,255,255,0.05);">
      <span id="z-summary-text">Ready to scan items on this page...</span>
      <div>
        <a href="javascript:void(0)" id="z-toggle-all" style="color: #38bdf8; text-decoration: none; font-weight: 600;">Select/Deselect All</a>
      </div>
    </div>

    <div class="zenith-body" id="z-items-container">
      <div style="text-align: center; padding: 30px 10px; color: #64748b;">
        <p>Click <strong>"Extract Current Items"</strong> to scan your friends/groups/pages on this page.</p>
      </div>
    </div>

    <div class="zenith-footer">
      <button class="zenith-btn zenith-btn-scan" id="z-scan-btn">Extract Items</button>
      <button class="zenith-btn zenith-btn-purge" id="z-purge-btn">Execute Removal (5–9s Stealth)</button>
    </div>
  `;

  document.body.appendChild(overlay);

  document.getElementById('z-close-btn').addEventListener('click', () => overlay.remove());

  const scanBtn = document.getElementById('z-scan-btn');
  const itemsContainer = document.getElementById('z-items-container');
  const countBadge = document.getElementById('z-count-badge');
  const summaryText = document.getElementById('z-summary-text');
  const toggleAll = document.getElementById('z-toggle-all');
  const purgeBtn = document.getElementById('z-purge-btn');

  function scanItems() {
    items = [];
    const map = new Set();
    const mainArea = document.querySelector('div[role="main"]') || document.body;
    const cards = Array.from(mainArea.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-in-tab-overlay'));

    for (const card of cards) {
      const link = card.querySelector('a[role="link"], a[href*="facebook.com/"], a[href^="/"]');
      if (!link) continue;

      const href = (link.href || '').split('?')[0].split('&')[0];
      const rawText = (card.innerText || link.innerText || '').trim();
      if (!rawText) continue;

      const cardLower = rawText.toLowerCase();
      if (cardLower.includes('add friend') || cardLower.includes('دوست شامل کریں') ||
          cardLower.includes('friend request') || cardLower.includes('people you may know') ||
          cardLower.includes('آپ شاید جانتے ہیں')) {
        continue;
      }

      const name = rawText.split('\n')[0].trim();
      if (name && name.length > 1 && !isProtectedOwner(name, href)) {
        if (!map.has(href)) {
          map.add(href);
          const img = card.querySelector('img') || link.querySelector('img');
          const avatar = (img && img.src && !img.src.includes('data:image/svg')) ? img.src : '';
          items.push({ id: href, name: name, url: href, avatar: avatar, selected: true });
        }
      }
    }

    renderItems();
  }

  function renderItems() {
    countBadge.textContent = `${items.length} Items`;
    const selectedCount = items.filter(x => x.selected).length;
    summaryText.textContent = `${selectedCount} of ${items.length} checked for removal`;

    if (items.length === 0) {
      itemsContainer.innerHTML = `<div style="text-align: center; padding: 30px; color: #64748b;">No items found. Scroll down on Facebook and click Extract Items again.</div>`;
      return;
    }

    itemsContainer.innerHTML = items.map((it, idx) => `
      <div class="zenith-item" id="z-item-${idx}">
        <div class="zenith-item-info">
          <img class="zenith-avatar" src="${it.avatar || 'https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif'}" onerror="this.onerror=null;this.src='https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif';" />
          <div class="zenith-name" title="${it.name}">${it.name}</div>
        </div>
        <input type="checkbox" class="zenith-checkbox" data-idx="${idx}" ${it.selected ? 'checked' : ''} />
      </div>
    `).join('');

    itemsContainer.querySelectorAll('.zenith-checkbox').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const idx = parseInt(e.target.getAttribute('data-idx'));
        items[idx].selected = e.target.checked;
        const sel = items.filter(x => x.selected).length;
        summaryText.textContent = `${sel} of ${items.length} checked for removal`;
      });
    });
  }

  scanBtn.addEventListener('click', scanItems);

  toggleAll.addEventListener('click', () => {
    const anyUnchecked = items.some(x => !x.selected);
    items.forEach(x => x.selected = anyUnchecked);
    renderItems();
  });

  async function executeSingleRemoval(it) {
    const name = it.name || '';
    const url = it.url || '';
    if (isProtectedOwner(name, url)) return true;

    const mainArea = document.querySelector('div[role="main"]') || document.body;
    const allCards = Array.from(mainArea.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-in-tab-overlay'));
    let card = allCards.find(c => (c.innerText || '').includes(name));

    if (!card) {
      const searchInputs = Array.from(document.querySelectorAll('input[type="search"], input[placeholder*="Search"], input[placeholder*="تلاش"]')).filter(inp => !inp.closest('#zenith-in-tab-overlay'));
      const searchInput = searchInputs[0];
      if (searchInput) {
        try {
          searchInput.focus();
          searchInput.value = name;
          searchInput.dispatchEvent(new Event('input', { bubbles: true }));
          await new Promise(r => setTimeout(r, 1400));
          const freshCards = Array.from(mainArea.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[class*="x1yztbdb"]')).filter(c => !c.closest('#zenith-in-tab-overlay'));
          card = freshCards.find(c => (c.innerText || '').includes(name));
        } catch(e) {}
      }
    }

    if (!card) return false;

    const cardText = (card.innerText || '').toLowerCase();
    if (cardText.includes('add friend') || cardText.includes('دوست شامل کریں')) {
      return true;
    }

    const cardButtons = Array.from(card.querySelectorAll('div[role="button"], button')).filter(btn => !isForbiddenButton(btn));
    const actionBtn = cardButtons.find(btn => isFriendActionMenuButton(btn)) || cardButtons.find(btn => btn.getAttribute('aria-haspopup') === 'menu');

    if (actionBtn && safeSimulatedClick(actionBtn)) {
      await new Promise(r => setTimeout(r, 1200));

      const menuItems = Array.from(document.querySelectorAll('div[role="menuitem"], div[role="button"], span'));
      const unfriendOpt = menuItems.find(el => {
        const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
        return t.includes('unfriend') || t.includes('leave group') || t.includes('unlike') || t.includes('unfollow') || t.includes('دوستی ختم') || t.includes('گروپ چھوڑیں') || t.includes('ان فالو');
      });

      if (unfriendOpt && safeSimulatedClick(unfriendOpt)) {
        await new Promise(r => setTimeout(r, 1200));

        const dialogBtns = Array.from(document.querySelectorAll('div[role="dialog"] div[role="button"], div[role="dialog"] button, div[aria-label="Confirm"], div[aria-label="Unfriend"], div[aria-label="تصدیق"]'));
        const confirmBtn = dialogBtns.find(el => {
          const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
          return !t.includes('cancel') && !t.includes('منسوخ') && (t.includes('confirm') || t.includes('unfriend') || t.includes('leave') || t.includes('remove') || t.includes('yes') || t.includes('تصدیق') || t.includes('ختم'));
        });

        if (confirmBtn && safeSimulatedClick(confirmBtn)) {
          await new Promise(r => setTimeout(r, 1500));
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

  purgeBtn.addEventListener('click', async () => {
    const toRemove = items.filter(x => x.selected);
    if (toRemove.length === 0) {
      alert("No items checked for removal.");
      return;
    }

    if (!confirm(`⚠️ ARE YOU SURE?\n\nYou are about to remove ${toRemove.length} items with Ultra-Safe 5–9s stealth delays.`)) {
      return;
    }

    isRunning = true;
    purgeBtn.disabled = true;
    scanBtn.disabled = true;

    for (let i = 0; i < toRemove.length; i++) {
      if (!isRunning) break;
      const item = toRemove[i];
      summaryText.textContent = `Removing (${i + 1}/${toRemove.length}): ${item.name}...`;

      try {
        await executeSingleRemoval(item);
      } catch (err) {
        console.error(err);
      }

      // Stealth Pacing (5.0s – 9.0s)
      if (i < toRemove.length - 1 && isRunning) {
        const sleep = 5000 + Math.random() * 4000;
        await new Promise(r => setTimeout(r, sleep));
      }

      // Cooling Break every 15 operations
      if ((i + 1) % 15 === 0 && i < toRemove.length - 1 && isRunning) {
        summaryText.textContent = `🛡️ Anti-ban cooling break (18s)...`;
        await new Promise(r => setTimeout(r, 18000));
      }
    }

    summaryText.textContent = `🎉 Purge completed! Cleaned ${toRemove.length} items.`;
    purgeBtn.disabled = false;
    scanBtn.disabled = false;
  });

  scanItems();
})();
