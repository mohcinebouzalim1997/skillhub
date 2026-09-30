(function () {
  var bridge = { connected: false, token: null, status: null };

  function initMarketplace(root) {
    var search = root.querySelector('[data-skill-search]');
    var cards = Array.from(root.querySelectorAll('[data-skill-card]'));
    var chips = Array.from(root.querySelectorAll('[data-skill-filter]'));
    var count = root.querySelector('[data-skill-count]');
    var active = 'all';
    function apply() {
      var q = (search && search.value || '').trim().toLowerCase();
      var visible = 0;
      cards.forEach(function (card) {
        var text = (card.getAttribute('data-search') || '').toLowerCase();
        var cat = card.getAttribute('data-category') || '';
        var ok = (active === 'all' || active === cat) && (!q || text.indexOf(q) !== -1);
        card.classList.toggle('hidden', !ok);
        if (ok) visible += 1;
      });
      if (count) count.textContent = visible + (visible === 1 ? ' skill' : ' skills');
    }
    if (search) search.addEventListener('input', apply);
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        active = chip.getAttribute('data-skill-filter') || 'all';
        chips.forEach(function (c) { c.classList.toggle('active', c === chip); });
        apply();
      });
    });
    apply();
  }

  function initCopyButtons() {
    document.querySelectorAll('[data-copy-text]').forEach(function (button) {
      if (button.getAttribute('data-copy-ready') === '1') return;
      button.setAttribute('data-copy-ready', '1');
      button.addEventListener('click', function () {
        var value = button.getAttribute('data-copy-text') || '';
        navigator.clipboard.writeText(value).then(function () {
          var old = button.textContent;
          button.textContent = 'Copied ✓';
          window.setTimeout(function () { button.textContent = old; }, 1300);
        });
      });
    });
  }

  function renderBridgeStatus() {
    document.querySelectorAll('[data-control-status]').forEach(function (el) {
      if (bridge.connected) {
        var skills = bridge.status && bridge.status.skills || {};
        var current = Object.keys(skills).filter(function (id) { return skills[id].state === 'current'; }).length;
        var updates = Object.keys(skills).filter(function (id) { return skills[id].state === 'update-available'; }).length;
        el.innerHTML = '<strong>Local control center connected ✓</strong> · ' + current + ' current · ' + updates + ' update(s) available';
        el.classList.add('connected');
      }
    });
    document.querySelectorAll('[data-skill-action]').forEach(function (button) {
      var id = button.getAttribute('data-skill-id');
      var row = bridge.status && bridge.status.skills && bridge.status.skills[id];
      if (!bridge.connected || !row) return;
      button.style.display = 'inline-flex';
      button.disabled = row.state === 'current';
      button.textContent = row.state === 'current' ? 'Installed ✓' : (row.state === 'update-available' ? 'Update' : 'Install');
      button.setAttribute('data-action-kind', row.state === 'update-available' ? 'update-skill' : 'install-skill');
    });
    document.querySelectorAll('[data-pack-action], [data-stack-action]').forEach(function (button) {
      if (bridge.connected) button.style.display = 'inline-flex';
    });
  }

  function bridgePost(endpoint, payload, button) {
    if (!bridge.connected) return;
    var old = button.textContent;
    button.disabled = true;
    button.textContent = 'Working…';
    fetch('/api/' + endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SkillHub-Token': bridge.token},
      body: JSON.stringify(payload)
    }).then(function (response) { return response.json().then(function (body) { return {ok: response.ok, body: body}; }); })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || 'SkillHub action failed');
        bridge.status = result.body.status;
        renderBridgeStatus();
      }).catch(function (err) {
        button.disabled = false;
        button.textContent = old;
        window.alert(err.message);
      });
  }

  function initBridgeActions() {
    document.querySelectorAll('[data-skill-action]').forEach(function (button) {
      if (button.getAttribute('data-bridge-ready') === '1') return;
      button.setAttribute('data-bridge-ready', '1');
      button.addEventListener('click', function () {
        var kind = button.getAttribute('data-action-kind') || 'install-skill';
        bridgePost(kind, {skill: button.getAttribute('data-skill-id')}, button);
      });
    });
    document.querySelectorAll('[data-pack-action]').forEach(function (button) {
      if (button.getAttribute('data-bridge-ready') === '1') return;
      button.setAttribute('data-bridge-ready', '1');
      button.addEventListener('click', function () { bridgePost('install-pack', {pack: button.getAttribute('data-pack-id')}, button); });
    });
    document.querySelectorAll('[data-stack-action]').forEach(function (button) {
      if (button.getAttribute('data-bridge-ready') === '1') return;
      button.setAttribute('data-bridge-ready', '1');
      button.addEventListener('click', function () { bridgePost('install-stack', {stack: button.getAttribute('data-stack-id')}, button); });
    });
  }

  function connectBridge() {
    fetch('/api/session', {cache: 'no-store'}).then(function (response) {
      if (!response.ok) throw new Error('no bridge');
      return response.json();
    }).then(function (data) {
      bridge.connected = true;
      bridge.token = data.token;
      bridge.status = data;
      document.documentElement.classList.add('skillhub-local');
      renderBridgeStatus();
    }).catch(function () {
      bridge.connected = false;
    });
  }

  function boot() {
    document.querySelectorAll('[data-marketplace]').forEach(initMarketplace);
    initCopyButtons();
    initBridgeActions();
    connectBridge();
  }
  if (typeof document$ !== 'undefined') document$.subscribe(boot);
  else document.addEventListener('DOMContentLoaded', boot);
})();
