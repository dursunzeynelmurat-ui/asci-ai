import streamlit as st
import requests
import base64
import json
import re
import sqlite3
import datetime
import time
import random

# --- Sayfa Yapılandırması ---
st.set_page_config(
    page_title="Akıllı Mutfak Asistanı", 
    layout="wide", 
    page_icon="👨‍🍳",
    initial_sidebar_state="collapsed"
)

# --- API ve Veritabanı ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

def init_db():
    conn = sqlite3.connect('tarifler.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def save_recipe_to_db(title, content, source):
    conn = sqlite3.connect('tarifler.db')
    c = conn.cursor()
    c.execute('INSERT INTO recipes (title, content, source) VALUES (?, ?, ?)', (title, content, source))
    conn.commit()
    conn.close()

def get_all_recipes():
    conn = sqlite3.connect('tarifler.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM recipes ORDER BY created_at DESC')
    recipes = [dict(row) for row in c.fetchall()]
    conn.close()
    return recipes

def delete_recipe_from_db(recipe_id):
    conn = sqlite3.connect('tarifler.db')
    c = conn.cursor()
    c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    conn.commit()
    conn.close()

init_db()

# --- Yardımcı Fonksiyonlar ---
def file_to_generative_part(uploaded_file):
    if uploaded_file is None: return None, None
    file_bytes = uploaded_file.read()
    base64_data = base64.b64encode(file_bytes).decode('utf-8')
    return {"inlineData": {"data": base64_data, "mimeType": uploaded_file.type}}, uploaded_file.type

def call_gemini_api(parts_list, system_instruction, api_key, use_search_grounding=False):
    if not api_key: return None
    
    payload = {
        "contents": [{"parts": parts_list}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
    }
    if use_search_grounding: payload["tools"] = [{"google_search": {}}]
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{GEMINI_API_URL}?key={api_key}", 
                headers={'Content-Type': 'application/json'}, 
                data=json.dumps(payload)
            )
            response.raise_for_status()
            result = response.json()
            candidate = result.get('candidates', [None])[0]
            text = candidate.get('content', {}).get('parts', [{}])[0].get('text') if candidate else None
            if not text and response.status_code == 200: return ""
            if not text: raise Exception("API'den geçerli yanıt alınamadı.")
            return text
        except Exception as e:
            if attempt < max_retries - 1: time.sleep(2); continue
            st.error(f"Hata: {e}")
            return None

# --- CSS (Sadeleştirilmiş ve Düzeltilmiş) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Poppins', sans-serif; }
    
    /* Buton Stilleri */
    .stButton button {
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s;
        font-weight: 600;
    }
    .stButton button:hover {
        border-color: #10b981;
        color: #10b981;
        background-color: #f0fdf4;
    }
    /* Navigasyon Butonları */
    div[data-testid="column"] .stButton button {
        height: 100%;
        min-height: 60px;
    }
    </style>
""", unsafe_allow_html=True)

# --- Session & API ---
if 'current_page' not in st.session_state: st.session_state['current_page'] = "HOME"
if 'saved_recipes' not in st.session_state: st.session_state['saved_recipes'] = []
if 'transfer_content' not in st.session_state: st.session_state['transfer_content'] = ""
if 'chat_messages' not in st.session_state: st.session_state['chat_messages'] = []

api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("api_keys", {}).get("gemini")
if not api_key:
    st.error("🔑 API Anahtarı Eksik! Lütfen `secrets.toml` dosyasını kontrol edin.")
    st.stop()

# --- Header ---
c1, c2 = st.columns([1, 10])
with c1: st.markdown("# 👨‍🍳")
with c2:
    if st.session_state['current_page'] == "HOME":
        st.markdown("# Akıllı Mutfak Asistanı")
    else:
        if st.button("🏠 Ana Menüye Dön"):
            st.session_state['current_page'] = "HOME"
            st.rerun()

st.markdown("---")

# --- Navigasyon (HOME) ---
PAGES = {
    "🍽️ FOTOĞRAFTAN TARİF": "nav_det", "🔎 TARİF ARAMA": "nav_ser", "🧊 DOLAP ŞEFİ": "nav_fri",
    "💬 MUTFAK GURUSU": "nav_chat", "📊 BESİN ANALİZİ": "nav_nut", "📅 MENÜ PLANLAYICI": "nav_men",
    "🍷 LEZZET EŞLEŞTİRİCİ": "nav_pai", "♻️ TARİF UYARLAMA": "nav_ada", "± PORSİYON": "nav_sca",
    "📒 TARİF DEFTERİM": "nav_boo", "🔄 İKAME": "nav_sub", "⚖️ ÇEVİRİCİ": "nav_con",
    "🌡️ SAKLAMA": "nav_sto", "📝 LİSTE": "nav_lis"
}

if st.session_state['current_page'] == "HOME":
    st.subheader("🚀 Araçlar")
    keys = list(PAGES.keys())
    cols = st.columns(4)
    for i, key in enumerate(keys):
        with cols[i % 4]:
            if st.button(key, use_container_width=True):
                st.session_state['current_page'] = key
                st.rerun()

# --- Ortak Kayıt Fonksiyonu ---
def render_save(content, default_title, source):
    if content:
        st.markdown("---")
        with st.expander("💾 Kaydet", expanded=True):
            with st.form(key=f"sv_{source}"):
                c1, c2 = st.columns([3, 1])
                t = c1.text_input("Başlık", value=default_title)
                if c2.form_submit_button("Kaydet", use_container_width=True):
                    if t:
                        save_recipe_to_db(t, content, source)
                        st.toast("Kaydedildi!", icon="✅")
                    else:
                        st.warning("Başlık giriniz.")

# --- SAYFALAR ---
pg = st.session_state['current_page']

# 1. FOTOĞRAF
if pg == "🍽️ FOTOĞRAFTAN TARİF":
    st.header("📸 Fotoğraf Analizi")
    img = st.file_uploader("Resim Yükle", type=['jpg','png'])
    if img: st.image(img, width=300)
    if st.button("Analiz Et", type="primary"):
        if img:
            with st.spinner("Analiz ediliyor..."):
                res = call_gemini_api([file_to_generative_part(img)[0], {"text": "Bu yemeğin tarifi nedir?"}], "Şefsin.", api_key)
                st.session_state['det_res'] = res
        else:
            st.warning("Lütfen önce bir fotoğraf yükleyin.")
    if 'det_res' in st.session_state:
        st.markdown(st.session_state['det_res'])
        render_save(st.session_state['det_res'], "Fotoğraf Tarifi", "Fotoğraf")

# 2. ARAMA
elif pg == "🔎 TARİF ARAMA":
    st.header("🔎 Web Arama")
    with st.form("search_form"):
        q = st.text_input("Yemek Adı")
        if st.form_submit_button("Bul", type="primary"):
            if q:
                with st.spinner("Aranıyor..."):
                    res = call_gemini_api([{"text": f"'{q}' tarifi"}], "En iyi tarifi bul.", api_key, True)
                    st.session_state['ser_res'] = res
                    st.session_state['ser_q'] = q
            else:
                st.warning("Yemek adı giriniz.")
    if 'ser_res' in st.session_state:
        st.markdown(st.session_state['ser_res'])
        render_save(st.session_state['ser_res'], st.session_state.get('ser_q', ''), "Arama")

# 3. DOLAP
elif pg == "🧊 DOLAP ŞEFİ":
    st.header("🧊 Dolap Şefi")
    img = st.file_uploader("Malzeme Resmi", type=['jpg','png'])
    if img: st.image(img, width=300)
    if st.button("Fikir Ver", type="primary"):
        if img:
            with st.spinner("Düşünülüyor..."):
                res = call_gemini_api([file_to_generative_part(img)[0], {"text": "Ne pişirebilirim?"}], "3 yemek fikri ver.", api_key)
                st.session_state['fri_res'] = res
        else:
            st.warning("Resim yükleyiniz.")
    
    if 'fri_res' in st.session_state:
        st.markdown(st.session_state['fri_res'])
        # Fikirlerden tam tarif oluşturma (Basitleştirilmiş)
        ideas = re.findall(r'\d+\.\s*\**(.*?)\**\n', st.session_state['fri_res']) # Basit regex
        if not ideas: ideas = ["Seçenek 1", "Seçenek 2"] # Fallback
        
        sel_idea = st.selectbox("Bir fikir seçip tarifini oluştur:", ["Seçiniz..."] + ideas)
        if sel_idea != "Seçiniz...":
            if st.button("Tarifi Getir"):
                with st.spinner("Yazılıyor..."):
                    full = call_gemini_api([{"text": f"{sel_idea} tarifi"}], "Şefsin.", api_key)
                    st.session_state['fri_full'] = full
                    
    if 'fri_full' in st.session_state:
        st.info("Tam Tarif:")
        st.markdown(st.session_state['fri_full'])
        render_save(st.session_state['fri_full'], "Dolap Tarifi", "Dolap")

# 4. CHAT
elif pg == "💬 MUTFAK GURUSU":
    st.header("💬 Sohbet")
    for m in st.session_state['chat_messages']:
        st.chat_message(m["role"]).markdown(m["content"])
    if p := st.chat_input("Soru sor..."):
        st.session_state['chat_messages'].append({"role": "user", "content": p})
        st.chat_message("user").markdown(p)
        res = call_gemini_api([{"text": p}], "Mutfak gurususun.", api_key)
        st.session_state['chat_messages'].append({"role": "assistant", "content": res})
        st.chat_message("assistant").markdown(res)

# 5. BESİN
elif pg == "📊 BESİN ANALİZİ":
    st.header("📊 Besin Analizi")
    val = st.session_state.get('transfer_content', '')
    with st.form("nut_form"):
        txt = st.text_area("Tarif", value=val)
        if st.form_submit_button("Analiz Et", type="primary"):
            if txt:
                with st.spinner("Hesaplanıyor..."):
                    res = call_gemini_api([{"text": f"Besin değerleri: {txt}"}], "Diyetisyensin.", api_key)
                    st.session_state['nut_res'] = res
            else:
                st.warning("Metin giriniz.")
    if 'nut_res' in st.session_state:
        st.markdown(st.session_state['nut_res'])
        render_save(st.session_state['nut_res'], "Besin Raporu", "Analiz")

# 6. MENÜ
elif pg == "📅 MENÜ PLANLAYICI":
    st.header("📅 Menü Planla")
    with st.form("men_form"):
        d = st.selectbox("Diyet", ["Standart", "Vegan", "Keto"])
        if st.form_submit_button("Oluştur", type="primary"):
            with st.spinner("Planlanıyor..."):
                res = call_gemini_api([{"text": f"{d} diyeti için 1 günlük menü."}], "Diyetisyensin.", api_key)
                st.session_state['men_res'] = res
    if 'men_res' in st.session_state:
        st.markdown(st.session_state['men_res'])
        render_save(st.session_state['men_res'], f"{d} Menü", "Plan")

# 7. EŞLEŞTİRME
elif pg == "🍷 LEZZET EŞLEŞTİRİCİ":
    st.header("🍷 Eşleştirme")
    val = st.session_state.get('transfer_content', '') if len(st.session_state.get('transfer_content', '')) < 50 else ""
    with st.form("pai_form"):
        dish = st.text_input("Yemek", value=val)
        if st.form_submit_button("Bul", type="primary"):
            if dish:
                with st.spinner("Bakılıyor..."):
                    res = call_gemini_api([{"text": f"{dish} yanına ne gider?"}], "Gurmesin.", api_key)
                    st.session_state['pai_res'] = res
            else:
                st.warning("Yemek adı giriniz.")
    if 'pai_res' in st.session_state:
        st.markdown(st.session_state['pai_res'])
        render_save(st.session_state['pai_res'], "Eşleşme", "Gurme")

# 8. UYARLAMA
elif pg == "♻️ TARİF UYARLAMA":
    st.header("♻️ Uyarlama")
    val = st.session_state.get('transfer_content', '')
    with st.form("ada_form"):
        txt = st.text_area("Tarif", value=val)
        req = st.text_input("İstek (örn: glutensiz)")
        if st.form_submit_button("Uyarla", type="primary"):
            if txt and req:
                with st.spinner("Uyarlanıyor..."):
                    res = call_gemini_api([{"text": f"Bu tarifi {req} yap: {txt}"}], "Şefsin.", api_key)
                    st.session_state['ada_res'] = res
            else:
                st.warning("Bilgileri giriniz.")
    if 'ada_res' in st.session_state:
        st.markdown(st.session_state['ada_res'])
        render_save(st.session_state['ada_res'], "Uyarlama", "Uyarlama")

# 9. PORSİYON
elif pg == "± PORSİYON":
    st.header("± Porsiyon")
    val = st.session_state.get('transfer_content', '')
    with st.form("sca_form"):
        txt = st.text_area("Tarif", value=val)
        n = st.number_input("Kişi Sayısı", value=2, min_value=1)
        if st.form_submit_button("Hesapla", type="primary"):
            if txt:
                with st.spinner("Hesaplanıyor..."):
                    res = call_gemini_api([{"text": f"Bu tarifi {n} kişilik yap: {txt}"}], "Matematikçisin.", api_key)
                    st.session_state['sca_res'] = res
            else:
                st.warning("Tarif giriniz.")
    if 'sca_res' in st.session_state:
        st.markdown(st.session_state['sca_res'])
        render_save(st.session_state['sca_res'], f"Tarif ({n} Kişilik)", "Porsiyon")

# 10. DEFTER
elif pg == "📒 TARİF DEFTERİM":
    st.header("📒 Defter")
    recs = get_all_recipes()
    if not recs: st.info("Boş.")
    else:
        sel = st.selectbox("Seçiniz:", [r['id'] for r in recs], format_func=lambda x: next(r['title'] for r in recs if r['id'] == x))
        if sel:
            r = next(x for x in recs if x['id'] == sel)
            st.subheader(r['title'])
            st.markdown(r['content'])
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("🚀 Porsiyon"):
                st.session_state['transfer_content'] = r['content']; st.session_state['current_page'] = "± PORSİYON"; st.rerun()
            if c2.button("♻️ Uyarla"):
                st.session_state['transfer_content'] = r['content']; st.session_state['current_page'] = "♻️ TARİF UYARLAMA"; st.rerun()
            if c3.button("📊 Analiz"):
                st.session_state['transfer_content'] = r['content']; st.session_state['current_page'] = "📊 BESİN ANALİZİ"; st.rerun()
            if c4.button("🗑️ Sil", type="primary"):
                delete_recipe_from_db(sel); st.rerun()

# DİĞERLERİ
elif pg in ["🔄 İKAME", "⚖️ ÇEVİRİCİ", "🌡️ SAKLAMA", "📝 LİSTE"]:
    st.header(pg)
    with st.form("tool_form"):
        i = st.text_input("Girdi") if pg != "📝 LİSTE" else st.text_area("Liste")
        if st.form_submit_button("İşle", type="primary"):
            if i:
                with st.spinner("..."):
                    p = f"{i} ikamesi?" if pg=="🔄 İKAME" else (f"{i} çevir tr standart" if pg=="⚖️ ÇEVİRİCİ" else (f"{i} saklama?" if pg=="🌡️ SAKLAMA" else f"Listeyi düzenle: {i}"))
                    res = call_gemini_api([{"text": p}], "Uzmansın.", api_key)
                    st.session_state[f'res_{pg}'] = res
            else:
                st.warning("Girdi yapınız.")
    if f'res_{pg}' in st.session_state:
        st.markdown(st.session_state[f'res_{pg}'])
        render_save(st.session_state[f'res_{pg}'], "Sonuç", pg)
