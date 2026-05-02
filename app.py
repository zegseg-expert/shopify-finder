from flask import Flask, render_template_string, request, jsonify, make_response
import requests
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
    return [e for e in emails if not any(e.endswith(x) for x in ['.png','.jpg','.css','.js','.svg','.gif'])]

def scrape_store_email(domain):
    pages = ['/pages/contact','/pages/about-us','/pages/about','/policies/contact-information']
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

def get_all_stores():
    conn = sqlite3.connect('stores.db')
    c = conn.cursor()
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
body{background:#f8f9fa;}
.navbar{background:#5c6bc0!important;}
.card{border:none;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);}
.btn-primary{background:#5c6bc0;border-color:#5c6bc0;}
.btn-primary:hover{background:#3949ab;border-color:#3949ab;}
.badge-email{background:#e8f5e9;color:#2e7d32;padding:4px 10px;border-radius:20px;font-size:12px;}
.badge-no{background:#fce4ec;color:#c62828;padding:4px 10px;border-radius:20px;font-size:12px;}
#loading{display:none;}
</style>
</head>
<body>
<nav class="navbar navbar-dark px-4 py-3">
  <span class="navbar-brand fw-bold">Shopify Store Finder</span>
  <span class="text-white-50 small">Personal Use Only</span>
</nav>
<div class="container py-4">
  <div class="card p-4 mb-4">
    <h5 class="mb-3">Find New Shopify Stores</h5>
    <div class="mb-2">
      <input type="text" id="keyword" class="form-control" placeholder="Niche keyword (e.g. fashion, fitness, pets)">
    </div>
    <div class="row g-2 mb-2">
      <div class="col-6">
        <select id="maxResults" class="form-select">
          <option value="20">20 stores</option>
          <option value="30">30 stores</option>
          <option value="50" selected>50 stores</option>
        </select>
      </div>
      <div class="col-6">
        <select id="timeFilter" class="form-select">
          <option value="qdr:w">Past week</option>
          <option value="qdr:m" selected>Past month</option>
          <option value="qdr:y">Past year</option>
        </select>
      </div>
    </div>
    <button class="btn btn-primary w-100" id="searchBtn" onclick="doSearch()">Search Stores</button>
    <div id="loading" class="text-center mt-3">
      <div class="spinner-border text-primary"></div>
      <p class="mt-2 text-muted small">Searching... please wait 1-2 minutes</p>
    </div>
  </div>

  <div class="row g-3 mb-4">
    <div class="col-4">
      <div class="card p-3 text-center" style="background:#5c6bc0;color:white;">
        <h3 id="totalCount">0</h3><small>Saved</small>
      </div>
    </div>
    <div class="col-4">
      <div class="card p-3 text-center" style="background:#5c6bc0;color:white;">
        <h3 id="emailCount">0</h3><small>Emails</small>
      </div>
    </div>
    <div class="col-4">
      <div class="card p-3 text-center" style="background:#5c6bc0;color:white;">
        <h3 id="nicheCount">0</h3><small>Niches</small>
      </div>
    </div>
  </div>

  <div class="card p-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0">Saved Stores</h5>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-success" onclick="exportCSV()">CSV</button>
        <button class="btn btn-sm btn-warning" onclick="copyEmails()">Emails</button>
        <button class="btn btn-sm btn-danger" onclick="clearAll()">Clear</button>
      </div>
    </div>
    <input type="text" id="filterInput" class="form-control form-control-sm mb-2" placeholder="Filter stores..." oninput="filterTable()">
    <div class="table-responsive">
      <table class="table table-hover table-sm">
        <thead class="table-light">
          <tr><th>#</th><th>Store Name</th><th>Domain</th><th>Email</th><th>Niche</th><th>Date</th></tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <textarea id="emailsBox" class="form-control mt-2" rows="4" style="display:none;" readonly></textarea>
  </div>
</div>

<script>
var allStores = [];

function doSearch() {
  var keyword = document.getElementById('keyword').value.trim();
  if (!keyword) { alert('Please enter a keyword!'); return; }
  var maxResults = parseInt(document.getElementById('maxResults').value);
  var timeFilter = document.getElementById('timeFilter').value;
  var btn = document.getElementById('searchBtn');
  btn.disabled = true;
  btn.innerHTML = 'Searching... please wait';
  document.getElementById('loading').style.display = 'block';
  fetch('/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keyword: keyword, max_results: maxResults, time_filter: timeFilter})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    alert(data.message);
    loadStores();
  })
  .catch(function(e) { alert('Error: ' + e); })
  .finally(function() {
    btn.disabled = false;
    btn.innerHTML = 'Search Stores';
    document.getElementById('loading').style.display = 'none';
  });
}

function loadStores() {
  fetch('/stores')
  .then(function(r) { return r.json(); })
  .then(function(data) {
    allStores = data;
    renderTable(allStores);
    document.getElementById('totalCount').textContent = allStores.length;
    document.getElementById('emailCount').textContent = allStores.filter(function(s){return s.email;}).length;
    document.getElementById('nicheCount').textContent = new Set(allStores.map(function(s){return s.niche;})).size;
  });
}

function renderTable(stores) {
  var tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';
  if (stores.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">No stores yet. Search above!</td></tr>';
    return;
  }
  stores.forEach(function(s, i) {
    var em = s.email
      ? '<span class="badge-email">' + s.email + '</span>'
      : '<span class="badge-no">No email</span>';
    tbody.innerHTML += '<tr><td>' + (i+1) + '</td><td><small>' + s.name.substring(0,25) + '</small></td><td><small><a href="https://' + s.domain + '" target="_blank">' + s.domain + '</a></small></td><td>' + em + '</td><td><small>' + s.niche + '</small></td><td><small>' + s.date_found + '</small></td></tr>';
  });
}

function filterTable() {
  var val = document.getElementById('filterInput').value.toLowerCase();
  var filtered = allStores.filter(function(s) {
    return s.domain.toLowerCase().includes(val) || s.name.toLowerCase().includes(val) || (s.email||'').toLowerCase().includes(val);
  });
  renderTable(filtered);
}

function exportCSV() { window.location.href = '/export'; }

function copyEmails() {
  var emails = allStores.filter(function(s){return s.email;}).map(function(s){return s.email;}).join('\n');
  if (!emails) { alert('No emails found yet!'); return; }
  var box = document.getElementById('emailsBox');
  box.style.display = 'block';
  box.value = emails;
  box.select();
  document.execCommand('copy');
  alert('Emails copied!');
}

function clearAll() {
  if (!confirm('Clear all saved stores?')) return;
  fetch('/clear', {method:'POST'}).then(function(){loadStores();});
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
        'message': 'Found ' + str(count) + ' stores for "' + keyword + '"! ' + str(email_count) + ' have emails.',
        'count': count
    })

@app.route('/stores')
def stores():
    return jsonify(get_all_stores())

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
