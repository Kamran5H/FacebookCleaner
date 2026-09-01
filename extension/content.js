/**
 * Facebook Zenith Triage - Universal Full-Grid 300+ Live Collector & Purge Suite (Extension Content Script)
 */

(async function() {
  const old = document.getElementById('zenith-suite-overlay');
  if (old) old.remove();

  const hud = document.createElement('div');
  hud.id = 'zenith-suite-overlay';
  hud.style.cssText = `
    position: fixed; top: 16px; right: 16px; width: 580px; max-height: 92vh;
    background: rgba(9, 13, 22, 0.98); color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    border: 1.5px solid rgba(0, 242, 254, 0.5); border-radius: 22px;
    box-shadow: 0 25px 80px rgba(0, 0, 0, 0.98), 0 0 50px rgba(0, 242, 254, 0.25);
    z-index: 99999999; display: flex; flex-direction: column; overflow: hidden;
    backdrop-filter: blur(28px); -webkit-backdrop-filter: blur(28px);
  `;

  let items = new Map();
  let isScanning = false;
  let isPurging = false;
  let shouldStopPurge = false;
  let targetCount = 300;

  const url = window.location.href;
  let activeTab = 'friends';
  if (url.includes('/groups')) activeTab = 'groups';
  else if (url.includes('/pages') || url.includes('category=liked')) activeTab = 'pages';

  hud.innerHTML = `
    <div style="padding: 16px 20px; background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <div id="zhud-live-dot" style="width: 12px; height: 12px; border-radius: 50%; background: #00f2fe; box-shadow: 0 0 12px #00f2fe;"></div>
        <div>
          <div style="font-size: 16px; font-weight: 900; background: linear-gradient(135deg, #00f2fe, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Facebook Zenith Triage</div>
          <div style="font-size: 11px; color: #94a3b8;">Live Full-Grid Scanner (300-Item Batch Review)</div>
        </div>
      </div>
      <div style="display: flex; gap: 8px;">
        <button id="zhud-minimize" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: #94a3b8; border-radius: 8px; width: 32px; height: 32px; cursor: pointer; font-size: 16px;">_</button>
        <button id="zhud-close" style="background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: #f87171; border-radius: 8px; width: 32px; height: 32px; cursor: pointer; font-size: 18px;">&times;</button>
      </div>
    </div>

    <div style="padding: 10px 16px; background: rgba(0,0,0,0.35); display: flex; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06);">
      <button id="zhud-tab-friends" style="flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; background: ${activeTab === 'friends' ? 'linear-gradient(135deg, #00f2fe, #1877f2)' : 'rgba(255,255,255,0.05)'}; color: #fff;">👥 Friends Grid</button>
      <button id="zhud-tab-groups" style="flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; background: ${activeTab === 'groups' ? 'linear-gradient(135deg, #00f2fe, #1877f2)' : 'rgba(255,255,255,0.05)'}; color: #fff;">👥 Joined Groups</button>
      <button id="zhud-tab-pages" style="flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 700; border: none; cursor: pointer; background: ${activeTab === 'pages' ? 'linear-gradient(135deg, #00f2fe, #1877f2)' : 'rgba(255,255,255,0.05)'}; color: #fff;">📄 Liked Pages</button>
    </div>

    <div style="padding: 12px 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; background: rgba(0,0,0,0.25);">
      <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(0,242,254,0.25); border-radius: 12px; padding: 10px; text-align: center;">
        <div style="font-size: 10px; color: #94a3b8; text-transform: uppercase; font-weight: 700;">Live Discovered</div>
        <div id="zhud-cnt-total" style="font-size: 22px; font-weight: 900; color: #00f2fe;">0</div>
      </div>
      <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 12px; padding: 10px; text-align: center;">
        <div style="font-size: 10px; color: #fca5a5; text-transform: uppercase; font-weight: 700;">Slated to Remove</div>
        <div id="zhud-cnt-remove" style="font-size: 22px; font-weight: 900; color: #ef4444;">0</div>
      </div>
      <div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: 12px; padding: 10px; text-align: center;">
        <div style="font-size: 10px; color: #6ee7b7; text-transform: uppercase; font-weight: 700;">Kept (Unchecked)</div>
        <div id="zhud-cnt-kept" style="font-size: 22px; font-weight: 900; color: #10b981;">0</div>
      </div>
    </div>

    <div id="zhud-scan-bar" style="height: 4px; background: rgba(255,255,255,0.05); width: 100%; overflow: hidden;">
      <div id="zhud-scan-fill" style="height: 100%; width: 0%; background: linear-gradient(90deg, #00f2fe, #6366f1); transition: width 0.2s;"></div>
    </div>

    <div style="padding: 12px 16px; background: rgba(0,0,0,0.4); border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 8px;">
      <div style="display: flex; gap: 8px;">
        <input id="zhud-search" type="text" placeholder="🔍 Filter by name to uncheck & keep..." style="flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 9px 14px; color: #fff; font-size: 13px; outline: none;" />
        <button id="zhud-btn-scan" style="padding: 9px 16px; border-radius: 10px; font-size: 12px; font-weight: 800; background: linear-gradient(135deg, #0ea5e9, #0284c7); color: #fff; border: none; cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 4px 15px rgba(14,165,233,0.4);">
          ⚡ Auto-Scroll to 300+
        </button>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px;">
        <div style="display: flex; gap: 10px;">
          <a href="javascript:void(0)" id="zhud-sel-all" style="color: #38bdf8; text-decoration: none; font-weight: 700;">Select All (Remove)</a>
          <span style="color: #475569;">|</span>
          <a href="javascript:void(0)" id="zhud-uncheck-all" style="color: #34d399; text-decoration: none; font-weight: 700;">Uncheck All (Keep All)</a>
          <span style="color: #475569;">|</span>
          <a href="javascript:void(0)" id="zhud-invert" style="color: #cbd5e1; text-decoration: none;">Invert</a>
        </div>
        <span id="zhud-status" style="color: #38bdf8; font-weight: 600;">Live listener active • Scroll page to load</span>
      </div>
    </div>

    <div id="zhud-list" style="padding: 12px 16px; overflow-y: auto; max-height: 330px; display: flex; flex-direction: column; gap: 8px; background: rgba(0,0,0,0.2);">
      <div style="text-align: center; padding: 40px 10px; color: #64748b; font-size: 13px;">
        Scanning active Facebook tab... Scroll down or click <strong>"⚡ Auto-Scroll to 300+"</strong>!
      </div>
    </div>

    <div style="padding: 14px 18px; background: rgba(0,0,0,0.65); border-top: 1px solid rgba(255,255,255,0.08); display: flex; flex-direction: column; gap: 10px;">
      <div id="zhud-progress-wrap" style="display: none; flex-direction: column; gap: 4px;">
        <div style="display: flex; justify-content: space-between; font-size: 11px;">
          <span id="zhud-prog-text" style="color: #00f2fe; font-weight: 700;">Unfriending item 0/0...</span>
          <span id="zhud-prog-pct" style="color: #f87171; font-weight: 800;">0%</span>
        </div>
        <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 999px; overflow: hidden;">
          <div id="zhud-prog-fill" style="height: 100%; width: 0%; background: linear-gradient(90deg, #ef4444, #f43f5e); transition: width 0.3s;"></div>
        </div>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
        <button id="zhud-load-more" style="padding: 11px 16px; border-radius: 10px; font-size: 12px; font-weight: 700; background: rgba(255,255,255,0.06); color: #fff; border: 1px solid rgba(255,255,255,0.15); cursor: pointer;">+100 More</button>
        <button id="zhud-btn-purge" style="flex: 1; padding: 12px 20px; border-radius: 12px; font-size: 13px; font-weight: 900; background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; cursor: pointer; box-shadow: 0 4px 25px rgba(239, 68, 68, 0.6); display: flex; justify-content: center; align-items: center; gap: 8px;">
          🔥 Execute Ultra-Safe Removal (5-8s Stealth)
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
    hud.style.width = isMin ? '260px' : '580px';
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

  /**
   * STRICT BUTTON & CARD SAFETY GUARDS
   * Ensures the engine NEVER clicks 'Add friend', 'Message', or sends requests to strangers.
   */
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
      'دوست', 'مزید', 'اختیارات', 'دوستی'
    ];

    if (goodKeywords.some(w => aria.includes(w))) return true;
    if (txt === 'friends' || txt === 'دوست' || txt === 'more' || txt === 'مزید') return true;
    if (hasPopup && !isForbiddenButton(el)) return true;

    return false;
  }

  function scrapeAllVisibleCards() {
    const genericExclusions = [
      'home', 'friends', 'watch', 'marketplace', 'groups', 'gaming', 'menu', 'facebook',
      'custom lists', 'birthdays', 'friend requests', 'suggestions', 'all friends',
      'photos', 'videos', 'about', 'terms', 'privacy policy', 'privacy center', 'reels',
      'posts', 'more', 'manage', 'search', 'edit profile', 'add to story', 'see all',
      'dashboard', 'professional dashboard', 'following', 'followers', 'events', 'saved'
    ];

    const badUrlPatterns = [
      '/notifications', '/login_alerts', '/posts/', '/following', '/followers',
      '/professional_dashboard', '/events', '/saved', '/help/', '/policies/',
      '/friends/', '/friends_recent', '/friends_college', '/friends_current_city',
      '/friends_mutual', '/friends_with_upcoming_birthdays', '/friends_all',
      'category=', 'l.php'
    ];

    const links = Array.from(document.querySelectorAll('a[role="link"], a[href*="facebook.com/"], a[href^="/"]'));

    for (const l of links) {
      const href = (l.href || '').split('?')[0].split('&')[0];
      if (!href) continue;

      if (badUrlPatterns.some(k => (l.href || '').includes(k))) continue;

      const rawText = (l.innerText || '').trim();
      if (!rawText || rawText.includes('mutual friend') || rawText.includes('followers') || rawText.includes('Unread') || rawText.includes('highlighted a post')) continue;

      const name = rawText.split('\n')[0].trim();
      if (name.length < 2 || genericExclusions.some(k => name.toLowerCase() === k || name.toLowerCase().startsWith(k))) continue;

      const isValidTarget = href.includes('profile.php') || href.includes('/groups/') || (href.includes('facebook.com/') && !href.includes('/messages/'));
      if (!isValidTarget) continue;

      let card = l.closest('div[role="listitem"]') || l.closest('div[class*="x1yztbdb"]') || l.closest('div[class*="x9f619"]') || l.parentElement;
      for (let i = 0; i < 4; i++) {
        if (card && card.parentElement && card.querySelector('div[aria-label="More"], div[aria-haspopup="menu"], div[role="button"][aria-label*="Friend"], div[role="button"][aria-label*="Manage"], div[role="button"][aria-label*="مزید"], div[role="button"][aria-label*="دوست"]')) {
          break;
        }
        if (card && card.parentElement) card = card.parentElement;
      }

      if (activeTab === 'friends' && card) {
        const cardText = (card.innerText || '').toLowerCase();
        if (cardText.includes('add friend') || cardText.includes('دوست شامل کریں') || cardText.includes('friend request') || cardText.includes('درخواست') || cardText.includes('people you may know') || cardText.includes('آپ شاید جانتے ہیں')) {
          continue;
        }

        const addBtn = card.querySelector('div[aria-label*="Add friend"], div[aria-label*="دوست شامل کریں"], div[aria-label*="Add Friend"]');
        if (addBtn) continue;
      }

      if (!items.has(name)) {
        let avatar = '';
        const img = l.querySelector('img') || (l.parentElement ? l.parentElement.querySelector('img') : null);
        if (img && img.src && !img.src.includes('data:image/svg')) {
          avatar = img.src;
        }

        const cardButtons = card ? Array.from(card.querySelectorAll('div[role="button"], button')).filter(btn => !isForbiddenButton(btn)) : [];
        const moreBtn = cardButtons.find(btn => isFriendActionMenuButton(btn)) || (card ? card.querySelector('div[aria-haspopup="menu"]') : null);

        let subText = '';
        if (card) {
          const mutualMatch = (card.innerText || '').match(/\d+\s+mutual friend[s]?/i);
          if (mutualMatch) subText = mutualMatch[0];
        }

        items.set(name, {
          id: href || name,
          name: name,
          url: href,
          avatar: avatar,
          subText: subText,
          button: moreBtn,
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
    const filtered = all.filter(x => !query || x.name.toLowerCase().includes(query));

    const removeCount = all.filter(x => x.selected).length;
    const keptCount = all.length - removeCount;

    document.getElementById('zhud-cnt-total').textContent = all.length;
    document.getElementById('zhud-cnt-remove').textContent = removeCount;
    document.getElementById('zhud-cnt-kept').textContent = keptCount;

    const pct = Math.min(100, Math.round((all.length / targetCount) * 100));
    document.getElementById('zhud-scan-fill').style.width = `${pct}%`;

    if (filtered.length === 0) {
      list.innerHTML = `
        <div style="text-align: center; padding: 40px 10px; color: #64748b; font-size: 13px;">
          ${query ? 'No matching items found for your filter.' : 'No items found. Click "⚡ Auto-Scroll to 300+" to scan!'}
        </div>
      `;
      return;
    }

    list.innerHTML = filtered.map((item, idx) => {
      const avatarSrc = (item.avatar && typeof item.avatar === 'string' && item.avatar.startsWith('http'))
        ? item.avatar
        : 'https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif';

      return `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; border-radius: 12px; background: ${item.selected ? 'rgba(239,68,68,0.06)' : 'rgba(16,185,129,0.06)'}; border: 1px solid ${item.selected ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)'}; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0;">
            <img src="${avatarSrc}" style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 1px solid rgba(255,255,255,0.15);" onerror="this.onerror=null;this.src='https://static.xx.fbcdn.net/rsrc.php/v3/yo/r/UlIqmHJn-SK.gif';" />
            <div style="min-width: 0;">
              <div style="font-size: 13px; font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(item.name)}</div>
              <div style="font-size: 11px; color: #94a3b8; display: flex; align-items: center; gap: 6px;">
                <span>${escapeHtml(item.subText || (activeTab === 'friends' ? 'Friend' : (activeTab === 'groups' ? 'Group' : 'Page')))}</span>
                <span>&bull;</span>
                <a href="${item.url || '#'}" target="_blank" style="color: #38bdf8; text-decoration: none;">View</a>
              </div>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
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

  window.addEventListener('scroll', () => {
    scrapeAllVisibleCards();
    renderUI();
  }, { passive: true });

  async function autoScrollTo(target) {
    if (isScanning) return;
    isScanning = true;

    const btn = document.getElementById('zhud-btn-scan');
    const status = document.getElementById('zhud-status');
    const fill = document.getElementById('zhud-scan-fill');

    btn.textContent = '⏳ Scrolling...';
    btn.style.background = '#475569';

    let noNewCount = 0;
    const maxLoops = 120;

    for (let loop = 0; loop < maxLoops; loop++) {
      if (items.size >= target) break;

      status.textContent = `Scanning... Discovered ${items.size} / ${target}`;
      const pct = Math.min(100, Math.round((items.size / target) * 100));
      fill.style.width = `${pct}%`;

      window.scrollBy({ top: 1200, behavior: 'smooth' });
      await new Promise(r => setTimeout(r, 450));

      const prevSize = items.size;
      scrapeAllVisibleCards();

      if (items.size === prevSize) {
        noNewCount++;
        if (noNewCount > 35) break;
      } else {
        noNewCount = 0;
      }
    }

    scrapeAllVisibleCards();
    renderUI();
    isScanning = false;
    btn.textContent = '⚡ Auto-Scroll to 300+';
    btn.style.background = 'linear-gradient(135deg, #0ea5e9, #0284c7)';
    status.textContent = `✅ Complete: Loaded ${items.size} items!`;

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

  document.getElementById('zhud-btn-scan').onclick = () => autoScrollTo(300);
  document.getElementById('zhud-load-more').onclick = () => {
    targetCount = items.size + 100;
    autoScrollTo(targetCount);
  };

  function safeSimulatedClick(el) {
    if (!el) return false;
    try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(e) {}
    try { el.focus(); } catch(e) {}
    try {
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
      el.click();
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
      return true;
    } catch(e) {
      try { el.click(); return true; } catch(err) { return false; }
    }
  }

  async function executeUnfriendFriend(name, url) {
    const allCards = Array.from(document.querySelectorAll('div[role="listitem"], div[class*="x1yztbdb"], div[class*="x9f619"]')).filter(c => !c.closest('#zenith-suite-overlay'));
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
          await new Promise(r => setTimeout(r, 200));

          searchInput.value = name;
          searchInput.dispatchEvent(new Event('input', { bubbles: true }));
          searchInput.dispatchEvent(new Event('change', { bubbles: true }));
          await new Promise(r => setTimeout(r, 1500));

          const freshCards = Array.from(document.querySelectorAll('div[role="listitem"], div[class*="x1yztbdb"], div[class*="x9f619"]')).filter(c => !c.closest('#zenith-suite-overlay'));
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
    const actionBtn = cardButtons.find(btn => isFriendActionMenuButton(btn)) || cardButtons.find(btn => btn.getAttribute('aria-haspopup') === 'menu');

    if (!actionBtn) return false;

    if (safeSimulatedClick(actionBtn)) {
      await new Promise(r => setTimeout(r, 1200));

      const menuItems = Array.from(document.querySelectorAll('div[role="menuitem"], div[role="button"], span'));
      const unfriendOpt = menuItems.find(el => {
        const t = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase();
        return t.includes('unfriend') || t.includes('remove friend') || t.includes('دوستی ختم') || t.includes('فرینڈ لسٹ سے ہٹائیں');
      });

      if (!unfriendOpt) {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
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
          await new Promise(r => setTimeout(r, 1500));
          return true;
        }
      }
    }

    return false;
  }

  async function executeLeaveGroup(name, url) {
    const allCards = Array.from(document.querySelectorAll('div[role="listitem"], div[class*="x1yztbdb"], div[class*="x9f619"]')).filter(c => !c.closest('#zenith-suite-overlay'));
    const targetCard = allCards.find(c => (c.innerText || '').includes(name));

    if (targetCard) {
      const cardText = (targetCard.innerText || '').toLowerCase();
      if (cardText.includes('join group') || cardText.includes('گروپ میں شامل ہوں')) {
        return true;
      }

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
            await new Promise(r => setTimeout(r, 1500));
            return true;
          }
        }
      }
    }
    return false;
  }

  async function executeUnfollowPage(name, url) {
    const allCards = Array.from(document.querySelectorAll('div[role="listitem"], div[class*="x1yztbdb"], div[class*="x9f619"]')).filter(c => !c.closest('#zenith-suite-overlay'));
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
        }
      }
    }
    return false;
  }

  async function executeSingleItemRemoval(it) {
    const name = it.name || '';
    const url = it.url || '';

    // Never remove your own account: set your name / profile-handle stems here.
    const PROTECTED_STEMS = ['your_name', 'your_username'];
    if (PROTECTED_STEMS.some(s => name.toLowerCase().includes(s) || url.includes(s))) {
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

  /**
   * DIRECT IN-CARD PURGE EXECUTION (STEALTH 5-8s)
   */
  document.getElementById('zhud-btn-purge').onclick = async () => {
    const toRemove = Array.from(items.values()).filter(x => x.selected);
    if (!toRemove.length) return alert("No items checked for removal! Check the items you want to remove.");

    if (!confirm(`⚠️ ARE YOU SURE?\n\nYou are about to REMOVE ${toRemove.length} checked items directly from your Facebook account with safe 5-8s human stealth pacing.`)) return;

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

      if (i < toRemove.length - 1 && !shouldStopPurge) {
        const delay = 5000 + Math.random() * 3000;
        progText.textContent = `Sleeping ${(delay/1000).toFixed(1)}s (anti-ban stealth)...`;
        await new Promise(r => setTimeout(r, delay));
      }

      if ((i + 1) % 15 === 0 && i < toRemove.length - 1 && !shouldStopPurge) {
        progText.textContent = `🛡️ Anti-ban cooling break (15s)...`;
        await new Promise(r => setTimeout(r, 15000));
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

  scrapeAllVisibleCards();
  renderUI();
  await autoScrollTo(300);
})();
