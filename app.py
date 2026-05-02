from flask import Flask, render_template_string, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import csv
import io
from datetime import datetime
from fake_useragent import UserAgent

app = Flask(__name__)

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

def get_headers():
    try:
        ua = UserAgent()
        return {'User-Agent': ua.random}
    except:
        return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def extract_emails(text):
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))

def scrape_store_email(domain):
    pages = ['/pages/contact', '/pages/about-us', '/pages/about', '/policies/contact-information']
    for page in pages:
        try:
            url = f'https://{domain}{page}'
            r = requests.get(url, headers=get_headers(), timeout=8)
            if r.status_code == 200:
                emails = extract_emails(r.text)
                emails = [e for e in emails if not e.endswith(('.png','.jpg','.css','.js'))]
                if emails:
                    return emails[0]
        except:
            continue
    return ''

def search_shopify_stores(keyword, max_results=20):
    stores = []
    queries = [
        f'site:myshopify.com "{keyword}"',
        f'"powered by shopify" "{keyword}"',
        f'site:myshopify.com "{keyword}" inurl:contact',
    ]
    seen = set()
    for query in queries:
        try:
            url = f'https://www.google.com/search?q={requests.utils.quote(query)}&num=10&tbs=qdr:m'
            r = requests.get(url, headers=get_headers(), timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for g in soup.find_all('div', class_='g'):
                try:
                    link = g.find('a')['href']
                    title = g.find('h3').text if g.find('h3') else 'Unknown Store'
                    domain = re.search(r'https?://([^/]+)', link)
                    if domain:
                        domain = domain.group(1)
                        if domain not in seen and ('myshopify' in domain or 'shopify' in link.lower()):
                            seen.add(domain)
                            stores.append({'domain': domain, 'name': title, 'niche': keyword, 'email': '', 'date_found': datetime.now().strftime('%Y-%m-%d %H:%M')})
                except:
                    continue
        except:
            continue
    return stores[:max_results]

def save_store(store):
    try:
        conn = sqlite3.connect('stores.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO stores (domain, name, email, niche, date_found) VALUES (?,?,?,?,?)',
                  (store['domain'], store['name'], store['email'], store['niche'], store['date_found']))
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

HTML = '''
<!DOCTYPE html>
<html>
<head>
<title>Shopify Store Finder</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{background:#f8f9fa;}
.navbar{background:#5c6bc0!important;}
.card{border:none;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);}
.btn-primary{background:#5c6bc0;border-color:#5c6bc0;}
.badge-email{background:#e8f5e9;color:#2e7d32;padding:4px 10px;border-radius:20px;font-size:12px;}
.badge-no-email{background:#fce4ec;color:#c62828;padding:4px 10px;border-radius:20px;font-size:12px;}
#loading{display:none;}
</style>
</head>
<body>
<nav class="navbar navbar-dark px-4 py-3">
  <span class="navbar-brand fw-bold">🛍️ Shopify Store Finder</span>
  <span class="text-white-50 small">Personal Use Only</span>
</nav>
<div class="container py-4">
  <div class="card p-4 mb-4">
    <h5 class="mb-3">Find New Shopify Stores</h5>
    <div class="row g-2">
      <div class="col-md-6">
        <input type="text" id="keyword" class="form-control" placeholder="Enter niche keyword (e.g. fashion, fitness, pets)">
      </div>
      <div class="col-md-3">
        <select id="maxResults" class="form-select">
          <option value="10">10 stores</option>
          <option value="20" selected>20 stores</option>
          <option value="30">30 stores</option>
        </select>
      </div>
      <div class="col-md-3">
        <button class="btn btn-primary w-100" onclick="searchStores()">🔍 Search Stores</button>
      </div>
    </div>
    <div id="loading" class="text-center mt-3">
      <div class="spinner-border text-primary"></div>
      <p class="mt-2 text-muted">Searching for stores and extracting emails...</p>
    </div>
  </div>

  <div class="card p-4 mb-4" id="statsCard" style="display:none;">
    <div class="row text-center">
      <div class="col"><h3 id="totalCount">0</h3><small class="text-muted">Total Saved</small></div>
      <div class="col"><h3 id="emailCount">0</h3><small class="text-muted">With Email</small></div>
      <div class="col"><h3 id="nicheCount">0</h3><small class="text-muted">Niches</small></div>
    </div>
  </div>

  <div class="card p-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0">Saved Stores</h5>
      <div class="d-flex gap-2">
        <input type="text" id="filterInput" class="form-control form-control-sm" placeholder="Filter..." oninput="filterTable()" style="width:200px;">
        <button class="btn btn-sm btn-outline-success" onclick="exportCSV()">📥 Export CSV</button>
        <button class="btn btn-sm btn-outline-danger" onclick="clearAll()">🗑️ Clear All</button>
      </div>
    </div>
    <div class="table-responsive">
      <table class="table table-hover" id="storeTable">
        <thead class="table-light">
          <tr><th>Store Name</th><th>Domain</th><th>Email</th><th>Niche</th><th>Date Found</th></tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
async function searchStores() {
  const keyword = document.getElementById('keyword').value.trim();
  const maxResults = document.getElementById('maxResults').value;
  if (!keyword) { alert('Enter a keyword'); return; }
  document.getElementById('loading').style.display = 'block';
  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({keyword, max_results: parseInt(maxResults)})
    });
    const data = await res.json();
    alert(data.message);
    loadStores();
  } catch(e) { alert('Error: ' + e); }
  document.getElementById('loading').style.display = 'none';
}

async function loadStores() {
  const res = await fetch('/stores');
  const stores = await res.json();
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';
  stores.forEach(s => {
    const emailBadge = s.email
      ? `<span class="badge-email">${s.email}</span>`
      : `<span class="badge-no-email">No email</span>`;
    tbody.innerHTML += `<tr>
      <td>${s.name}</td>
      <td><a href="https://${s.domain}" target="_blank">${s.domain}</a></td>
      <td>${emailBadge}</td>
      <td><span class="badge bg-light text-dark">${s.niche}</span></td>
      <td><small>${s.date_found}</small></td>
    </tr>`;
  });
  const withEmail = stores.filter(s=>s.email).length;
  const niches = new Set(stores.map(s=>s.niche)).size;
  document.getElementById('totalCount').textContent = stores.length;
  document.getElementById('emailCount').textContent = withEmail;
  document.getElementById('nicheCount').textContent = niches;
  document.getElementById('statsCard').style.display = 'block';
}

function filterTable() {
  const val = document.getElementById('filterInput').value.toLowerCase();
  document.querySelectorAll('#tableBody tr').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(val) ? '' : 'none';
  });
}

function exportCSV() { window.location.href = '/export'; }

async function clearAll() {
  if (!confirm('Clear all saved stores?')) return;
  await fetch('/clear', {method:'POST'});
  loadStores();
}

loadStores();
</script>
</body>
</html>
'''

@app.route('/')
def index():
    init_db()
    return render_template_string(HTML)

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    keyword = data.get('keyword', '')
    max_results = data.get('max_results', 20)
    stores = search_shopify_stores(keyword, max_results)
    count = 0
    for store in stores:
        store['email'] = scrape_store_email(store['domain'])
        save_store(store)
        count += 1
    return jsonify({'message': f'Found and saved {count} stores for "{keyword}"', 'count': count})

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
