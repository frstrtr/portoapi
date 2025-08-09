(function(){
  const tg = window.Telegram?.WebApp;
  if (tg) tg.expand();

  const apiBase = `${location.origin}/api/v1`;
  const listEl = document.getElementById('list');
  const refreshBtn = document.getElementById('refreshBtn');
  const toAddrEl = document.getElementById('toAddr');
  const details = document.getElementById('details');
  const pending = document.getElementById('pending');
  const detailsContent = document.getElementById('detailsContent');
  const backBtn = document.getElementById('backBtn');
  const prepareBtn = document.getElementById('prepareBtn');
  const submitBtn = document.getElementById('submitBtn');
  const signedHexEl = document.getElementById('signedHex');

  let state = { sellerId: null, selected: null, rawTx: null, initData: null, token: null };

  function showToast(text){
    if (tg) tg.showPopup({title: 'Info', message: String(text), buttons:[{type:'ok'}]});
    else alert(text);
  }

  function tgData(){
    // Prefer Telegram-provided initData; fall back to URL params
    const params = new URLSearchParams(location.search);
    const sid = params.get('seller_id');
    if (sid) state.sellerId = sid;
    const urlInit = params.get('initData');
    if (tg && tg.initData) state.initData = tg.initData; else if (urlInit) state.initData = urlInit;
    // Extra fallback: use initDataUnsafe.user.id as sellerId inside Telegram
    const unsafeId = tg?.initDataUnsafe?.user?.id;
    if (!state.sellerId && unsafeId) state.sellerId = String(unsafeId);
  }

  async function ensureAuth(){
    if (state.token) return; // already authenticated
    // Refresh initData from Telegram context if available
    if (!state.initData && tg && tg.initData) state.initData = tg.initData;
    if (!state.initData) return; // no initData available (likely plain browser dev mode)
    try{
      const res = await fetch(`${apiBase}/withdrawals/auth`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({initData: state.initData})
      });
      if (!res.ok) {
        const txt = await res.text().catch(()=> '');
        throw new Error(`Auth ${res.status}: ${txt || res.statusText}`);
      }
      const data = await res.json();
      state.token = data.token;
    }catch(e){
      console.warn('Auth failed', e);
      // Don't block UI; will fall back to seller_id path
    }
  }

  function authHeaders(){
    return state.token ? { 'Authorization': `Bearer ${state.token}` } : {};
  }

  async function fetchPending(){
    listEl.innerHTML = '<li>Loading…</li>';
    try{
      await ensureAuth();
      let url = `${apiBase}/withdrawals/pending`;
      const headers = authHeaders();
      if (!state.token){
        // Dev/Telegram fallback via query params
        const qs = new URLSearchParams();
        if (state.sellerId) qs.set('seller_id', state.sellerId);
        const urlInit = state.initData || (tg && tg.initData) || null;
        if (urlInit) qs.set('initData', urlInit);
        if ([...qs.keys()].length) url += `?${qs.toString()}`;
      }
      let res = await fetch(url, { headers });
      if (!res.ok) {
        const txt = await res.text().catch(()=> '');
        throw new Error(`Pending ${res.status}: ${txt || res.statusText}`);
      }
      const data = await res.json();
      renderList((data && data.items) ? data.items : []);
    }catch(e){
      const hint = (!state.token && !state.sellerId) ? ' Open via the bot button or append ?seller_id=YOUR_ID for dev.' : '';
      listEl.innerHTML = `<li>Error: ${(e.message||e)}${hint}</li>`;
    }
  }

  function renderList(items){
    if (!items.length){
      listEl.innerHTML = '<li>No pending withdrawals</li>';
      return;
    }
    listEl.innerHTML = '';
    items.forEach(item => {
      const li = document.createElement('li');
      li.innerHTML = `
        <div><b>Invoice #${item.invoice_id}</b></div>
        <div>From: <code>${item.from_address}</code></div>
        <div>Amount: ${item.amount_usdt.toFixed(6)} USDT</div>
        <button data-id="${item.invoice_id}">Sign</button>
      `;
      li.querySelector('button').addEventListener('click', () => selectItem(item));
      listEl.appendChild(li);
    });
  }

  function selectItem(item){
    state.selected = item;
    pending.classList.add('hidden');
    details.classList.remove('hidden');
    detailsContent.innerHTML = `
      <div><b>Invoice #${item.invoice_id}</b></div>
      <div>From: <code>${item.from_address}</code></div>
      <div>To: <code>${toAddrEl.value || '(enter above)'} </code></div>
      <div>Amount: ${item.amount_usdt.toFixed(6)} USDT</div>
    `;
    submitBtn.disabled = true;
    signedHexEl.value = '';
  }

  backBtn.addEventListener('click', () => {
    state.selected = null; state.rawTx = null;
    pending.classList.remove('hidden');
    details.classList.add('hidden');
  });

  prepareBtn.addEventListener('click', async () => {
    const to = toAddrEl.value.trim();
    if (!to || to[0] !== 'T') { showToast('Enter destination TRON address'); return; }
    if (!state.selected) { showToast('Select an invoice'); return; }
    try{
      await ensureAuth();
      const res = await fetch(`${apiBase}/withdrawals/prepare`, {
        method: 'POST', headers: Object.assign({'Content-Type':'application/json'}, authHeaders()),
        body: JSON.stringify({invoice_id: state.selected.invoice_id, to_address: to})
      });
      if (!res.ok) {
        const txt = await res.text().catch(()=> '');
        throw new Error(`Prepare ${res.status}: ${txt || res.statusText}`);
      }
      const data = await res.json();
      state.rawTx = data.raw_tx;
      showToast('TX prepared. Sign with your wallet and paste signed hex below.');
      submitBtn.disabled = false;
    }catch(e){ showToast('Prepare failed: '+(e.message||e)); }
  });

  submitBtn.addEventListener('click', async () => {
    const hex = signedHexEl.value.trim();
    if (!hex) { showToast('Paste signed hex first'); return; }
    try{
      await ensureAuth();
      const res = await fetch(`${apiBase}/withdrawals/submit`, {
        method: 'POST', headers: Object.assign({'Content-Type':'application/json'}, authHeaders()),
        body: JSON.stringify({invoice_id: state.selected.invoice_id, signed_tx_hex: hex})
      });
      const data = await res.json();
      if (data.result){
        showToast('Broadcasted: '+(data.txid||''));
        backBtn.click();
        await fetchPending();
      } else {
        showToast('Error: '+(data.error||'unknown'));
      }
    }catch(e){ showToast('Submit failed: '+(e.message||e)); }
  });

  refreshBtn.addEventListener('click', fetchPending);

  tgData();
  fetchPending();
})();
