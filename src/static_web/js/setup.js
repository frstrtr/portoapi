// JS для генерации seed/xPub на стороне клиента

let mnemonic = '';
let token = '';

window.onload = function() {
    // Извлечь token из URL
    const params = new URLSearchParams(window.location.search);
    token = params.get('token') || '';
    if (!token) {
        alert('Token не найден в URL!');
        document.body.innerHTML = '<h2>Ошибка: отсутствует token</h2>';
        return;
    }
    // UI для buyer_id и account (invoices_group)
    const container = document.createElement('div');
    container.innerHTML = `
      <h2>Ваша seed-фраза</h2>
      <div id="seedBox" style="font-size:1.2em; background:#f4f4f4; padding:1em; margin-bottom:1em;"></div>
      <input id="buyer_id" type="text" placeholder="Buyer ID (например, email или username)" style="width:70%;margin-bottom:0.5em;" />
      <input id="account" type="number" min="0" value="0" placeholder="Account (по умолчанию 0)" style="width:28%;margin-bottom:0.5em;float:right;" />
      <div style="clear:both;"></div>
      <label><input type="checkbox" id="confirmSave" /> Я сохранил свою фразу</label><br>
      <button id="continueBtn" disabled>Продолжить</button>
      <div id="statusMsg" style="margin-top:1em;"></div>
    `;
    document.body.appendChild(container);
    generateSeed();
    document.getElementById('confirmSave').addEventListener('change', function() {
        document.getElementById('continueBtn').disabled = !this.checked;
    });
    document.getElementById('continueBtn').onclick = completeRegistration;
}

function generateSeed() {
    // Используем bip39 для генерации seed-фразы
    if (typeof bip39 === 'undefined') {
        alert('bip39 не загружен!');
        return;
    }
    mnemonic = bip39.generateMnemonic();
    document.getElementById('seedBox').innerText = mnemonic;
}

async function completeRegistration() {
    document.getElementById('statusMsg').innerText = 'Вычисление xPub...';
    // Получить buyer_id и account (invoices_group)
    const buyer_id = document.getElementById('buyer_id').value.trim();
    const account = parseInt(document.getElementById('account').value) || 0;
    if (!buyer_id) {
        document.getElementById('statusMsg').innerText = 'Укажите buyer_id!';
        return;
    }
    // Вычислить xPub для TRON: m/44'/195'/account'
    const seed = bip39.mnemonicToSeedSync(mnemonic);
    const hdkey = ethereumjs.Wallet.hdkey.fromMasterSeed(seed);
    const node = hdkey.derivePath(`m/44'/195'/${account}'`);
    const xpub = node.publicExtendedKey;
    // Отправить POST на API
    document.getElementById('statusMsg').innerText = 'Отправка данных на сервер...';
    try {
        const resp = await fetch('/api/complete_registration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, xpub, buyer_id, invoices_group: account })
        });
        if (resp.ok) {
            document.getElementById('statusMsg').innerHTML = '<b>Настройка завершена, вернитесь в Telegram.</b>';
        } else {
            const err = await resp.text();
            document.getElementById('statusMsg').innerText = 'Ошибка: ' + err;
        }
    } catch (e) {
        document.getElementById('statusMsg').innerText = 'Ошибка соединения: ' + e.message;
    }
}
