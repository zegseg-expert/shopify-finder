from flask import Flask, render_template_string, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import csv
import io
from datetime import datetime

app = Flask(__name__)

SERPAPI_KEY = 'f4cb1dfb81de2e942b9773416ab32c9dac86ea7dcab5c541321d0cc585b43f6d'

def init_db():
    conn = sqlite3.connect('stores.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stores
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  domain TEXT UNIQUE,
                  name TEXT,
                  email TEXT,
                  niche TEXT,
                  date_found TEXT)''')
    conn.commit()
    conn.close()

def extract_emails(text):
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = list(set(re.findall(pattern, text)))
    return [e for e in emails if not any(e.endswith(x) for x in ['.png','.jpg','.css','.js','.svg','.gif','.woff'])]

def scrape_store_email(domain):
    pages = ['/pages/contact','/pages/about-us','/pages/about','/policies/contact-information','/pages/faq']
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for page in pages:
        try:
            r = requests.get(f'https://{domain}{page}', headers=headers, timeout=8)
            if r.status_code == 200:
                emails = extract_emails(r.text)
                if emails:
                    return emails[0]
        except:
            continue
    return ''

def search_shopify_stores(keyword, max_results=50, time_filter='qdr:m'):
    stores = []
    seen = set()
    queries = [
        f'site:myshopify.com "{keyword}"',
        f'site:myshopify.com "{keyword}" inurl:contact',
        f'site:myshopify.com "{keyword}" inurl:about',
        f'"powered by shopify" "{keyword}"',
        f'site:myshopify.com "{keyword}" "@gmail.com"',
        f'site:myshopify.com "{keyword}" "new arrivals"',
        f'site:myshopify.com "{keyword}" "free shipping"',
    ]
    for query in queries:
        if len(stores) >= max_results:
            break
        try:
            url = 'https://serpapi.com/search'
            params = {
                'api_key': SERPAPI_KEY,
                'q': query,
                'num': 10,
                'tbs': time_filter,
                'engine': 'google',
            }
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            for item in data.get('organic_results', []):
                link = item.get('link', '')
                title = item.get('title', 'Unknown Store')
                domain_match = re.search(r'https?://([^/]+)', link)
                if domain_match:
                    d = domain_match.group(1)
                    if d not in seen:
                        seen.add(d)
                        stores.append({
                            'domain': d,
                            'name': title,
                            'niche': keyword,
                            'email': '',
                            'date_found': datetime.now().strftime('%Y-%m-%d %H:%M')
                        })
        except Exception as e:
            print(f'Error: {e}')
            continue
    return stores[:max_results]

def save_store(store):
    try:
        conn = sqlite3.connect('stores.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO stores (domain,name,email,niche,date_found) VALUES (?,?,?,?,?)',
                  (store['domain'],store['name'],store['email'],store['niche'],store['date_found']))
        conn.commit()
        conn.close()
    except:
        pass

def get_all_stores(niche_filter=''):
    conn = sqlite3.connect('stores.db')
    c = conn.cursor()
    if niche_filter:
        c.execute('SELECT * FROM stores WHERE niche=? ORDER BY id DESC', (niche_filter,))
    else:
        c.execute('SELECT * FROM stores ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return [{'id':r[0],'domain':r[1],'name':r[2],'email':r[3],'niche':r[4],'date_found':r[5]} for r in rows]

HTML = '''<!DOCTYPE html>
<html>
<head>
<title>Shopify Store Finder</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{background:#f0f2f5;font-family:sans-serif;}
.navbar{background:#4a3f8f!important;}
.card{border:none;border-radius:14px;box-shadow:0 2px 12px rgba(0,0,0,0.07);margin-bottom:1rem;}
.stat{background:#4a3f8f;color:white;border-radius:14px;padding:1rem;text-align:center;}
.stat h2{font-size:2rem;font-weight:700;margin:0;}
.stat p{margin:0;opacity:.8;font-size:.85rem;}
.badge-email{background:#e8f5e9;color:#2e7d32;padding:3px 10px;border-radius:20px;font-size:11px;white-space:nowrap;}
.badge-no{background:#fce4ec;color:#c62828;padding:3px 10px;border-radius:20px;font-size:11px;}
#loading{display:none;text-align:center;padding:1rem;}
.btn-search{background:#4a3f8f;color:white;border:none;padding:.5rem 1.5rem;border-radius:8px;font-weight:600;width:100%;}
.btn-search:hover{background:#3a2f7f;color:white;}
.btn-search:disabled{background:#999;cursor:not-allowed;}
</style>
</head>
<body>
<nav class="navbar navbar-dark px-4 py-3">
  <span class="navbar-brand fw-bold">🛍️ Shopify Store Finder</span>
  <span class="text-white-50 small">Personal Use Only</span>
</nav>

<div class="container py-3">
  <div class="card p-3">
    <h6 class="fw-bold mb-3">🔍 Find New Shopify Stores</h6>
    <div class="mb-2">
      <input type="text" id="keyword" class="form-control" placeholder="Niche keyword (e.g. fashion, fitness, pets)">
    </div>
    <div class="row g-2 mb-2">
      <div class="col-6">
        <select id="maxResults" class="form-select form-select-sm">
          <option value="20">20 stores</option>
          <option value="30">30 stores</option>
          <option value="50" selected>50 stores</option>
        </select>
      </div>
      <div class="col-6">
        <select id="timeFilter" class="form-select form-select-sm">
          <option value="qdr:w">Past week</option>
          <option value="qdr:m" selected>Past month</option>
          <option value="qdr:y">Past year</option>
        </select>
      </div>
    </div>
    <button class="btn-search" id="searchBtn" type="button" onclick="doSearch()">🔍 Search Stores</button>
    <div id="loading">
      <div class="spinner-border text-primary mt-2" style="width:1.5rem;height:1.5rem;"></div>
      <p class="text-muted small mt-1">Searching for stores and extracting emails...<br>Please wait 1-2 minutes.</p>
    </div>
  </div>

  <div class="row g-2 mb-2">
    <div class="col-4"><div class="stat"><h2 id="totalCount">0</h2><p>Saved</p></div></div>
    <div class="col-4"><div class="stat"><h2 id="emailCount">0</h2><p>Emails</p></div></div>
    <div class="col-4"><div class="stat"><h2 id="nicheCount">0</h2><p>Niches</p></div></div>
  </div>

  <div class="card p-3">
    <div class="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-1">
      <h6 class="fw-bold mb-0">📋 Saved Stores</h6>
      <div class="d-flex gap-1 flex-wrap">
        <button class="btn btn-sm btn-success" type="button" onclick="exportCSV()">📥 CSV</button>
        <button class="btn btn-sm btn-warning" type="button" onclick="copyEmails()">📧 Emails</button>
        <button class="btn btn-sm btn-danger" type="button" onclick="clearAll()">🗑️ Clear</button>
      </div>
    </div>
    <div class="mb-2 d-flex gap-1">
      <input type="text" id="filterInput" class="form-control form-control-sm" placeholder="Filter..." oninput="filterTable()">
      <select id="nicheSelect" class="form-select form-select-sm" style="width:130px;" onchange="filterByNiche()">
        <option value="">All niches</option>
      </select>
    </div>
    <div class="table-responsive">
      <table class="table table-sm table-hover">
        <thead class="table-light">
          <tr><th>#</th><th>Store</th><th>Email</th><th>Niche</th></tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <textarea id="emailsBox" class="form-control mt-2" rows="4" style="display:none;" readonly placeholder="Emails will appear here..."></textarea>
  </div>
</div>

<script>
let allStores = [];

function doSearch(){
  const keyword = document.getElementById('keyword').value.trim();
  if(!keyword){ alert('Please enter a keyword!'); return; }
  const maxResults = parseInt(document.getElementById('maxResults').value);
  const timeFilter = document.getElementById('timeFilter').value;
  const btn = document.getElementById('searchBtn');
  btn.disabled = true;
  btn.textContent = 'Searching... please wait';
  document.getElementById('loading').style.display = 'block';
  fetch('/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keyword: keyword, max_results: maxResults, time_filter: timeFilter})
  })
  .then(r => r.json())
  .then(data => {
    alert(data.message);
    loadStores();
  })
  .catch(e => alert('Error: ' + e))
  .finally(() => {
    btn.disabled = false;
    btn.textContent = '🔍 Search Stores';
    document.getElementById('loading').style.display = 'none';
  });
}

function loadStores(){
  fetch('/stores')
  .then(r => r.json())
  .then(data => {
    allStores = data;
    renderTable(allStores);
    updateStats(allStores);
    updateNicheFilter(allStores);
  });
}

function renderTable(stores){
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';
  if(stores.length === 0){
    tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">No stores found yet. Search above!</td></tr>';
    return;
  }
  stores.forEach((s,i) => {
    const em = s.email
      ? '<span class="badge-email">'+s.email+'</span>'
      : '<span class="badge-no">No email</span>';
    tbody.innerHTML += '<tr><td><small>'+(i+1)+'</small></td><td><small><a href="https://'+s.domain+'" target="_blank">'+s.domain+'</a><br><span class="text-muted" style="font-size:10px;">'+s.name.substring(0,30)+'</span></small></td><td>'+em+'</td><td><span class="badge bg-light text-dark" style="font-size:10px;">'+s.niche+'</span></td></tr>';
  });
}

function updateStats(stores){
  document.getElementById('totalCount').textContent = stores.length;
  document.getElementById('emailCount').textContent = stores.filter(s=>s.email).length;
  document.getElementById('nicheCount').textContent = new Set(stores.map(s=>s.niche)).size;
}

function updateNicheFilter(stores){
  const niches = [...new Set(stores.map(s=>s.niche))];
  const sel = document.getElementById('nicheSelect');
  const cur = sel.value;
  sel.innerHTML = '<option value="">All niches</option>';
  niches.forEach(n => sel.innerHTML += '<option value="'+n+'"'+(n===cur?' selected':'')+'>'+n+'</option>');
}

function filterTable(){
  const val = document.getElementById('filterInput').value.toLowerCase();
  const filtered = allStores.filter(s =>
    s.domain.toLowerCase().includes(val) ||
    s.name.toLowerCase().includes(val) ||
    (s.email||'').toLowerCase().includes(val)
  );
  renderTable(filtered);
}

function filterByNiche(){
  const niche = document.getElementById('nicheSelect').value;
  const filtered = niche ? allStores.filter(s=>s.niche===niche) : allStores;
  renderTable(filtered);
  updateStats(filtered);
}

function exportCSV(){ window.location.href = '/export'; }

function copyEmails(){
  const emails = allStores.filter(s=>s.email).map(s=>s.email).join('\n');
  if(!emails){ alert('No emails found yet!'); return; }
  const box = document.getElementById('emailsBox');
  box.style.display = 'block';
  box.value = emails;
  box.select();
  document.execCommand('copy');
  alert('✅ '+allStores.filter(s=>s.email).length+' emails copied to clipboard!');
}

function clearAll(){
  if(!confirm('Clear all saved stores?')) return;
  fetch('/clear', {method:'POST'}).then(() => loadStores());
}

loadStores();
</script>
</body>
</html>'''

@app.route('/')
def index():
    init_db()
    return render_template_string(HTML)

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    keyword = data.get('keyword', '')
    max_results = data.get('max_results', 50)
    time_filter = data.get('time_filter', 'qdr:m')
    stores = search_shopify_stores(keyword, max_results, time_filter)
    count = 0
    email_count = 0
    for store in stores:
        store['email'] = scrape_store_email(store['domain'])
        if store['email']:
            email_count += 1
        save_store(store)
        count += 1
    return jsonify({
        'message': f'✅ Found {count} stores for "{keyword}"! {email_count} have emails.',
        'count': count
    })

@app.route('/stores')
def stores():
    niche = request.args.get('niche', '')
    return jsonify(get_all_stores(niche))

@app.route('/export')
def export():
    stores = get_all_stores()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['id','domain','name','email','niche','date_found'])
    writer.writeheader()
    writer.writerows(stores)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=shopify_stores.csv'
    response.headers['Content-type'] = 'text/csv'
    return response

@app.route('/clear', methods=['POST'])
def clear():
    conn = sqlite3.connect('stores.db')
    conn.execute('DELETE FROM stores')
    conn.commit()
    conn.close()
    return jsonify({'status': 'cleared'})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
