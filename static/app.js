const $ = id => document.getElementById(id);

function showMsg(el, text, type) { el.textContent = text; el.className = 'msg show ' + (type || 'info'); }
function hideMsg(el) { el.className = 'msg'; }

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch (e) {}
  return { status: r.status, data };
}

const STAT_LABELS = {
  gamesplayed: 'Games Played', wins: 'Wins', kills: 'Kills', deaths: 'Deaths',
  headshots: 'Headshots', head_shot_kills: 'Headshots', damage: 'Damage',
  top10_times: 'Top 10', top_n_times: 'Top', highest_kills: 'Best Kills',
  rating_points: 'Rating Points', revives: 'Revives', revivals: 'Revives',
  assists: 'Assists', mvp_count: 'MVP', distance_travelled: 'Distance',
  survival_time: 'Survival Time', knock_down: 'Knockdowns', knock_downs: 'Knockdowns',
  pick_ups: 'Pickups', gold_medal_cnt: 'Gold', silver_medal_cnt: 'Silver',
  hit_count: 'Hits', double_kills: '2x Kills', triple_kills: '3x Kills',
  four_kills: '4x Kills', streak_wins: 'Streak Wins', throwing_kills: 'Throw Kills',
  one_game_most_damage: 'Most DMG', one_game_most_kills: 'Most Kills',
  rating_enabled_games: 'RP Games', headshot_count: 'HS Count', road_kills: 'Road Kills'
};

const abbreviate = (n, d = 1) => {
  if (!n && n !== 0) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n / 1e9).toFixed(d).replace(/\.0$/, '') + 'B';
  if (abs >= 1e6) return (n / 1e6).toFixed(d).replace(/\.0$/, '') + 'M';
  if (abs >= 1e4) return (n / 1e3).toFixed(d).replace(/\.0$/, '') + 'K';
  return n.toLocaleString();
};
const exactNum = (n) => (n === null || n === undefined) ? '—' : Number(n).toLocaleString();
const fmtDur = (v) => { if (!v) return '—'; const s = Number(v); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h}h ${m}m` : `${m}m`; };
const fmtUptime = (s) => {
  if (!s && s !== 0) return '—';
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h ${m}m`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
};

function animateCount(el, target, formatter, dur = 900) {
  const start = performance.now();
  function tick(now) {
    const p = Math.min((now - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = formatter(eased * target);
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function setStat(el, value, isPct, isDur) {
  const target = value === null || value === undefined ? 0 : value;
  const fmt = (v) => isPct ? v.toFixed(1) + '%' : isDur ? fmtDur(v) : abbreviate(v);
  const exact = isPct ? Number(value || 0).toFixed(2) + '%' : isDur ? fmtDur(value) : exactNum(value);
  el.title = `Exact: ${exact}`;
  const sub = el.querySelector('.exact');
  if (sub) sub.textContent = exact;
  animateCount(el, target, fmt);
}

function statEl(label, value, isPct = false, isDur = false) {
  const disp = isPct ? (value || 0).toFixed(1) + '%' : isDur ? fmtDur(value) : abbreviate(value);
  const exact = isPct ? Number(value || 0).toFixed(2) + '%' : isDur ? fmtDur(value) : exactNum(value);
  return `<div class="stat" data-exact="${exact}" title="Exact: ${exact} — click to pin">
    <span class="exact">${exact}</span>
    <div class="v">${disp}</div>
    <div class="k">${label}</div>
  </div>`;
}

document.addEventListener('click', e => {
  const stat = e.target.closest('.stat');
  if (!stat) return;
  const v = stat.querySelector('.v');
  const exact = stat.dataset.exact;
  if (!exact || stat.classList.contains('pinned')) {
    stat.classList.remove('pinned');
    v.textContent = stat.dataset.orig;
    stat.querySelector('.exact').style.opacity = '';
    return;
  }
  stat.classList.add('pinned');
  stat.dataset.orig = v.textContent;
  v.textContent = exact;
  stat.querySelector('.exact').style.opacity = '0';
});

function statCard(obj, label) {
  const d = (obj && obj.detailedstats) || {};
  const games = Number(obj && obj.gamesplayed) || 0;
  const wins = Number(obj && obj.wins) || 0;
  const kills = Number(obj && obj.kills) || 0;
  const deaths = Number(d.deaths) || 0;
  const kd = deaths ? (kills / deaths) : kills;
  const wr = games ? (wins / games * 100) : 0;
  const rows = [
    ['Games Played', games, false, false], ['Wins', wins, false, false],
    ['Win Rate', wr, true, false], ['Kills', kills, false, false],
    ['Deaths', deaths, false, false], ['K/D', kd, false, false]
  ];
  for (const k of Object.keys(STAT_LABELS)) {
    const v = d[k];
    if (v !== undefined && v !== null && v !== 0 && !['deaths'].includes(k)) {
      rows.push([STAT_LABELS[k], v, false, k === 'survival_time']);
    }
  }
  const seen = {};
  let html = '<div class="mode-panel active"><div class="stats-grid">';
  rows.forEach(([k, v, isPct, isDur]) => {
    if (seen[k]) return; seen[k] = 1;
    html += statEl(k, v, isPct, isDur);
  });
  html += '</div></div>';
  return html;
}

function togglePw(el, full) { el.textContent = el.textContent.includes('…') ? full : full.slice(0, 12) + '…'; }

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function colorizeLog(text) {
  let out = esc(text);
  out = out.replace(/✅/g, '<span class="c-ok">✓</span>')
           .replace(/❌/g, '<span class="c-err">✗</span>')
           .replace(/⚠️/g, '<span class="c-warn">⚠</span>')
           .replace(/🟢/g, '<span class="c-ok">●</span>')
           .replace(/🔴/g, '<span class="c-err">●</span>');
  return out;
}

document.addEventListener('DOMContentLoaded', () => {
  const burger = $('burger');
  if (burger) burger.onclick = () => $('sidebar').classList.toggle('open');
  document.querySelectorAll('.nav a').forEach(a => {
    if (a.getAttribute('href') === location.pathname) a.classList.add('active');
  });
});