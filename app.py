import streamlit as st
import requests
import base64
import json
import re
import sqlite3
import datetime
import time
import random

# --- Sayfa Yapılandırması (En başta olmalı) ---
st.set_page_config(
    page_title="Akıllı Mutfak Asistanı", 
    layout="wide", 
    page_icon="👨‍🍳",
    initial_sidebar_state="collapsed"
)

# --- API Sabitleri ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- Veritabanı İşlemleri (SQLite) ---
def init_db():
    conn = sqlite3.connect('tarifler.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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
    if not api_key: return None # Hata UI tarafında gösterilir
    
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
            if not text: raise Exception("API'den geçerli metin yanıtı alınamadı.")
            return text

        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [500, 502, 503, 504]:
                if attempt < max_retries - 1:
                    time.sleep((2 ** attempt) + random.random())
                    continue
                else:
                    st.error(f"Sunucu yanıt vermiyor (Hata {e.response.status_code}).")
                    return None
            else:
                st.error(f"API Hatası: {e}")
                return None
        except Exception as e:
            st.error(f"Hata: {e}")
            return None

# --- Modern UI & CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Poppins', sans-serif;
    }
    
    .stApp {
        background-color: #f8fafc;
    }
    
    /* Başlıklar */
    h1, h2, h3 {
        color: #0f766e;
        font-weight: 700;
    }
    
    /* Dashboard Kartları için Buton Stili */
    .stButton button {
        border-radius: 12px;
        height: auto;
        min-height: 50px;
        border: 1px solid #e2e8f0;
        background-color: white;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
        color: #334155;
        font-weight: 600;
        font-size: 16px;
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border-color: #10b981;
        color: #10b981;
    }
    
    /* Form Gönder Butonları (Primary) */
    div[data-testid="stForm"] button[kind="primary"] {
        background-color: #10b981;
        color: white;
        border: none;
    }
    div[data-testid="stForm"] button[kind="primary"]:hover {
        background-color: #059669;
        color: white;
    }

    /* Chat Kutusu */
    .stChatMessage {
        background-color: white;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Başarı Mesajları */
    .stToast {
        background-color: #10b981 !important;
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- Session State ---
if 'current_page' not in st.session_state: st.session_state['current_page'] = "HOME"
if 'transfer_content' not in st.session_state: st.session_state['transfer_content'] = ""
if 'chat_messages' not in st.session_state: st.session_state['chat_messages'] = []
if 'saved_recipes' not in st.session_state: st.session_state['saved_recipes'] = []

# --- API Anahtarı Kontrolü ---
api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("api_keys", {}).get("gemini")

# --- Ana Başlık Alanı ---
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown("# 👨‍🍳")
with col_title:
    if st.session_state['current_page'] == "HOME":
        st.markdown("# Akıllı Mutfak Asistanı")
        st.markdown("*Yapay zeka destekli kişisel şefiniz ve mutfak yöneticiniz.*")
    else:
        c1, c2 = st.columns([1, 5])
        with c1:
            if st.button("🏠 Ana Menü", key="go_home_btn"):
                st.session_state['current_page'] = "HOME"
                st.rerun()
        with c2:
            page_titles = {
                "DETECTOR": "Fotoğraftan Tarif Çıkar",
                "SEARCH": "Web'den Tarif Bul",
                "FRIDGE": "Dolap Şefi",
                "CHAT": "Mutfak Gurusu",
                "MENU": "Menü Planlayıcı",
                "PAIRING": "Lezzet Eşleştirici",
                "NUTRITION": "Besin Analizi",
                "ADAPT": "Tarif Uyarlama",
                "SCALE": "Porsiyon Ayarlayıcı",
                "BOOK": "Tarif Defterim",
                "SUB": "Malzeme İkamesi",
                "CONV": "Ölçü Çevirici",
                "STORAGE": "Saklama Rehberi",
                "LIST": "Alışveriş Listesi"
            }
            st.markdown(f"### {page_titles.get(st.session_state['current_page'], '')}")

st.markdown("---")

if not api_key:
    st.error("🔑 API Anahtarı bulunamadı! Lütfen `secrets.toml` dosyanızı kontrol edin.")
    st.stop()

# ==============================================================================
# 🏠 DASHBOARD (ANA SAYFA)
# ==============================================================================
if st.session_state['current_page'] == "HOME":
    
    st.subheader("🔍 Keşfet & Bul")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📸 Fotoğraftan Tarif", use_container_width=True): st.session_state['current_page'] = "DETECTOR"; st.rerun()
    with c2:
        if st.button("🔎 Tarif Arama (Web)", use_container_width=True): st.session_state['current_page'] = "SEARCH"; st.rerun()
    with c3:
        if st.button("🧊 Dolap Şefi", use_container_width=True): st.session_state['current_page'] = "FRIDGE"; st.rerun()

    st.markdown("###") 

    st.subheader("🤖 Şefin Asistanı")
    c4, c5, c6, c7 = st.columns(4)
    with c4:
        if st.button("💬 Mutfak Gurusu", use_container_width=True): st.session_state['current_page'] = "CHAT"; st.rerun()
    with c5:
        if st.button("📅 Menü Planlayıcı", use_container_width=True): st.session_state['current_page'] = "MENU"; st.rerun()
    with c6:
        if st.button("🍷 Lezzet Eşleştirici", use_container_width=True): st.session_state['current_page'] = "PAIRING"; st.rerun()
    with c7:
        if st.button("📊 Besin Analizi", use_container_width=True): st.session_state['current_page'] = "NUTRITION"; st.rerun()

    st.markdown("###") 

    st.subheader("🧮 Hesap & Kitap")
    c8, c9, c10, c11, c12, c13 = st.columns(6)
    with c8:
        if st.button("± Porsiyon", use_container_width=True): st.session_state['current_page'] = "SCALE"; st.rerun()
    with c9:
        if st.button("♻️ Uyarlama", use_container_width=True): st.session_state['current_page'] = "ADAPT"; st.rerun()
    with c10:
        if st.button("🔄 İkame", use_container_width=True): st.session_state['current_page'] = "SUB"; st.rerun()
    with c11:
        if st.button("⚖️ Çevirici", use_container_width=True): st.session_state['current_page'] = "CONV"; st.rerun()
    with c12:
        if st.button("🌡️ Saklama", use_container_width=True): st.session_state['current_page'] = "STORAGE"; st.rerun()
    with c13:
        if st.button("📝 Liste", use_container_width=True): st.session_state['current_page'] = "LIST"; st.rerun()

    st.markdown("###")

    st.subheader("📚 Kütüphane")
    if st.button("📒 Tarif Defterim", type="primary", use_container_width=True): st.session_state['current_page'] = "BOOK"; st.rerun()

# ==============================================================================
# ALT SAYFALAR
# ==============================================================================

def render_save(content, default_title, source):
    if content:
        st.markdown("---")
        with st.expander("💾 Kaydet", expanded=True):
            with st.form(key=f"save_form_{source}"): # Kayıt için de form kullanıyoruz
                c1, c2 = st.columns([3, 1])
                title = c1.text_input("Kayıt Başlığı", value=default_title)
                submitted = c2.form_submit_button("Kaydet", use_container_width=True)
                if submitted:
                    if title:
                        save_recipe_to_db(title, content, source)
                        st.toast("Kayıt Başarılı!", icon="✅")
                    else:
                        st.toast("Başlık giriniz", icon="⚠️")

# 1. FOTOĞRAFTAN TARİF (Form kullanılmadı, dosya yükleme Enter ile tetiklenmez)
if st.session_state['current_page'] == "DETECTOR":
    c1, c2 = st.columns([1, 2])
    with c1:
        img = st.file_uploader("Yemek Fotoğrafı", type=['jpg', 'png'])
        if img: st.image(img, use_column_width=True)
        if st.button("Analiz Et", type="primary", use_container_width=True, disabled=not img):
            with st.spinner("Analiz ediliyor..."):
                res = call_gemini_api([file_to_generative_part(img)[0], {"text": "Bu yemeğin detaylı tarifini ver"}], "Sen bir şefsin.", api_key)
                st.session_state['det_res'] = res
    with c2:
        if 'det_res' in st.session_state:
            st.markdown(st.session_state['det_res'])
            render_save(st.session_state['det_res'], "Yeni Tarif", "Fotoğraf")

# 2. TARİF ARAMA (Form Eklendi - Enter çalışır)
elif st.session_state['current_page'] == "SEARCH":
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.form(key='search_form'):
            q = st.text_input("Yemek Adı", placeholder="Örn: Karnıyarık")
            submit_search = st.form_submit_button("Bul", type="primary", use_container_width=True, disabled=not q)
        
        if submit_search:
            with st.spinner("Aranıyor..."):
                res = call_gemini_api([{"text": f"'{q}' tarifi"}], "En iyi tarifi bul ve detaylı yaz.", api_key, True)
                st.session_state['search_res'] = res
                st.session_state['search_q'] = q
    with c2:
        if 'search_res' in st.session_state:
            st.markdown(st.session_state['search_res'])
            render_save(st.session_state['search_res'], st.session_state.get('search_q', 'Tarif'), "Arama")

# 3. DOLAP ŞEFİ (Form kullanılmadı, dosya yükleme)
elif st.session_state['current_page'] == "FRIDGE":
    c1, c2 = st.columns([1, 2])
    with c1:
        img = st.file_uploader("Malzeme Fotoğrafı", type=['jpg', 'png'])
        if img: st.image(img, use_column_width=True)
        if st.button("Fikir Ver", type="primary", use_container_width=True, disabled=not img):
            with st.spinner("Düşünülüyor..."):
                res = call_gemini_api([file_to_generative_part(img)[0], {"text": "Neler yapabilirim?"}], "3 yemek fikri öner. Başlıkları '### Fikir X: İsim' yap.", api_key)
                st.session_state['fridge_res'] = res
                st.session_state['fridge_full'] = None
    with c2:
        if st.session_state.get('fridge_full'):
            st.info("Seçilen Tarif 👇")
            st.markdown(st.session_state['fridge_full']['content'])
            render_save(st.session_state['fridge_full']['content'], st.session_state['fridge_full']['title'], "Dolap Şefi")
            if st.button("Geri Dön"): st.session_state['fridge_full'] = None; st.rerun()
        elif 'fridge_res' in st.session_state:
            st.markdown(st.session_state['fridge_res'])
            ideas = re.findall(r'### (.*?)\n', st.session_state['fridge_res'])
            if ideas:
                st.write("Tam tarif için seçin:")
                for idea in ideas:
                    name = idea.split(':')[-1].strip()
                    if st.button(f"🍳 {name} Yap"):
                        with st.spinner("Tarif yazılıyor..."):
                            full = call_gemini_api([{"text": f"'{name}' için 4 kişilik tam tarif yaz"}], "Uzman şef.", api_key)
                            st.session_state['fridge_full'] = {'title': name, 'content': full}
                            st.rerun()

# 4. MUTFAK GURUSU (Chat Input zaten Enter ile çalışır)
elif st.session_state['current_page'] == "CHAT":
    for m in st.session_state['chat_messages']:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    
    if p := st.chat_input("Bir soru sor..."):
        st.session_state['chat_messages'].append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        with st.chat_message("assistant"):
            with st.spinner("..."):
                hist = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state['chat_messages'][-5:]])
                res = call_gemini_api([{"text": p}], f"Sen mutfak gurususun. Kısa, öz ve esprili ol.\n{hist}", api_key)
                st.markdown(res)
                st.session_state['chat_messages'].append({"role": "assistant", "content": res})

# 5. BESİN ANALİZİ (Form Eklendi)
elif st.session_state['current_page'] == "NUTRITION":
    t_content = st.session_state.get('transfer_content', '')
    if len(t_content) > 200:
        default_txt = t_content
        st.info("Tarif aktarıldı.")
    else:
        default_txt = ""
    
    with st.form(key='nutri_form'):
        txt = st.text_area("Tarif Metni (Ctrl+Enter ile gönder)", value=default_txt, height=200)
        submit_nutri = st.form_submit_button("Analiz Et", type="primary", use_container_width=True)
    
    if submit_nutri:
        with st.spinner("Hesaplanıyor..."):
            res = call_gemini_api([{"text": f"Bu tarifin besin değerlerini (kalori, protein, yağ, karb) hesapla: {txt}"}], "Diyetisyensin.", api_key)
            st.session_state['nutri_res'] = res
            if default_txt: st.session_state['transfer_content'] = ""
    
    if 'nutri_res' in st.session_state:
        st.markdown(st.session_state['nutri_res'])
        render_save(st.session_state['nutri_res'], "Besin Analizi", "Analizör")

# 6. MENÜ PLANLAYICI (Form Eklendi)
elif st.session_state['current_page'] == "MENU":
    with st.form(key='menu_form'):
        c1, c2 = st.columns(2)
        with c1: diet = st.selectbox("Diyet", ["Standart", "Vegan", "Ketojenik", "Glutensiz"])
        with c2: goal = st.selectbox("Hedef", ["Sağlıklı Yaşam", "Kilo Verme", "Kas Yapma"])
        submit_menu = st.form_submit_button("Plan Oluştur", type="primary", use_container_width=True)
    
    if submit_menu:
        with st.spinner("Planlanıyor..."):
            res = call_gemini_api([{"text": f"{diet} diyeti ve {goal} hedefi için 1 günlük örnek menü."}], "Diyetisyensin.", api_key)
            st.session_state['menu_res'] = res
    if 'menu_res' in st.session_state:
        st.markdown(st.session_state['menu_res'])
        render_save(st.session_state['menu_res'], f"{diet} Menü", "Planlayıcı")

# 7. LEZZET EŞLEŞTİRİCİ (Form Eklendi - Enter çalışır)
elif st.session_state['current_page'] == "PAIRING":
    t_name = st.session_state.get('transfer_content', '')
    val = t_name if len(t_name) < 100 else ""
    
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.form(key='pair_form'):
            dish = st.text_input("Yemek Adı", value=val, placeholder="Örn: Izgara Somon")
            submit_pair = st.form_submit_button("Eşleşmeleri Bul", type="primary", use_container_width=True, disabled=not dish)
        
        if submit_pair:
            with st.spinner("Öneriliyor..."):
                res = call_gemini_api([{"text": f"{dish} yanına ne gider? İçecek, yan yemek, meze öner."}], "Gurmesin.", api_key)
                st.session_state['pair_res'] = res
                if val: st.session_state['transfer_content'] = ""
    with c2:
        if 'pair_res' in st.session_state:
            st.markdown(st.session_state['pair_res'])
            render_save(st.session_state['pair_res'], f"{dish} Eşleşmeleri", "Gurme")

# 8. TARİF UYARLAMA (Form Eklendi)
elif st.session_state['current_page'] == "ADAPT":
    t_cont = st.session_state.get('transfer_content', '')
    val = t_cont if len(t_cont) > 100 else ""
    
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.form(key='adapt_form'):
            txt = st.text_area("Orijinal Tarif", value=val, height=150)
            req = st.text_input("İsteğiniz", placeholder="Örn: Glutensiz yap")
            submit_adapt = st.form_submit_button("Uyarla", type="primary", use_container_width=True, disabled=not (txt and req))
        
        if submit_adapt:
            with st.spinner("Uyarlanıyor..."):
                res = call_gemini_api([{"text": f"Bu tarifi şuna göre düzenle: {req}\n\n{txt}"}], "Şefsin.", api_key)
                st.session_state['adapt_res'] = res
                if val: st.session_state['transfer_content'] = ""
    with c2:
        if 'adapt_res' in st.session_state:
            st.markdown(st.session_state['adapt_res'])
            render_save(st.session_state['adapt_res'], "Uyarlanmış Tarif", "Uyarlama")

# 9. PORSİYON AYARLAYICI (Form Eklendi)
elif st.session_state['current_page'] == "SCALE":
    t_cont = st.session_state.get('transfer_content', '')
    val = t_cont if len(t_cont) > 100 else ""
    
    c1, c2 = st.columns([1, 2])
    with c1:
        with st.form(key='scale_form'):
            txt = st.text_area("Orijinal Tarif", value=val, height=150)
            srv = st.number_input("Yeni Kişi Sayısı", value=4, min_value=1)
            submit_scale = st.form_submit_button("Hesapla", type="primary", use_container_width=True, disabled=not txt)
        
        if submit_scale:
            with st.spinner("Hesaplanıyor..."):
                res = call_gemini_api([{"text": f"Bu tarifi {srv} kişilik olacak şekilde güncelle:\n{txt}"}], "Matematikçi şefsin.", api_key)
                st.session_state['scale_res'] = res
                if val: st.session_state['transfer_content'] = ""
    with c2:
        if 'scale_res' in st.session_state:
            st.markdown(st.session_state['scale_res'])
            render_save(st.session_state['scale_res'], f"Tarif ({srv} Kişilik)", "Porsiyon")

# 10. TARİF DEFTERİM
elif st.session_state['current_page'] == "BOOK":
    recipes = get_all_recipes()
    if not recipes:
        st.info("Defteriniz boş.")
    else:
        c1, c2 = st.columns([1, 3])
        with c1:
            selected_id = st.radio("Tarifler", [r['id'] for r in recipes], format_func=lambda x: next(r['title'] for r in recipes if r['id'] == x))
        with c2:
            if selected_id:
                r = next(x for x in recipes if x['id'] == selected_id)
                st.subheader(r['title'])
                st.caption(f"Kaynak: {r['source']} | Tarih: {r['created_at']}")
                with st.container(border=True): st.markdown(r['content'])
                
                st.markdown("##### İşlemler")
                b1, b2, b3, b4, b5 = st.columns(5)
                if b1.button("🚀 Porsiyon", use_container_width=True):
                    st.session_state['transfer_content'] = r['content']
                    st.session_state['current_page'] = "SCALE"
                    st.rerun()
                if b2.button("♻️ Uyarla", use_container_width=True):
                    st.session_state['transfer_content'] = r['content']
                    st.session_state['current_page'] = "ADAPT"
                    st.rerun()
                if b3.button("🍷 Eşleştir", use_container_width=True):
                    st.session_state['transfer_content'] = r['title']
                    st.session_state['current_page'] = "PAIRING"
                    st.rerun()
                if b4.button("📊 Analiz", use_container_width=True):
                    st.session_state['transfer_content'] = r['content']
                    st.session_state['current_page'] = "NUTRITION"
                    st.rerun()
                if b5.button("🗑️ Sil", type="primary", use_container_width=True):
                    delete_recipe_from_db(r['id'])
                    st.rerun()

# DİĞER ARAÇLAR (Form Eklendi - Enter çalışır)
elif st.session_state['current_page'] in ["SUB", "CONV", "STORAGE", "LIST"]:
    cp = st.session_state['current_page']
    c1, c2 = st.columns([1, 1])
    with c1:
        with st.form(key=f'form_{cp}'):
            if cp == "SUB":
                i = st.text_input("Malzeme", placeholder="Örn: Yumurta")
                reason = st.text_input("Amaç (Opsiyonel)", placeholder="Vegan olması için")
                btn_txt, prompt_tmpl = "İkame Bul", "Bunun yerine ne kullanabilirim: {inp}. Amaç: {reason}."
            elif cp == "CONV":
                i = st.text_input("Çeviri (Örn: 1 bardak un kaç gr)")
                reason = ""
                btn_txt, prompt_tmpl = "Çevir", "Mutfak ölçüsü çevirisi yap: {inp}. Türk standartlarını kullan."
            elif cp == "STORAGE":
                i = st.text_input("Yemek", placeholder="Örn: Pişmiş Tavuk")
                reason = ""
                btn_txt, prompt_tmpl = "Bilgi Al", "{inp} için güvenli saklama süreleri (dolap/buzluk) ve saklama koşulları nedir?"
            elif cp == "LIST":
                i = st.text_area("Liste (Ctrl+Enter)", height=150)
                reason = ""
                btn_txt, prompt_tmpl = "Düzenle", "Bu alışveriş listesini market reyonlarına göre kategorize et ve birleştir: {inp}"

            submitted = st.form_submit_button(btn_txt, type="primary", disabled=not i)
        
        if submitted:
            with st.spinner("İşleniyor..."):
                final_prompt = prompt_tmpl.format(inp=inp, reason=reason)
                res = call_gemini_api([{"text": final_prompt}], "Sen uzman bir mutfak asistanısın.", api_key)
                st.session_state[f'res_{page}'] = res
    
    with c2:
        # Session state key mapping
        k = f'res_{cp}' # Doğrudan sayfa adını key olarak kullanalım (daha önceki karmaşıklığı önlemek için)
        
        if k in st.session_state and st.session_state[k]:
            with st.container(border=True): st.markdown(st.session_state[k])
            def_title = "Alışveriş Listesi" if cp == "LIST" else (i if len(i)<20 else i[:20])
            render_save(st.session_state[k], def_title, cp)
