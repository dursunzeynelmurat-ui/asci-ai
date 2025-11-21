import streamlit as st
import requests
import base64
import json
import re

# --- API Sabitleri ve Yapılandırma ---
# Gemini API URL'si
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- Yardımcı Fonksiyonlar ---

def file_to_generative_part(uploaded_file):
    """Yüklenen dosyayı Base64 verisine çevirir ve Gemini API formatına hazırlar."""
    if uploaded_file is None:
        return None, None

    # Dosyayı bellekte oku
    file_bytes = uploaded_file.read()
    
    # Base64 formatına çevir
    base64_data = base64.b64encode(file_bytes).decode('utf-8')
    mime_type = uploaded_file.type

    # Gemini API'nin beklediği format
    return {
        "inlineData": {
            "data": base64_data,
            "mimeType": mime_type
        }
    }, mime_type

def call_gemini_api(parts_list, system_instruction, api_key):
    """
    Gemini API'ye istek gönderir ve yanıtı işler.
    """
    if not api_key:
        raise ValueError("API Anahtarı bulunamadı.")

    # Multimodal istekler için doğru JSON yapısı
    payload = {
        "contents": [
            {
                "parts": parts_list
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
    }

    headers = {
        'Content-Type': 'application/json'
    }

    # API Anahtarını doğrudan URL'ye ekliyoruz
    full_url = f"{GEMINI_API_URL}?key={api_key}"
    
    # API'ye istek gönderme ve hata yönetimi
    # Exponential backoff mekanizması olmadan basit bir istek gönderme
    try:
        response = requests.post(full_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # 4xx veya 5xx hatalarını HTTPError olarak fırlatır

        # Yanıtı JSON olarak ayrıştırma
        result = response.json()
        
        # Metin içeriğini çıkar
        candidate = result.get('candidates', [None])[0]
        text = candidate.get('content', {}).get('parts', [{}])[0].get('text') if candidate else None

        if not text:
            # Geçerli metin yanıtı yoksa hata mesajını kontrol et
            error_message = result.get('error', {}).get('message', 'Bilinmeyen bir API yanıt hatası.')
            raise Exception(f"API'den geçerli metin yanıtı alınamadı. Hata: {error_message}")
        
        return text

    except requests.exceptions.HTTPError as e:
        status_code = response.status_code
        
        if status_code == 401:
            st.error("❌ API Hatası 401 (Yetkilendirme Başarısız)")
            st.warning("Lütfen API anahtarınızın doğru ve aktif olduğundan emin olun.")
        elif status_code == 400:
             st.error("❌ API Hatası 400 (Geçersiz İstek)")
             st.warning("Girdi formatınız (resim/metin) ya da API çağrısının yapısı hatalı olabilir. Detaylar için aşağıdaki hata mesajını inceleyin.")
        else:
            st.error(f"❌ HTTP Hatası {status_code}: İstek başarısız oldu.")
        
        # Hata detaylarını göster
        error_details = response.text
        with st.expander("Gelişmiş Hata Detayları"):
            st.code(error_details, language='json')
        return None
    
    except Exception as e:
        st.error(f"❌ Beklenmedik bir hata oluştu: {e}")
        return None

def generate_full_recipe(idea_name, ingredient_list, api_key):
    """Dolap Şefi'nden gelen bir fikre dayanarak tam bir tarif oluşturur."""
    st.subheader(f"'{idea_name}' İçin Tam Tarif Oluşturuluyor...")
    
    system_prompt_full = "Sen uzman bir şefsin. Görevin, verilen yemek fikri ve malzeme listesine dayanarak, mantıklı bir porsiyon sayısıyla (örneğin 4 kişilik) TAM ve detaylı bir tarif (malzemeler ve yapılış aşamaları) hazırlamaktır. Tüm çıktı TAMAMEN Türkçe ve iyi formatlanmış Markdown başlıkları ve listeleri kullanmalıdır."
    
    user_query_full = f"Aşağıdaki yemek fikri için, belirtilen mevcut malzemeleri de kullanarak, eksik malzemeleri tamamlayarak 4 kişilik tam bir tarif oluştur. Fikir adı: '{idea_name}'. Mevcut malzemeler: {ingredient_list}. Yeni tarif porsiyon sayısıyla başlamalı ve tam malzeme listesini, ardından detaylı yapılış aşamalarını içermelidir."
    
    parts_list_full = [
        {"text": user_query_full}
    ]

    result_text_full = call_gemini_api(parts_list_full, system_prompt_full, api_key)
    return result_text_full

def parse_fridge_suggestions(markdown_text):
    """
    Dolap Şefi'nin Markdown çıktısını 3 ayrı fikre böler.
    Her fikri {'title': ..., 'content': ...} olarak döndürür.
    Markdown çıktısının Yemek Fikri 1, Yemek Fikri 2, Yemek Fikri 3 başlıklarını kullandığını varsayar.
    """
    if not markdown_text:
        return []
    
    # Genişletilmiş regex: Başlık ve bir sonraki başlık veya metin sonu arasındaki her şeyi yakalar
    # Başlıklar genelde ## veya ### ile başlar
    suggestions = re.split(r'^(#+\s*Yemek Fikri\s*\d+):', markdown_text, flags=re.MULTILINE)
    
    # İlk eleman (bazen boş veya giriş metni) atılır
    suggestions.pop(0)

    parsed_list = []
    
    for i in range(0, len(suggestions), 2):
        # Başlık formatı: "# Yemek Fikri 1"
        raw_title = suggestions[i].strip()
        
        # İçerik: Bir sonraki eleman
        content = suggestions[i+1].strip()
        
        # Sadece yemek fikrinin adını çıkarmaya çalışalım (örn: "Kremalı Mantarlı Makarna" gibi)
        # Basitlik için, başlığı kullanıyoruz.
        parsed_list.append({
            'title': raw_title.replace('#', '').strip(), # Başlık işaretlerini kaldır
            'content': content
        })

    # Eğer ayrıştırma başarısız olursa, tüm metni tek bir sonuç olarak döndür
    if not parsed_list and markdown_text:
        return [{'title': "Dolap Şefi Analizi", 'content': markdown_text}]

    return parsed_list


# --- Streamlit Uygulama Arayüzü ---

st.set_page_config(page_title="Akıllı Mutfak Asistanı", layout="wide")

# Özel CSS ile arayüzü güzelleştirme
st.markdown("""
    <style>
    .stApp {
        background-color: #f7f9fb;
    }
    /* Ana içerik alanındaki başlıkları ve konteynerleri stilize etme */
    h1, h2, h3 {
        color: #10b981; /* Zümrüt Yeşili */
    }
    .results-container {
        padding: 16px;
        border-radius: 8px;
        background-color: #ffffff;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.06);
        min-height: 400px; 
    }
    /* Sidebar'ı biraz daha belirgin hale getirme */
    .css-1d391kg { /* sidebar container class */
        background-color: #e0f2f1; /* Açık Zümrüt Yeşili */
        border-right: 1px solid #10b981;
    }
    </style>
""", unsafe_allow_html=True)

st.title("👨‍🍳 Akıllı Mutfak Asistanınız")
st.markdown("""
    Yapay zekanın gücüyle mutfağınızı dönüştürün! Gemini, yemek fotoğraflarınızı analiz eder, tarifler çıkarır, elinizdeki malzemelerle yaratıcı yemekler önerir, ölçü birimi çevirileri yapar, porsiyonları ayarlar ve tariflerinizi kaydeder!
""")

# ==============================================================================
# API Anahtarı Yönetimi - Sadece secrets.toml'dan oku
# ==============================================================================

# API anahtarını sadece secrets'tan al
api_key = st.secrets.get("GEMINI_API_KEY")
if not api_key:
    api_key = st.secrets.get("api_keys", {}).get("gemini")

# Anahtarın durumunu kontrol et
if not api_key:
    st.error("🔑 API Anahtarı Eksik")
    st.warning("Lütfen Gemini API anahtarınızı `.streamlit/secrets.toml` dosyanıza `GEMINI_API_KEY` adıyla ekleyin.")
# ==============================================================================

# --- Oturum Durumu (Session State) Başlatma ---
# Kaydedilen tarifler için oturum durumu listesi
if 'saved_recipes' not in st.session_state:
    st.session_state['saved_recipes'] = []

# Dolap şefi için son öneri çıktısı
if 'last_fridge_output' not in st.session_state:
    st.session_state['last_fridge_output'] = ""

# Dolap şefi için tam tarif çıktısı
if 'generated_full_recipe' not in st.session_state:
    st.session_state['generated_full_recipe'] = None # {'title': '', 'content': ''}

# --- Yan Panel (Sidebar) Navigasyonu ---
st.sidebar.title("🛠️ Mutfak Araçları")

# Sayfa seçenekleri 
PAGES = {
    "🍽️ Tarif DEDEKTÖRÜ": "Yemek Fotoğrafından Tarifi Çözümle",
    "🧊 DOLAP ŞEFİ": "Malzeme Fotoğrafından Yemek Önerileri",
    "♻️ TARİF UYARLAMA": "Tarif Uyarlama ve Değiştirme",
    "± PORSİYON AYARLAYICI": "Tarif Porsiyonunu Otomatik Hesapla",
    "📒 TARİFLERİM": "Kayıtlı Tarifleriniz", 
    "🔄 MALZEME İKAMESİ": "Malzeme İkamesi Bulucu",
    "⚖️ ÖLÇÜ ÇEVİRİCİ": "Malzemeye Özel Ölçü Çevirici (Hacim 🔄 Ağırlık)"
}

selected_page = st.sidebar.selectbox(
    "Lütfen bir araç seçin:",
    list(PAGES.keys())
)

st.sidebar.markdown("---")
st.sidebar.info("Yan paneldeki menüyü kullanarak araçlar arasında hızla geçiş yapabilirsiniz.")

# --- Ana İçerik Alanı (Koşullu Renderlama) ---

# --- 1. Tarif Keşfetme Alanı ---
if selected_page == "🍽️ Tarif DEDEKTÖRÜ":
    st.header(PAGES[selected_page])
    st.markdown("Bir tabak yemeğin veya hazırladığınız yemeğin fotoğrafını yükleyin, Yapay Zeka anında tarifi, besin değerlerini ve alışveriş listenizi çıkarsın!")
    
    col1, col2 = st.columns([1, 2]) # Giriş alanı 1/3, sonuç alanı 2/3
    
    with col1:
        uploaded_file = st.file_uploader("📸 Yemeğin Fotoğrafını Yükle/Çek", type=['png', 'jpg', 'jpeg'], key="recipe_upload", help="Yemeğinizin net ve aydınlık bir fotoğrafını çekin.")
        
        is_recipe_ready = bool(api_key and uploaded_file) 

        if uploaded_file is not None:
            st.image(uploaded_file, caption='Yemek Önizleme', use_column_width=True)
            
        if not is_recipe_ready and api_key and uploaded_file is None:
            st.info("Butonu etkinleştirmek için lütfen bir resim yükleyin.")


        if st.button("🍽️ Tarif ve Besin Değerlerini Çıkar", key="generate_recipe_btn", disabled=not is_recipe_ready, use_container_width=True):
            if is_recipe_ready:
                with st.spinner('Tarif ve besin değerleri analiz ediliyor...'):
                    try:
                        image_part, mime_type = file_to_generative_part(uploaded_file)
                        
                        system_prompt = "Sen profesyonel bir aşçı ve beslenme uzmanısısın. Görev, resimdeki yemeği en ince ayrıntısına kadar analiz etmek ve TAMAMEN Türkçe olarak, aşağıda belirtilen formatta detaylı bilgi sağlamaktır. Yanıtını iyi formatlanmış Markdown başlıkları, kalın metinler ve listeler kullanarak hazırla."
                        
                        user_query = f"Bu pişmiş bir yemeğin fotoğrafı. Lütfen tam tarifi, gerekli malzemelerin alışveriş listesini (temel mutfak malzemeleri hariç, örneğin su, tuz, karabiber, sirke, temel yağlar gibi) ve tahmini besin değerlerini (Kalori, Yağ, Protein, Şeker, Tuz) **Markdown** formatında net başlıklarla ayırarak sağla. Besin değerleri bölümünde her bir öğeyi ayrı satırda ve sadece sayısal tahmini değerleri (örn: 500 kcal, 20g) belirterek listele. Lütfen başlangıçtaki porsiyon sayısını belirt."
                        
                        parts_list = [
                            image_part,
                            {"text": user_query}
                        ]

                        result_text = call_gemini_api(parts_list, system_prompt, api_key)

                        st.session_state['last_recipe_output'] = result_text

                        with col2:
                            st.subheader("✅ Çözümlenen Tarif ve Analiz")
                            if result_text:
                                st.markdown(result_text)
                                st.session_state['last_recipe_output'] = result_text
                                
                                st.markdown("---")
                                st.subheader("Kaydet")
                                recipe_title = st.text_input("Tarif Başlığı (Kaydetmek için)", key="save_title_recipe_dedector", placeholder="Örn: Ev Yapımı Lazanya")
                                if st.button("💾 Bu Tarifi Kaydet", key="save_recipe_dedector_btn", disabled=not recipe_title):
                                    if recipe_title:
                                        st.session_state['saved_recipes'].append({
                                            'title': recipe_title,
                                            'content': result_text,
                                            'source': 'Tarif Dedektörü'
                                        })
                                        st.success(f"'{recipe_title}' tarifi başarıyla kaydedildi! (Bu, oturum kapanana kadar geçerlidir.)")
                                        # Input'u temizle
                                        st.session_state["save_title_recipe_dedector"] = ""
                            else:
                                st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                                
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")


    with col2:
        st.subheader("🍽️ Tarif Sonucu")
        with st.container(border=True, height=500):
            if 'last_recipe_output' in st.session_state and st.session_state.get('last_recipe_output') != "":
                st.markdown(st.session_state['last_recipe_output'])
            else:
                st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Yüklediğiniz resim analiz edildikten sonra burada bir başlık, malzeme listesi ve besin değerleri görünecektir.
                        <br><br>
                        *Afiyet olsun!*
                    </p>
                    """, unsafe_allow_html=True)


# --- 2. Dolap Şefi Alanı ---
elif selected_page == "🧊 DOLAP ŞEFİ":
    st.header(PAGES[selected_page])
    st.markdown("Buzdolabınızdaki veya elinizdeki malzemelerin fotoğrafını yükleyin. AI size o malzemelerle yapabileceğiniz **3 yaratıcı yemek fikri** ve eksik malzemeleri söylesin!")
    
    col3, col4 = st.columns([1, 2])
    
    with col3:
        uploaded_file_fridge = st.file_uploader("🛒 Malzemelerin Fotoğrafını Yükle/Çek", type=['png', 'jpg', 'jpeg'], key="fridge_upload", help="Elinizdeki malzemeleri bir araya getirip net bir fotoğraf çekin.")
        
        is_fridge_ready = bool(api_key and uploaded_file_fridge)
        
        if uploaded_file_fridge is not None:
            st.image(uploaded_file_fridge, caption='Malzeme Önizleme', use_column_width=True)

        if not is_fridge_ready and api_key and uploaded_file_fridge is None:
            st.info("Butonu etkinleştirmek için lütfen bir resim yükleyiniz.")


        if st.button("✨ Yemek Önerileri Oluştur", key="generate_suggestions_btn", disabled=not is_fridge_ready, use_container_width=True):
            if is_fridge_ready:
                st.session_state['generated_full_recipe'] = None # Yeni öneri geldiğinde tam tarifi sıfırla
                with st.spinner('Malzemeler analiz ediliyor ve öneriler oluşturuluyor...'):
                    try:
                        image_part_fridge, mime_type_fridge = file_to_generative_part(uploaded_file_fridge)
                        
                        system_prompt_fridge = "Sen yaratıcı bir mutfak şefisin. Görevin, resimdeki malzemeleri en verimli şekilde kullanarak hazırlanabilecek 3 farklı yemek tarifi fikri sunmak. Her fikri ayrı ayrı, net başlıklarla ve TAMAMEN Türkçe olarak sun. Yanıtını iyi formatlanmış Markdown başlıkları, kalın metinler ve listeler kullanarak hazırla."
                        
                        user_query_fridge = f"Bu, buzdolabımdaki veya tezgahımdaki malzemelerin fotoğrafı. Lütfen bu malzemeleri kullanarak yapabileceğim 3 farklı yemek fikri sun. Her yemek için, **Yemek Fikri 1/2/3** şeklinde başlık kullan. Bu başlığın altında yemeğin adını, hangi malzemelerin mevcut olduğunu ve tamamlamak için hangi eksik malzemelerin gerektiğini **Markdown** formatında listele. Sadece sonucu ver."
                        
                        parts_list_fridge = [
                            image_part_fridge,
                            {"text": user_query_fridge}
                        ]

                        result_text_fridge = call_gemini_api(parts_list_fridge, system_prompt_fridge, api_key)
                        st.session_state['last_fridge_output'] = result_text_fridge

                        with col4:
                            st.subheader("✅ Önerilen Yemekler ve Eksikler")
                            if result_text_fridge:
                                st.markdown("Aşağıdaki önerilerden birini seçerek tam tarifi oluşturabilirsiniz:")
                            else:
                                st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                                
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")


    with col4:
        st.subheader("🧊 Öneri Sonucu")
        with st.container(border=True, height=500):
            
            if st.session_state.get('generated_full_recipe'):
                # Tam tarif oluşturulduysa, onu göster ve kaydetme butonu ekle
                full_recipe = st.session_state['generated_full_recipe']
                st.subheader(f"✅ Tam Tarif: {full_recipe['title']}")
                st.markdown(full_recipe['content'])
                
                st.markdown("---")
                st.subheader("Tarifi Kaydet")
                recipe_title_full = st.text_input("Tarif Başlığı (Kaydetmek için)", key="save_title_recipe_full_fridge", value=full_recipe['title'], placeholder="Örn: Kolay Mercimek Çorbası")
                
                if st.button("💾 Bu Tam Tarifi Kaydet", key="save_recipe_full_fridge_btn", disabled=not recipe_title_full):
                    if recipe_title_full:
                        st.session_state['saved_recipes'].append({
                            'title': recipe_title_full,
                            'content': full_recipe['content'],
                            'source': 'Dolap Şefi (Tam Tarif)'
                        })
                        st.success(f"'{recipe_title_full}' tam tarifi başarıyla kaydedildi! (Bu, oturum kapanana kadar geçerlidir.)")
                        # Kaydettikten sonra tam tarif gösterimini sıfırla
                        st.session_state['generated_full_recipe'] = None
                        st.rerun() # Sayfayı yenile ve sadece önerileri göster
            
            elif st.session_state.get('last_fridge_output'):
                # Sadece öneri çıktıysa, önerileri parçala ve butonları göster
                suggestions = parse_fridge_suggestions(st.session_state['last_fridge_output'])
                
                if suggestions:
                    for i, suggestion in enumerate(suggestions):
                        with st.expander(f"**{suggestion['title']}** Fikri İçeriği"):
                            st.markdown(suggestion['content'])
                            
                            # Tam tarif oluşturma butonu
                            if st.button(f"➡️ Tam Tarifi Oluştur", key=f"create_full_recipe_{i}", use_container_width=True):
                                # Kullanıcının sadece tam tarifi oluşturmasını beklediğimiz için burası
                                with st.spinner(f"'{suggestion['title']}' için tam tarif oluşturuluyor..."):
                                    # Malzeme listesi için basit bir yer tutucu metin kullanıyoruz
                                    ingredient_summary = f"({suggestion['content'].split('Mevcut Malzemeler:')[-1].split('Eksik Malzemeler:')[-1].strip().split('\n')[0].strip()})"
                                    
                                    full_recipe_content = generate_full_recipe(suggestion['title'], ingredient_summary, api_key)
                                    
                                    if full_recipe_content:
                                        # Tam tarifi session state'e kaydet ve göster
                                        st.session_state['generated_full_recipe'] = {
                                            'title': suggestion['title'],
                                            'content': full_recipe_content
                                        }
                                        st.rerun() # Tam tarifi göstermek için sayfayı yenile
                                    else:
                                        st.error("Tam tarif oluşturulamadı.")
                else:
                    st.error("Önerilen metin ayrıştırılamadı. Lütfen API çıktısını kontrol edin.")
            
            else:
                # İlk durum: Hiçbir şey yok
                st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Malzeme fotoğrafınız yüklendikten ve analiz edildikten sonra burada 3 adet yaratıcı yemek fikri ve eksik listesi görünecektir. Bir fikri seçerek tam tarife dönüştürebilirsiniz!
                        <br><br>
                        *Hemen Mutfağa!*
                    </p>
                    """, unsafe_allow_html=True)


# --- 3. Tarif Uyarlama Alanı ---
elif selected_page == "♻️ TARİF UYARLAMA":
    st.header(PAGES[selected_page])
    st.markdown("Mevcut bir tarifi (yazılı metin olarak) yapay zekaya verin ve beslenme tercihlerinize veya elinizdeki malzemelere göre uyarlamasını isteyin.")
    
    default_recipe_text = st.session_state.get('last_recipe_output', '') if 'last_recipe_output' in st.session_state else ""

    recipe_to_adapt = st.text_area(
        "Uyarlanacak Tarifin Metni", 
        height=200, 
        key="adapt_recipe_input", 
        help="Buraya, değiştirmek istediğiniz tarifin tamamını yapıştırın.",
        value=default_recipe_text
    )
    
    adaptation_request = st.text_input(
        "Değişiklik İsteği (Örn: 'Bunu glutensiz yap' veya 'Sığır etini mantarla değiştir')", 
        key="adaptation_request_input"
    )

    is_adapt_ready = bool(api_key and recipe_to_adapt and adaptation_request)
    
    adapt_col1, adapt_col2 = st.columns([1, 2])

    with adapt_col1:
        if st.button("♻️ Tarifi Uyarlama", key="adapt_recipe_btn", disabled=not is_adapt_ready, use_container_width=True):
            if is_adapt_ready:
                with st.spinner('Tarif isteğinize göre uyarlanıyor...'):
                    try:
                        system_prompt_adapt = "Sen yaratıcı bir şef ve beslenme uzmanısısın. Görevin, verilen tarifi, kullanıcının isteği doğrultusunda mantıklı ve uygulanabilir bir şekilde değiştirmek ve yeni tarifi TAMAMEN Türkçe olarak sunmaktır. Sadece yeni, güncellenmiş tarifi, malzeme ve yapılış aşamalarını Markdown formatında döndür. Giriş/giriş kısmı olmadan doğrudan tarife başla."
                        
                        user_query_adapt = f"Aşağıdaki tarifi, şu isteğe göre uyarlar mısın: '{adaptation_request}'.\n\n--- Orijinal Tarif ---\n{recipe_to_adapt}"
                        
                        parts_list_adapt = [
                            {"text": user_query_adapt}
                        ]

                        result_text_adapt = call_gemini_api(parts_list_adapt, system_prompt_adapt, api_key)
                        st.session_state['last_adapt_output'] = result_text_adapt

                        with adapt_col2:
                             st.subheader("✅ Uyarlanmış Yeni Tarif")
                             with st.container(border=True, height=500):
                                 if result_text_adapt:
                                     st.markdown(result_text_adapt)
                                 else:
                                     st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                        
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")
            else:
                st.info("Lütfen hem tarifi hem de değişiklik isteğinizi girin.")

    with adapt_col2:
        st.subheader("✅ Uyarlanmış Yeni Tarif")
        with st.container(border=True, height=500):
            if 'last_adapt_output' in st.session_state and st.session_state['last_adapt_output']:
                st.markdown(st.session_state['last_adapt_output'])
            else:
                 st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Tarif metnini ve değişiklik isteğini girdikten sonra uyarlanmış yeni tarif burada görünecektir.
                    </p>
                    """, unsafe_allow_html=True)
                 
# --- 4. Porsiyon Ayarlayıcı Alanı ---
elif selected_page == "± PORSİYON AYARLAYICI":
    st.header(PAGES[selected_page])
    st.markdown("Bir tarifi mevcut porsiyon sayısıyla birlikte yapıştırın. Yapay zeka, istediğiniz yeni porsiyon sayısına göre tüm malzemeleri ve pişirme talimatlarını otomatik olarak güncellesin.")
    
    default_recipe_text = st.session_state.get('last_recipe_output', '') if 'last_recipe_output' in st.session_state else ""

    recipe_to_scale = st.text_area(
        "Porsiyonu Ayarlanacak Tarif Metni", 
        height=200, 
        key="scale_recipe_input", 
        help="Lütfen tarifin mevcut porsiyon sayısını (örneğin '4 kişilik') içerdiğinden emin olun.",
        value=default_recipe_text
    )
    
    target_servings = st.number_input(
        "Yeni Porsiyon Sayısı", 
        min_value=1, 
        value=2, 
        step=1,
        key="target_servings_input",
        help="Tarifi kaç kişilik yapmak istiyorsunuz?"
    )

    is_scale_ready = bool(api_key and recipe_to_scale and target_servings >= 1)
    
    scale_col1, scale_col2 = st.columns([1, 2])

    with scale_col1:
        if st.button("± Porsiyonu Güncelle", key="scale_recipe_btn", disabled=not is_scale_ready, use_container_width=True):
            if is_scale_ready:
                with st.spinner(f'Tarif {target_servings} kişilik porsiyona göre yeniden hesaplanıyor...'):
                    try:
                        system_prompt_scale = (
                            "Sen hassas bir mutfak matematikçisi ve şefsin. Görevin, verilen bir tarifi, kullanıcının belirttiği yeni porsiyon sayısına göre tüm malzeme miktarlarını ve ilgili pişirme sürelerini/talimatlarını **orantılı ve mantıklı bir şekilde** yeniden hesaplayıp TAMAMEN Türkçe olarak sunmaktır. Sadece yeni, güncellenmiş tarifi, malzeme ve yapılış aşamalarını Markdown formatında döndür. Çıktının başlangıcında, yeni porsiyon sayısını net bir şekilde belirt."
                        )
                        
                        user_query_scale = (
                            f"Aşağıdaki tarifi al. Orijinal porsiyon sayısını tarife metninden çıkar ve tüm malzeme ve talimatları **{target_servings} kişilik** porsiyona göre yeniden ölçeklendirip bana yeni, tam tarifi ver. Lütfen ölçü birimlerini (özellikle kaşık/bardak gibi hacim birimlerini) doğru orantılayarak güncelle.\n\n"
                            f"--- Orijinal Tarif ---\n{recipe_to_scale}"
                        )
                        
                        parts_list_scale = [
                            {"text": user_query_scale}
                        ]

                        result_text_scale = call_gemini_api(parts_list_scale, system_prompt_scale, api_key)
                        st.session_state['last_scale_output'] = result_text_scale

                        with scale_col2:
                             st.subheader(f"✅ Güncellenmiş Tarif ({target_servings} Kişilik)")
                             with st.container(border=True, height=500):
                                 if result_text_scale:
                                     st.markdown(result_text_scale)
                                     st.session_state['last_scale_output'] = result_text_scale
                                     
                                     st.markdown("---")
                                     st.subheader("Kaydet")
                                     recipe_title_scale = st.text_input("Tarif Başlığı (Kaydetmek için)", key="save_title_recipe_scaler", placeholder="Örn: 8 Kişilik Tiramisu")
                                     if st.button("💾 Bu Tarifi Kaydet", key="save_recipe_scaler_btn", disabled=not recipe_title_scale):
                                        if recipe_title_scale:
                                            st.session_state['saved_recipes'].append({
                                                'title': recipe_title_scale,
                                                'content': result_text_scale,
                                                'source': f'Porsiyon Ayarlayıcı ({target_servings} Kişi)'
                                            })
                                            st.success(f"'{recipe_title_scale}' tarifi başarıyla kaydedildi! (Bu, oturum kapanana kadar geçerlidir.)")
                                            # Input'u temizle
                                            st.session_state["save_title_recipe_scaler"] = ""
                                 else:
                                     st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                        
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")
            else:
                st.info("Lütfen tarifi yapıştırın ve yeni porsiyon sayısını girin.")

    with scale_col2:
        st.subheader("✅ Güncellenmiş Tarif Sonucu")
        with st.container(border=True, height=500):
            if 'last_scale_output' in st.session_state and st.session_state['last_scale_output']:
                st.markdown(st.session_state['last_scale_output'])
            else:
                 st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Tarif metnini yapıştırıp hedef porsiyon sayısını ayarladıktan sonra, yeni porsiyona göre ayarlanmış güncel tarif burada görünecektir.
                    </p>
                    """, unsafe_allow_html=True)

# --- 5. Tariflerim Alanı (YENİ ÖZELLİK) ---
elif selected_page == "📒 TARİFLERİM":
    st.header(PAGES[selected_page])
    st.markdown("Kaydettiğiniz tarifleri buradan görüntüleyebilir ve yönetebilirsiniz.")
    st.warning("🚨 **ÖNEMLİ NOT:** Bu özellik, Streamlit'in kısıtlamaları nedeniyle tarifleri yalnızca **mevcut tarayıcı oturumunuz süresince** saklar. Tarayıcı sekmesini kapattığınızda veya uygulamayı yenilediğinizde tarifler kaybolacaktır.")
    
    if not st.session_state.get('saved_recipes'):
        st.info("Henüz kaydedilmiş bir tarifiniz bulunmuyor. 'Tarif Dedektörü' veya 'Porsiyon Ayarlayıcı' sekmelerinde bir tarif oluşturup kaydedebilirsiniz.")
    else:
        st.subheader(f"Toplam {len(st.session_state['saved_recipes'])} Kayıtlı Tarif")
        
        # Gösterilecek tarifi seçmek için Selectbox
        recipe_titles = [f"{i+1}. {r['title']} (Kaynak: {r['source']})" for i, r in enumerate(st.session_state['saved_recipes'])]
        
        # Eğer liste boş değilse (ki bu kontrol yukarıda yapıldı, ama yine de güvenliğe alalım)
        if recipe_titles:
            selected_recipe_index = st.selectbox(
                "Görüntülenecek Tarifi Seçin", 
                range(len(st.session_state['saved_recipes'])), 
                format_func=lambda i: recipe_titles[i], 
                key="recipe_viewer_select"
            )
            
            # Seçilen tarifin içeriğini gösterme
            if selected_recipe_index is not None:
                selected_recipe = st.session_state['saved_recipes'][selected_recipe_index]
                
                st.markdown("---")
                st.title(selected_recipe['title'])
                st.markdown(f"**Kaynak:** *{selected_recipe['source']}*")
                st.markdown("---")
                
                # Tarif içeriği
                with st.container(border=True):
                    st.markdown(selected_recipe['content'])
                
                st.markdown("---")
                
                # Silme butonu
                if st.button(f"🗑️ '{selected_recipe['title']}' Tarifini Sil", key="delete_recipe_btn", type="primary"):
                    # Silme işlemi
                    del st.session_state['saved_recipes'][selected_recipe_index]
                    st.success(f"'{selected_recipe['title']}' tarifi başarıyla silindi.")
                    # Listeyi yenilemek için uygulamayı yeniden çalıştır
                    st.rerun() 

# --- 6. Malzeme İkamesi Alanı ---
elif selected_page == "🔄 MALZEME İKAMESİ":
    st.header(PAGES[selected_page])
    st.markdown("Elinizde olmayan veya kullanmak istemediğiniz bir malzeme için en iyi ikameleri, kullanım amaçlarına göre oranlarıyla birlikte öğrenin.")

    col5, col6 = st.columns([1, 2])

    with col5:
        ingredient_to_substitute = st.text_input(
            "Hangi Malzemeyi İkame Etmek İstiyorsunuz?", 
            key="substitute_ingredient_input",
            placeholder="Örn: Yumurta, Süt, Buğday Unu, Tereyağı"
        )
        
        context_reason = st.text_input(
            "İkame Nedeni/Kullanım Amacı (Zorunlu Değil)", 
            key="substitute_reason_input",
            placeholder="Örn: Vegan tarif için, daha az yağlı olması için, bağlayıcı olarak"
        )

        is_substitute_ready = bool(api_key and ingredient_to_substitute)

        if st.button("🔄 İkame Alternatiflerini Bul", key="find_substitute_btn", disabled=not is_substitute_ready, use_container_width=True):
            if is_substitute_ready:
                with st.spinner('İkame alternatifleri aranıyor...'):
                    try:
                        system_prompt_substitute = "Sen mutfak uzmanı bir ikame profesyelisin. Görevin, verilen malzeme için en uygun, pratik ve ölçüleri belirten ikame alternatiflerini TAMAMEN Türkçe olarak sunmaktır. Yanıtın, her ikame için neden uygun olduğunu, hangi durumlarda kullanıldığını ve en önemlisi **ikame oranını (Örn: 1:1, 1 yumurta yerine 1/4 fincan elma püresi)** açıkça belirtmelidir. Markdown tablolarını veya listelerini kullan."
                        
                        reason_text = f"'{context_reason}' amacı/sebebiyle" if context_reason else "genel olarak"
                        
                        user_query_substitute = f"Lütfen '{ingredient_to_substitute}' malzemesini, {reason_text} ikame edebileceğim en iyi 3-5 alternatif ve bunların ikame oranlarını tablo formatında veya detaylı liste halinde ver."
                        
                        parts_list_substitute = [
                            {"text": user_query_substitute}
                        ]

                        result_text_substitute = call_gemini_api(parts_list_substitute, system_prompt_substitute, api_key)
                        st.session_state['last_substitute_output'] = result_text_substitute
                            
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")
            else:
                st.info("Lütfen ikame etmek istediğiniz malzemeyi girin.")
    
    with col6:
        st.subheader("✅ İkame Alternatifleri")
        with st.container(border=True, height=500):
            if 'last_substitute_output' in st.session_state and st.session_state['last_substitute_output']:
                st.markdown(st.session_state['last_substitute_output'])
            else:
                 st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Malzemeyi ve ikame nedeninizi girdikten sonra, pratik ve ölçüleriyle birlikte en uygun alternatifler burada listelenecektir.
                    </p>
                    """, unsafe_allow_html=True)


# --- 7. Ölçü Çevirici Alanı (ÇİFT YÖNLÜ ve TR BAZLI) ---
elif selected_page == "⚖️ ÖLÇÜ ÇEVİRİCİ":
    st.header(PAGES[selected_page])
    st.markdown("Hacim (Bardak, kaşık, ml, L) ve Ağırlık (Gram, kg) ölçülerini, seçtiğiniz malzemenin yoğunluğuna göre hassas bir şekilde çevirin. Çeviriler Türkiye mutfağı standartlarına uygundur.")

    col7, col8 = st.columns([1, 2])

    with col7:
        # Çeviri Yönü Seçimi
        conversion_type = st.radio(
            "Çeviri Yönü",
            ('Hacim ➡️ Ağırlık (Örn: Bardak Un kaç gramdır?)', 'Ağırlık ➡️ Hacim (Örn: 100 gram Un kaç bardaktır?)'),
            key="conversion_type_select",
            horizontal=True
        )

        # Hacim Birimleri ve Ağırlık Birimleri (Türkiye standartlarına uygun olarak güncellendi)
        VOLUME_UNITS = [
            'Bardak', 
            'Yemek Kaşığı', 
            'Tatlı Kaşığı', 
            'Çay Kaşığı', 
            'Mililitre (ml)', 
            'Litre (L)'
        ]
        WEIGHT_UNITS = ['Gram (g)', 'Kilogram (kg)', 'Ons (oz)', 'Pound (lb)']

        # Çeviri Yönüne göre birimlerin belirlenmesi
        if conversion_type == 'Hacim ➡️ Ağırlık (Örn: Bardak Un kaç gramdır?)':
            source_units = VOLUME_UNITS
            target_units = WEIGHT_UNITS
        else:
            source_units = WEIGHT_UNITS
            target_units = VOLUME_UNITS
        
        # Ağırlık/Miktar Girişi
        col_amount, col_unit = st.columns([2, 3])
        with col_amount:
            amount_input = st.number_input(
                "Miktar", 
                min_value=0.01, 
                value=1.0, 
                step=0.5,
                key="convert_amount_input"
            )
        
        # Kaynak Birim Seçimi
        with col_unit:
            source_unit_select = st.selectbox(
                "Kaynak Birim",
                source_units,
                key="convert_source_unit_select"
            )

        # Malzeme Girişi (En kritik kısım)
        ingredient_input = st.text_input(
            "Malzeme (Zorunlu)", 
            key="convert_ingredient_input",
            placeholder="Örn: Buğday Unu, Toz Şeker, Tereyağı, Su"
        )
        
        # Hedef Birim Seçimi
        target_unit_select = st.selectbox(
            "Hedef Birim",
            target_units,
            key="convert_target_unit_select"
        )

        is_converter_ready = bool(api_key and amount_input > 0 and ingredient_input)

        if st.button("⚖️ Hesapla ve Çevir", key="calculate_conversion_btn", disabled=not is_converter_ready, use_container_width=True):
            if is_converter_ready:
                with st.spinner('Yoğunluğa özel ve Türkiye mutfağı standartlarına göre çeviri hesaplanıyor...'):
                    try:
                        system_prompt_converter = (
                            "Sen, mutfak ölçü birimleri ve gıda yoğunlukları konusunda uzman, titiz bir asistansın. "
                            "Görevin, verilen miktarı, başlangıç birimini, malzemeyi ve hedef birimi dikkate alarak, "
                            "özellikle **Türkiye mutfağında standart kabul edilen ölçüleri (örn: 1 yemek kaşığı yaklaşık 15 ml, 1 bardak yaklaşık 200 ml)** "
                            "kullanarak doğru çeviriyi ve bu çevirinin nedenini veya varsayımlarını (kullanılan yoğunluk değeri gibi) açıklamaktır. "
                            "Yanıtın yalnızca sonuç ve kısa bir açıklama içermelidir. Sonucu kalın ve büyük yazılarla belirt."
                        )
                        
                        user_query_converter = (
                            f"Lütfen '{amount_input} {source_unit_select}' miktarındaki '{ingredient_input}' malzemesini, "
                            f"'{target_unit_select}' birimine çevir. Çeviri yaparken lütfen Türkiye mutfak ölçütlerini (bardak, kaşık) referans al. "
                            f"Sonucu ve nedenini (kullanılan yoğunluk) açıklayarak ver."
                        )
                        
                        parts_list_converter = [
                            {"text": user_query_converter}
                        ]

                        # API Çağrısı
                        result_text_converter = call_gemini_api(parts_list_converter, system_prompt_converter, api_key)
                        st.session_state['last_converter_output'] = result_text_converter
                            
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")
            else:
                st.info("Lütfen çevrilecek miktarı ve malzemeyi eksiksiz girin.")
    
    with col8:
        st.subheader("✅ Hesaplama Sonucu")
        with st.container(border=True, height=500):
            if 'last_converter_output' in st.session_state and st.session_state['last_converter_output']:
                st.markdown(st.session_state['last_converter_output'])
            else:
                 st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Çeviri yönünü, miktarı, birimi ve malzemeyi girdikten sonra, malzemenin yoğunluğuna özel çeviri sonucu burada görünecektir.
                    </p>
                    """, unsafe_allow_html=True)
