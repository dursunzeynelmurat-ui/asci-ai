import streamlit as st
import requests
import base64
import json
import re
import sqlite3
import datetime

# --- API Sabitleri ve Yapılandırma ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- Veritabanı İşlemleri (SQLite) ---
def init_db():
    """Veritabanını ve tabloyu oluşturur (yoksa)."""
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
    """Tarifi veritabanına kaydeder."""
    conn = sqlite3.connect('tarifler.db')
    c = conn.cursor()
    c.execute('INSERT INTO recipes (title, content, source) VALUES (?, ?, ?)', (title, content, source))
    conn.commit()
    conn.close()

def get_all_recipes():
    """Tüm tarifleri tarihe göre sıralı getirir."""
    conn = sqlite3.connect('tarifler.db')
    conn.row_factory = sqlite3.Row # Sütun isimleriyle erişim için
    c = conn.cursor()
    c.execute('SELECT * FROM recipes ORDER BY created_at DESC')
    recipes = [dict(row) for row in c.fetchall()]
    conn.close()
    return recipes

def delete_recipe_from_db(recipe_id):
    """Tarifi siler."""
    conn = sqlite3.connect('tarifler.db')
    c = conn.cursor()
    c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    conn.commit()
    conn.close()

# Uygulama başlarken veritabanını başlat
init_db()

# --- Yardımcı Fonksiyonlar ---

def file_to_generative_part(uploaded_file):
    if uploaded_file is None: return None, None
    file_bytes = uploaded_file.read()
    base64_data = base64.b64encode(file_bytes).decode('utf-8')
    return {"inlineData": {"data": base64_data, "mimeType": uploaded_file.type}}, uploaded_file.type

def call_gemini_api(parts_list, system_instruction, api_key, use_search_grounding=False):
    if not api_key: raise ValueError("API Anahtarı bulunamadı.")
    payload = {
        "contents": [{"parts": parts_list}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
    }
    if use_search_grounding: payload["tools"] = [{"google_search": {}}]
    
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
    except Exception as e:
        st.error(f"Hata oluştu: {e}")
        return None

# --- Streamlit Uygulama Arayüzü ---

st.set_page_config(page_title="Akıllı Mutfak Asistanı", layout="wide", page_icon="👨‍🍳")

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    h1, h2, h3 { color: #0f766e; }
    
    /* Navigasyon Butonları */
    .nav-btn {
        margin: 5px; width: 100%;
    }
    div[data-testid="stHorizontalBlock"] {
        align-items: center;
    }
    
    /* Sonuç Kutuları */
    .result-box {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
        margin-top: 10px;
    }
    
    /* Toast Mesajları */
    .stToast {
        background-color: #10b981 !important;
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("👨‍🍳 Akıllı Mutfak Asistanı")

# API Anahtarı Kontrolü
api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("api_keys", {}).get("gemini")
if not api_key:
    st.error("🔑 API Anahtarı Eksik! Lütfen `secrets.toml` dosyanızı kontrol edin.")
    st.stop()

# --- Navigasyon Yönetimi ---
PAGES = {
    "🏠 ANA SAYFA": "nav_home",
    "🍽️ FOTOĞRAFTAN TARİF": "nav_detector",
    "🔎 TARİF ARAMA": "nav_search", 
    "🧊 DOLAP ŞEFİ": "nav_fridge",
    "📅 MENÜ PLANLAYICI": "nav_menu", # YENİ
    "🍷 LEZZET EŞLEŞTİRİCİ": "nav_pairing", # YENİ
    "♻️ TARİF UYARLAMA": "nav_adapt",
    "± PORSİYON": "nav_scale",
    "📒 TARİF DEFTERİM": "nav_book", 
    "🔄 İKAME": "nav_sub",
    "⚖️ ÇEVİRİCİ": "nav_conv",
    "🌡️ SAKLAMA": "nav_storage",
    "📝 LİSTE": "nav_list",
}

# Session State Başlatma
if 'current_page' not in st.session_state: st.session_state['current_page'] = "🏠 ANA SAYFA"
if 'transfer_content' not in st.session_state: st.session_state['transfer_content'] = ""

# Navigasyon Barı
with st.container():
    st.markdown("### 🚀 Hızlı Menü")
    cols = st.columns(len(PAGES))
    # Butonları 2 satıra bölmek için basit mantık (13 öğe var, 7 ve 6 olarak bölelim)
    row1_count = 7
    
    row1 = st.columns(row1_count)
    row2 = st.columns(len(PAGES) - row1_count)
    
    for i, (page_name, key) in enumerate(PAGES.items()):
        if i < row1_count:
            target_col = row1[i]
        else:
            target_col = row2[i - row1_count]
        
        with target_col:
            btn_type = "primary" if page_name == st.session_state['current_page'] else "secondary"
            if st.button(page_name, key=key, type=btn_type, use_container_width=True):
                st.session_state['current_page'] = page_name
                st.rerun()

st.markdown("---")

page = st.session_state['current_page']

# --- Ortak Kaydetme Bileşeni ---
def render_save_section(content, default_title, source_name, key_suffix):
    """Herhangi bir tarif çıktısının altına eklenebilecek standart kaydetme paneli."""
    if not content: return

    st.markdown("### 💾 Bu Tarifi/Planı Kaydet")
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            title = st.text_input("Başlık", value=default_title, key=f"title_{key_suffix}", label_visibility="collapsed", placeholder="Kayıt Adı Giriniz")
        with col2:
            if st.button("Kaydet", key=f"btn_{key_suffix}", use_container_width=True):
                if title:
                    save_recipe_to_db(title, content, source_name)
                    st.toast(f"✅ '{title}' Tarif Defterine kaydedildi!", icon="📒")
                else:
                    st.toast("⚠️ Lütfen bir başlık girin.", icon="⚠️")

# --- SAYFALAR ---

# 0. ANA SAYFA
if page == "🏠 ANA SAYFA":
    st.info("👋 Hoş Geldiniz! Yukarıdaki menüden bir araç seçerek başlayın.")
    st.markdown("""
    ### 🌟 Neler Yapabilirsiniz?
    * **📅 Menü Planlayıcı:** Diyetinize uygun günlük yemek planı oluşturun.
    * **🍷 Lezzet Eşleştirici:** Yemeğinizin yanına en iyi gidenleri bulun.
    * **🍽️ Tarif Bulucu & Dönüştürücü:** Fotoğraftan, webden veya dolabınızdan tarif üretin.
    """)
    
    # Son eklenen tarifleri göster
    recipes = get_all_recipes()
    if recipes:
        st.subheader("Son Eklenen Tarifler")
        cols = st.columns(3)
        for i, recipe in enumerate(recipes[:3]):
            with cols[i]:
                st.markdown(f"**{recipe['title']}**")
                st.caption(f"Kaynak: {recipe['source']}")
                if st.button("Görüntüle", key=f"home_view_{recipe['id']}"):
                    st.session_state['current_page'] = "📒 TARİF DEFTERİM"
                    st.rerun()

# 1. FOTOĞRAFTAN TARİF
elif page == "🍽️ FOTOĞRAFTAN TARİF":
    st.header("📸 Fotoğraftan Tarif Çıkar")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        img = st.file_uploader("Yemek Fotoğrafı Yükle", type=['jpg', 'png', 'jpeg'])
        if img: st.image(img, use_column_width=True)
        
        if st.button("Analiz Et", type="primary", disabled=not img, use_container_width=True):
            with st.spinner("Yemek analiz ediliyor..."):
                img_data = file_to_generative_part(img)
                prompt = "Bu yemeğin adı ne? Detaylı tarifi, malzemeleri ve besin değerleri nedir? Markdown formatında ver."
                res = call_gemini_api([img_data[0], {"text": "Bu yemeğin tarifini ver"}], prompt, api_key)
                st.session_state['det_res'] = res
    
    with col2:
        if 'det_res' in st.session_state and st.session_state['det_res']:
            with st.container(border=True):
                st.markdown(st.session_state['det_res'])
            # Kaydetme Alanı
            default_title = st.session_state['det_res'].split('\n')[0].replace('#', '').strip()
            render_save_section(st.session_state['det_res'], default_title, "Fotoğraf Analizi", "det")

# 2. TARİF ARAMA
elif page == "🔎 TARİF ARAMA":
    st.header("🔎 Web'den Tarif Bul")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        query = st.text_input("Yemek Adı", placeholder="Örn: İzmir Köfte")
        if st.button("Ara ve Bul", type="primary", disabled=not query, use_container_width=True):
            with st.spinner("Web taranıyor..."):
                prompt = f"'{query}' için en iyi, en popüler tam tarifi (malzemeler, yapılış) Türkçe olarak bul ve Markdown formatında sun."
                res = call_gemini_api([{"text": query}], prompt, api_key, use_search_grounding=True)
                st.session_state['search_res'] = res
                st.session_state['last_search_query'] = query
    
    with col2:
        if 'search_res' in st.session_state and st.session_state['search_res']:
            with st.container(border=True):
                st.markdown(st.session_state['search_res'])
            default_title = st.session_state.get('last_search_query', 'Yeni Tarif').title()
            render_save_section(st.session_state['search_res'], default_title, "Web Arama", "search")

# 3. DOLAP ŞEFİ
elif page == "🧊 DOLAP ŞEFİ":
    st.header("🧊 Dolap Şefi")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        img = st.file_uploader("Malzeme Fotoğrafı", type=['jpg', 'png', 'jpeg'])
        if img: st.image(img, use_column_width=True)
        
        if st.button("Fikir Üret", type="primary", disabled=not img, use_container_width=True):
            with st.spinner("Malzemeler inceleniyor..."):
                img_data = file_to_generative_part(img)
                prompt = "Bu malzemelerle yapılabilecek 3 farklı yemek fikri öner. Her fikri '### Fikir 1: Yemek Adı' formatında başlat. Sadece fikirleri ve eksik malzemeleri listele."
                res = call_gemini_api([img_data[0], {"text": "Yemek fikirleri ver"}], prompt, api_key)
                st.session_state['fridge_res'] = res
                st.session_state['generated_recipe'] = None 
    
    with col2:
        if 'fridge_res' in st.session_state and st.session_state['fridge_res']:
            if st.session_state.get('generated_recipe'):
                st.info("Seçilen Fikir İçin Tam Tarif Oluşturuldu 👇")
                with st.container(border=True):
                    st.markdown(st.session_state['generated_recipe']['content'])
                
                render_save_section(
                    st.session_state['generated_recipe']['content'], 
                    st.session_state['generated_recipe']['title'], 
                    "Dolap Şefi", 
                    "fridge_full"
                )
                if st.button("⬅️ Fikir Listesine Dön"):
                    st.session_state['generated_recipe'] = None
                    st.rerun()
            else:
                st.subheader("Önerilen Fikirler")
                st.markdown(st.session_state['fridge_res'])
                ideas = re.findall(r'### (.*?)\n', st.session_state['fridge_res'])
                if ideas:
                    st.markdown("---")
                    st.write("Beğendiğiniz fikrin tam tarifini oluşturmak için tıklayın:")
                    for idea in ideas:
                        clean_title = idea.replace('Fikir', '').replace(':', '').strip()
                        clean_title = re.sub(r'^\d+\s*', '', clean_title)
                        
                        if st.button(f"👨‍🍳 {clean_title} Tarifini Oluştur"):
                            with st.spinner(f"{clean_title} için tarif yazılıyor..."):
                                prompt = f"'{clean_title}' yemeği için, az önceki malzemeleri baz alarak 4 kişilik tam ve detaylı bir tarif yaz."
                                full_res = call_gemini_api([{"text": "Tarif oluştur"}], prompt, api_key)
                                st.session_state['generated_recipe'] = {'title': clean_title, 'content': full_res}
                                st.rerun()

# 4. GÜNLÜK MENÜ PLANLAYICI (YENİ)
elif page == "📅 MENÜ PLANLAYICI":
    st.header("📅 Günlük Menü Planlayıcı")
    st.markdown("Diyetinize ve tercihlerinize göre tüm günün yemek planını oluşturun.")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        diet_type = st.selectbox("Diyet Tipi", ["Standart", "Vejetaryen", "Vegan", "Ketojenik", "Glutensiz", "Yüksek Protein"])
        goal = st.selectbox("Hedef", ["Dengeli Beslenme", "Kilo Verme", "Enerji Artırma", "Pratik/Hızlı"])
        meals = st.multiselect("Öğünler", ["Kahvaltı", "Öğle Yemeği", "Akşam Yemeği", "Ara Öğün"], default=["Kahvaltı", "Öğle Yemeği", "Akşam Yemeği"])
        
        if st.button("Plan Oluştur", type="primary", use_container_width=True):
            with st.spinner("Günlük plan hazırlanıyor..."):
                prompt = f"{diet_type} diyeti için {goal} hedefli, şu öğünleri içeren 1 günlük örnek yemek planı oluştur: {', '.join(meals)}. Her öğün için kısa tarif ve kalori tahmini ver. Markdown formatında, tablo veya liste kullan."
                res = call_gemini_api([{"text": prompt}], "Sen uzman bir diyetisyen ve şefsin.", api_key)
                st.session_state['menu_res'] = res
                st.session_state['last_menu_info'] = f"{diet_type} Günlük Plan"

    with col2:
        if 'menu_res' in st.session_state and st.session_state['menu_res']:
            with st.container(border=True):
                st.markdown(st.session_state['menu_res'])
            render_save_section(st.session_state['menu_res'], st.session_state.get('last_menu_info', 'Günlük Plan'), "Menü Planlayıcı", "menu")

# 5. LEZZET EŞLEŞTİRİCİ (YENİ)
elif page == "🍷 LEZZET EŞLEŞTİRİCİ":
    st.header("🍷 Lezzet Eşleştirici & Tamamlayıcı")
    st.markdown("Ana yemeğinizin yanına neyin iyi gideceğini (içecek, salata, meze) öğrenin.")
    
    col1, col2 = st.columns([1, 2])
    
    # Transfer edilen içerik kontrolü (Tarif defterinden gelmiş olabilir)
    transfer_dish = st.session_state.get('transfer_content', '')
    # Eğer transfer edilen içerik uzun bir tarifse, sadece başlığı veya ilk satırı tahmin etmeye çalışabiliriz
    # Basitlik için burayı boş bırakıyoruz veya kullanıcıya bırakıyoruz, ancak transfer_content varsa inputa koyuyoruz.
    # (Burada transfer_content genellikle tarifin TAMAMI olduğu için, sadece ismini çekmek zor olabilir. 
    # Kullanıcı manuel yazsın veya tarif defterinden başlık gönderelim.)
    # Düzeltme: Tarif defterinden başlık gönderilmediği için, kullanıcı manuel girer veya transfer içeriği buraya uygun değilse temizleriz.
    if len(transfer_dish) > 100: # Muhtemelen tam tarif
        transfer_dish = "" # Temizle
    
    with col1:
        dish_name = st.text_input("Ana Yemek Adı", value=transfer_dish, placeholder="Örn: Izgara Somon, Mantı, Pizza")
        
        if st.button("Eşleşmeleri Bul", type="primary", disabled=not dish_name, use_container_width=True):
            with st.spinner("Gurme öneriler hazırlanıyor..."):
                prompt = f"'{dish_name}' yemeğinin yanına en iyi giden:\n1. İçecekler (Alkollü/Alkolsüz)\n2. Yan Lezzetler (Pilav, Püre, Salata vb.)\n3. Mezeler/Başlangıçlar\n4. Soslar\nBunları nedenleriyle birlikte öner."
                res = call_gemini_api([{"text": prompt}], "Sen bir gurmesin.", api_key)
                st.session_state['pair_res'] = res
                st.session_state['last_pair_dish'] = dish_name
                if transfer_dish: st.session_state['transfer_content'] = "" # Temizle

    with col2:
        if 'pair_res' in st.session_state and st.session_state['pair_res']:
            with st.container(border=True):
                st.markdown(st.session_state['pair_res'])
            
            def_title = f"{st.session_state.get('last_pair_dish', 'Yemek')} Eşleşmeleri"
            render_save_section(st.session_state['pair_res'], def_title, "Lezzet Eşleştirici", "pair")

# 6. TARİF UYARLAMA
elif page == "♻️ TARİF UYARLAMA":
    st.header("♻️ Tarif Uyarlama")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        default_text = st.session_state.get('transfer_content', '')
        if default_text: st.info("Bir tarif aktarıldı.")
        
        recipe_text = st.text_area("Orijinal Tarif", value=default_text, height=200, placeholder="Tarifi buraya yapıştırın...")
        request = st.text_input("İsteğiniz", placeholder="Örn: Glutensiz yap, mantar ekle...")
        
        if st.button("Uyarla", type="primary", disabled=not (recipe_text and request), use_container_width=True):
            with st.spinner("Uyarlanıyor..."):
                prompt = f"Aşağıdaki tarifi şu isteğe göre düzenle: '{request}'. \n\n{recipe_text}"
                res = call_gemini_api([{"text": prompt}], "Sen uzman bir şefsin. Sadece yeni tarifi ver.", api_key)
                st.session_state['adapt_res'] = res
                if default_text: st.session_state['transfer_content'] = ""

    with col2:
        if 'adapt_res' in st.session_state and st.session_state['adapt_res']:
            with st.container(border=True):
                st.markdown(st.session_state['adapt_res'])
            render_save_section(st.session_state['adapt_res'], "Uyarlanmış Tarif", "Uyarlama Modülü", "adapt")

# 7. PORSİYON AYARLAYICI
elif page == "± PORSİYON":
    st.header("± Porsiyon Ayarlayıcı")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        default_text = st.session_state.get('transfer_content', '')
        if default_text: st.info("Bir tarif aktarıldı.")
        
        recipe_text = st.text_area("Orijinal Tarif", value=default_text, height=200, placeholder="Tarifi buraya yapıştırın...")
        servings = st.number_input("Yeni Kişi Sayısı", min_value=1, value=4)
        
        if st.button("Hesapla", type="primary", disabled=not recipe_text, use_container_width=True):
            with st.spinner("Miktarlar hesaplanıyor..."):
                prompt = f"Bu tarifi tam olarak {servings} kişilik olacak şekilde tüm malzeme miktarlarını yeniden hesapla ve tarifi yeniden yaz.\n\n{recipe_text}"
                res = call_gemini_api([{"text": prompt}], "Sen bir mutfak matematikçisisin.", api_key)
                st.session_state['scale_res'] = res
                if default_text: st.session_state['transfer_content'] = "" 

    with col2:
        if 'scale_res' in st.session_state and st.session_state['scale_res']:
            with st.container(border=True):
                st.markdown(st.session_state['scale_res'])
            render_save_section(st.session_state['scale_res'], f"Tarif ({servings} Kişilik)", "Porsiyon Ayarlayıcı", "scale")

# 8. TARİF DEFTERİM (KALICI HAFIZA)
elif page == "📒 TARİF DEFTERİM":
    st.header("📒 Tarif Defterim")
    
    recipes = get_all_recipes()
    
    if not recipes:
        st.info("Henüz kaydedilmiş bir tarifiniz yok. Diğer araçları kullanarak tarif oluşturun ve kaydedin!")
    else:
        col_list, col_view = st.columns([1, 3])
        
        with col_list:
            st.subheader("Liste")
            selected_id = st.radio(
                "Tarif Seçin:", 
                [r['id'] for r in recipes], 
                format_func=lambda x: next(r['title'] for r in recipes if r['id'] == x)
            )
        
        with col_view:
            if selected_id:
                recipe = next(r for r in recipes if r['id'] == selected_id)
                
                st.markdown(f"## {recipe['title']}")
                st.caption(f"📅 {recipe['created_at']} | 🔗 Kaynak: {recipe['source']}")
                st.markdown("---")
                
                with st.container(border=True):
                    st.markdown(recipe['content'])
                
                st.markdown("### İşlemler")
                ac1, ac2, ac3, ac4 = st.columns(4)
                
                with ac1:
                    if st.button("🚀 Porsiyonla", help="Porsiyon Ayarlayıcıya gönder"):
                        st.session_state['transfer_content'] = recipe['content']
                        st.session_state['current_page'] = "± PORSİYON"
                        st.rerun()
                
                with ac2:
                    if st.button("♻️ Uyarla", help="Uyarlama aracına gönder"):
                        st.session_state['transfer_content'] = recipe['content']
                        st.session_state['current_page'] = "♻️ TARİF UYARLAMA"
                        st.rerun()
                
                with ac3:
                    if st.button("🍷 Eşleştir", help="Lezzet Eşleştiriciye gönder (Sadece başlık)"):
                        # Eşleştiriciye sadece başlığı göndermek daha mantıklı
                        st.session_state['transfer_content'] = recipe['title']
                        st.session_state['current_page'] = "🍷 LEZZET EŞLEŞTİRİCİ"
                        st.rerun()

                with ac4:
                    if st.button("🗑️ Sil", type="primary"):
                        delete_recipe_from_db(recipe['id'])
                        st.toast("Tarif silindi!", icon="🗑️")
                        st.rerun()

# Diğer basit araçlar
elif page in ["🔄 İKAME", "⚖️ ÇEVİRİCİ", "🌡️ SAKLAMA", "📝 LİSTE"]:
    st.header(page)
    
    if page == "🔄 İKAME":
        inp = st.text_input("Malzeme", placeholder="Örn: Yumurta")
        reason = st.text_input("Amaç (Opsiyonel)", placeholder="Vegan olması için")
        btn_txt = "İkame Bul"
        prompt_tmpl = "Bunun yerine ne kullanabilirim: {inp}. Amaç: {reason}."
        
    elif page == "⚖️ ÇEVİRİCİ":
        inp = st.text_input("Çevrilecek Ölçü", placeholder="Örn: 1 bardak un kaç gram?")
        reason = ""
        btn_txt = "Çevir"
        prompt_tmpl = "Mutfak ölçüsü çevirisi yap: {inp}. Türk standartlarını kullan."
        
    elif page == "🌡️ SAKLAMA":
        inp = st.text_input("Yemek/Gıda", placeholder="Örn: Pişmiş Tavuk")
        reason = ""
        btn_txt = "Bilgi Al"
        prompt_tmpl = "{inp} için güvenli saklama süreleri (dolap/buzluk) ve saklama koşulları nedir?"
        
    elif page == "📝 LİSTE":
        inp = st.text_area("Dağınık Liste", height=150)
        reason = ""
        btn_txt = "Düzenle"
        prompt_tmpl = "Bu alışveriş listesini market reyonlarına göre kategorize et ve birleştir: {inp}"

    if st.button(btn_txt, type="primary", disabled=not inp):
        with st.spinner("İşleniyor..."):
            final_prompt = prompt_tmpl.format(inp=inp, reason=reason)
            res = call_gemini_api([{"text": final_prompt}], "Sen uzman bir mutfak asistanısın.", api_key)
            st.session_state[f'res_{page}'] = res
    
    if f'res_{page}' in st.session_state and st.session_state[f'res_{page}']:
        with st.container(border=True):
            st.markdown(st.session_state[f'res_{page}'])
        
        def_title = "Alışveriş Listesi" if page == "📝 LİSTE" else (inp if len(inp)<20 else inp[:20])
        render_save_section(st.session_state[f'res_{page}'], def_title, page, "tool")
