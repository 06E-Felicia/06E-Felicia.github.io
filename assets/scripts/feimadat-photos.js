/* Public, registration-only reference photos. Never a VariFlight/MCP request. */
(() => {
  'use strict';
  const STORAGE = 'feimadat-photos-v2', DAY = 86400000;
  const inflight = new Map(), attempted = new Map(), queue = [];
  let running = 0, cache = {}, blocked = false;
  const validReg = value => /^[A-Z0-9][A-Z0-9-]{2,13}$/.test(value || '');
  const safeURL = (value, image) => {
    try {
      const u = new URL(value);
      const hosts = image ? ['t.plnspttrs.net','cdn.planespotters.net'] : ['www.planespotters.net','planespotters.net'];
      return u.protocol === 'https:' && hosts.includes(u.hostname) && !u.username && !u.password
        && (!u.port || u.port === '443') && !u.hash && (image || u.pathname.startsWith('/photo/')) ? u.href : '';
    } catch { return ''; }
  };
  const verified = (photo, reg) => photo && photo.reg === reg && safeURL(photo.src,true)
    && safeURL(photo.link,false) && typeof photo.photographer === 'string' && photo.photographer.trim();
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE) || '{}');
    for (const [reg,entry] of Object.entries(saved)) {
      if (validReg(reg) && Number.isFinite(entry?.at) && Date.now()-entry.at >= 0
          && Date.now()-entry.at < (entry.photo ? 30 : 7)*DAY
          && (entry.photo === null || verified(entry.photo,reg))) cache[reg] = entry;
    }
  } catch { /* Private mode and a full storage quota must not break the board. */ }
  const save = () => {
    try {
      const entries = Object.entries(cache).sort((a,b)=>b[1].at-a[1].at).slice(0,1000);
      cache = Object.fromEntries(entries); localStorage.setItem(STORAGE,JSON.stringify(cache));
    } catch { /* An in-memory cache remains available. */ }
  };
  async function pump() {
    while (running < 3 && queue.length) {
      const {reg,resolve} = queue.shift(); running++;
      (async () => {
        let photo = null;
        if (blocked) { running--; attempted.set(reg,null); inflight.delete(reg); resolve(null); pump(); return; }
        const controller = new AbortController(), timer = setTimeout(()=>controller.abort(),12000);
        try {
          const response = await fetch('https://api.planespotters.net/pub/photos/reg/'+encodeURIComponent(reg), {
            credentials:'omit',referrerPolicy:'no-referrer',signal:controller.signal
          });
          if (response.status === 403 || response.status === 429) blocked = true;
          if (!response.ok) throw new Error('Photo unavailable');
          const data = await response.json();
          if (!Array.isArray(data.photos)) throw new Error('Invalid photo response');
          for (const p of data.photos) {
            const src = safeURL((p.thumbnail_large || p.thumbnail || {}).src,true), link = safeURL(p.link,false);
            const author = typeof p.photographer === 'string' ? p.photographer.trim().slice(0,150) : '';
            if (src && link && author && (!p.reg || p.reg.toUpperCase().replace(/^B([A-Z0-9]{4})$/,'B-$1') === reg)) {
              photo = {src,link,photographer:author,reg,source:'planespotters',
                provider:'PlaneSpotters.net · 同注册号资料照片（非本航班实拍）'};
              break;
            }
          }
          // Only a valid response is negative-cached; network errors are not "no photo".
          if (photo || !data.photos.length) { cache[reg] = {at:Date.now(),photo}; save(); }
        } catch { /* Keep failures out of the flight board; do not retry this session. */ }
        finally { clearTimeout(timer); }
        attempted.set(reg,photo); inflight.delete(reg); running--; resolve(photo); pump();
      })();
    }
  }
  function getPhoto(reg) {
    if (!validReg(reg)) return Promise.resolve(null);
    const entry = cache[reg];
    if (entry && Date.now()-entry.at < (entry.photo ? 30 : 7)*DAY) return Promise.resolve(entry.photo);
    if (attempted.has(reg)) return Promise.resolve(attempted.get(reg));
    if (!inflight.has(reg)) {
      const promise = new Promise(resolve=>queue.push({reg,resolve}));
      inflight.set(reg,promise); pump();
    }
    return inflight.get(reg);
  }
  function paint(node, photo) {
    if (!node.isConnected) return;
    if (!photo) { node.textContent = '暂无资料照片'; return; }
    const detail = node.classList.contains('detail-no-photo');
    const container = document.createElement(detail ? 'figure' : 'a');
    container.className = detail ? 'detail-photo' : 'photo-thumb';
    const image = document.createElement('img');
    image.src = photo.src; image.alt = photo.reg+' 同注册号资料照片'; image.referrerPolicy = 'no-referrer';
    image.decoding = 'async'; container.append(image);
    const credit = document.createElement(detail ? 'figcaption' : 'span');
    credit.className = detail ? '' : 'credit';
    credit.textContent = '© '+photo.photographer+' · '+photo.provider;
    if (detail) {
      const link = document.createElement('a'); link.href = photo.link; link.target = '_blank';
      link.rel = 'noopener'; link.textContent = ' 照片来源 ↗'; credit.append(link);
    } else { container.href = photo.link; container.target = '_blank'; container.rel = 'noopener'; }
    container.title = credit.textContent; container.append(credit); node.replaceWith(container);
  }
  async function load(node) {
    if (node.dataset.photoLoading) return;
    node.dataset.photoLoading = '1';
    paint(node,await getPhoto(node.dataset.photoReg));
  }
  const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries=>{
    for (const e of entries) if (e.isIntersecting) { observer.unobserve(e.target); load(e.target); }
  },{rootMargin:'250px'}) : null;
  window.FeimadatPhotos = {observe(root) {
    // Disconnect old list nodes after sorting/filtering to avoid retaining full lists.
    if (root.id === 'list') observer?.disconnect();
    root.querySelectorAll('[data-photo-reg]').forEach(node=>{
      if (node.closest('dialog') || !observer) load(node); else observer.observe(node);
    });
  }};
})();
