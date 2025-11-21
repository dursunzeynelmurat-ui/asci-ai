import streamlit as st
import requests
import base64
import json

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
    
    Bu fonksiyonda artık bekleme mesajı (st.info) gösterilmeyecektir.
    """
    if not api_key:
        # API anahtarı yoksa bu hatayı fırlatır
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
    
    try:
        # İsteği gönder (Streamlit'in otomatik "Running..." göstergesi bu esnada görünecektir)
        response = requests.post(full_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # 4xx veya 5xx hatalarını HTTPError olarak fırlatır

        # Yanıtı JSON olarak ayrıştırma
        result = response.json()
        
        # Metin içeriğini çıkar
        text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')

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

# --- Streamlit Uygulama Arayüzü ---

st.set_page_config(page_title="Akıllı Mutfak Asistanı", layout="wide")

# Özel CSS ile arayüzü güzelleştirme
st.markdown("""
    <style>
    .stApp {
        background-color: #f7f9fb;
    }
    .stTabs [data-baseweb="tab-list"] {
		gap: 24px;
	}

	.stTabs [data-baseweb="tab"] {
		height: 50px;
		white-space: nowrap;
		background-color: #e0f2f1; /* Açık Zümrüt Yeşili */
        border-radius: 8px 8px 0 0;
        transition: all 0.3s;
	}

    .stTabs [aria-selected="true"] {
        background-color: #10b981; /* Zümrüt Yeşili 500 */
        color: white;
        border-bottom: 4px solid #047857; /* Koyu Zümrüt Yeşili */
        font-weight: bold;
    }
    /* Sonuç konteynerleri için güzel bir stil */
    .results-container {
        padding: 16px;
        border-radius: 8px;
        background-color: #ffffff;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.06);
        min-height: 400px; /* Sonuç alanını sabitle */
    }
    </style>
""", unsafe_allow_html=True)

st.title("👨‍🍳 Akıllı Mutfak Asistanınız")
st.markdown("""
    Yapay zekanın gücüyle mutfağınızı dönüştürün! Gemini, yemek fotoğraflarınızı analiz eder, tarifler çıkarır ve elinizdeki malzemelerle yaratıcı yemekler önerir. **Yeni: Tariflerinizi anında uyarlayın!**
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


# Sekmeler (Yeni sekme eklendi)
tab_recipe, tab_fridge, tab_adapt = st.tabs(["🍽️ Tarif DEDEKTÖRÜ", "🧊 DOLAP ŞEFİ", "♻️ TARİF UYARLAMA"])

# --- 1. Tarif Keşfetme Alanı ---
with tab_recipe:
    st.header("Yemek Fotoğrafından Tarifi Çözümle")
    st.markdown("Bir tabak yemeğin veya hazırladığınız yemeğin fotoğrafını yükleyin, Yapay Zeka anında tarifi, besin değerlerini ve alışveriş listenizi çıkarsın!")
    
    # GÜNCELLEME: Kolon oranını [1, 2] olarak değiştirerek giriş alanını küçült
    col1, col2 = st.columns([1, 2])
    
    with col1:
        uploaded_file = st.file_uploader("📸 Yemeğin Fotoğrafını Yükle/Çek", type=['png', 'jpg', 'jpeg'], key="recipe_upload", help="Yemeğinizin net ve aydınlık bir fotoğrafını çekin.")
        
        # BUTON KONTROLÜ İÇİN MANTIK: API key VE resim yüklendiğinde etkin olur.
        is_recipe_ready = bool(api_key and uploaded_file) 

        if uploaded_file is not None:
            # Önizleme gösteriliyor
            st.image(uploaded_file, caption='Yemek Önizleme', use_column_width=True)
            
        # Eğer hazır değilse, neden hazır olmadığını belirten bir mesaj göster
        if not is_recipe_ready and api_key: # Sadece resim eksikse uyar (API key var)
            if uploaded_file is None:
                st.info("Butonu etkinleştirmek için lütfen bir resim yükleyin.")


        if st.button("🍽️ Tarif ve Besin Değerlerini Çıkar", key="generate_recipe_btn", disabled=not is_recipe_ready, use_container_width=True):
            # API Anahtarı ve Resim Kontrolü başarılıysa devam et
            if is_recipe_ready:
                try:
                    # Gerekli girdileri hazırla
                    image_part, mime_type = file_to_generative_part(uploaded_file)
                    
                    system_prompt = "Sen profesyonel bir aşçı ve beslenme uzmanısısın. Görev, resimdeki yemeği en ince ayrıntısına kadar analiz etmek ve TAMAMEN Türkçe olarak, aşağıda belirtilen formatta detaylı bilgi sağlamaktır. Yanıtını iyi formatlanmış Markdown başlıkları, kalın metinler ve listeler kullanarak hazırla."
                    
                    user_query = f"Bu pişmiş bir yemeğin fotoğrafı. Lütfen tam tarifi, gerekli malzemelerin alışveriş listesini (temel mutfak malzemeleri hariç, örneğin su, tuz, karabiber, sirke, temel yağlar gibi) ve tahmini besin değerlerini (Kalori, Yağ, Protein, Şeker, Tuz) **Markdown** formatında net başlıklarla ayırarak sağla. Besin değerleri bölümünde her bir öğeyi ayrı satırda ve sadece sayısal tahmini değerleri (örn: 500 kcal, 20g) belirterek listele."
                    
                    # GÜNCELLEME: call_gemini_api'ye geçirilen parça listesi
                    parts_list = [
                        image_part,
                        {"text": user_query}
                    ]

                    # API Çağrısı
                    result_text = call_gemini_api(parts_list, system_prompt, api_key)

                    with col2:
                        st.subheader("✅ Çözümlenen Tarif ve Analiz")
                        if result_text:
                            # GÜNCELLEME: Cevabı doğrudan Markdown olarak göster
                            st.markdown(result_text)
                            st.session_state['last_recipe_output'] = result_text
                        else:
                            st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                            
                except Exception as e:
                    st.error(f"Genel Hata: {e}")


    with col2:
        st.subheader("🍽️ Tarif Sonucu")
        with st.container(border=True):
            if 'result_text' not in st.session_state:
                st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Yüklediğiniz resim analiz edildikten sonra burada bir başlık, malzeme listesi ve besin değerleri görünecektir.
                        <br><br>
                        *Afiyet olsun!*
                    </p>
                    """, unsafe_allow_html=True)
            elif st.session_state.get('last_tab') != 'recipe':
                 st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Yüklediğiniz resim analiz edildikten sonra burada bir başlık, malzeme listesi ve besin değerleri görünecektir.
                        <br><br>
                        *Afiyet olsun!*
                    </p>
                    """, unsafe_allow_html=True)


# --- 2. Dolap Şefi Alanı ---
with tab_fridge:
    st.header("Malzeme Fotoğrafından Yemek Önerileri")
    st.markdown("Buzdolabınızdaki veya elinizdeki malzemelerin fotoğrafını yükleyin. AI size o malzemelerle yapabileceğiniz **3 yaratıcı yemek fikri** ve eksik malzemeleri söylesin!")
    
    # GÜNCELLEME: Kolon oranını [1, 2] olarak değiştirerek giriş alanını küçült
    col3, col4 = st.columns([1, 2])
    
    with col3:
        uploaded_file_fridge = st.file_uploader("🛒 Malzemelerin Fotoğrafını Yükle/Çek", type=['png', 'jpg', 'jpeg'], key="fridge_upload", help="Elinizdeki malzemeleri bir araya getirip net bir fotoğraf çekin.")
        
        # BUTON KONTROLÜ İÇİN MANTIK: API key VE resim yüklendiğinde etkin olur.
        is_fridge_ready = bool(api_key and uploaded_file_fridge)
        
        if uploaded_file_fridge is not None:
            # Önizleme gösteriliyor
            st.image(uploaded_file_fridge, caption='Malzeme Önizleme', use_column_width=True)

        # Eğer hazır değilse, neden hazır olmadığını belirten bir mesaj göster
        if not is_fridge_ready and api_key: # Sadece resim eksikse uyar (API key var)
            if uploaded_file_fridge is None:
                st.info("Butonu etkinleştirmek için lütfen bir resim yükleyiniz.")


        if st.button("✨ Yemek Önerileri Oluştur", key="generate_suggestions_btn", disabled=not is_fridge_ready, use_container_width=True):
            # API Anahtarı ve Resim Kontrolü başarılıysa devam et
            if is_fridge_ready:
                try:
                    # Gerekli girdileri hazırla
                    image_part_fridge, mime_type_fridge = file_to_generative_part(uploaded_file_fridge)
                    
                    system_prompt_fridge = "Sen yaratıcı bir mutfak şefisin. Görevin, resimdeki malzemeleri en verimli şekilde kullanarak hazırlanabilecek 3 farklı yemek tarifi fikri sunmak. Tüm çıktı TAMAMEN Türkçe olmalıdır. Yanıtını iyi formatlanmış Markdown başlıkları, kalın metinler ve listeler kullanarak hazırla."
                    
                    user_query_fridge = f"Bu, buzdolabımdaki veya tezgahımdaki malzemelerin fotoğrafı. Lütfen bu malzemeleri kullanarak yapabileceğim 3 farklı yemek fikri sun. Her yemek için, yemeğin adını, hangi malzemelerin mevcut olduğunu ve tamamlamak için hangi eksik malzemelerin gerektiğini **Markdown** formatında listele."
                    
                    # GÜNCELLEME: call_gemini_api'ye geçirilen parça listesi
                    parts_list_fridge = [
                        image_part_fridge,
                        {"text": user_query_fridge}
                    ]

                    # API Çağrısı
                    result_text_fridge = call_gemini_api(parts_list_fridge, system_prompt_fridge, api_key)

                    with col4:
                        st.subheader("✅ Önerilen Yemekler ve Eksikler")
                        if result_text_fridge:
                            # GÜNCELLEME: Cevabı doğrudan Markdown olarak göster
                            st.markdown(result_text_fridge)
                        else:
                            st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                            
                except Exception as e:
                    st.error(f"Genel Hata: {e}")


    with col4:
        st.subheader("🧊 Öneri Sonucu")
        with st.container(border=True):
            if 'result_text_fridge' not in st.session_state:
                st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Malzeme fotoğrafınız yüklendikten ve analiz edildikten sonra burada 3 adet yaratıcı yemek fikri ve eksik listesi görünecektir.
                        <br><br>
                        *Hemen Mutfağa!*
                    </p>
                    """, unsafe_allow_html=True)
            elif st.session_state.get('last_tab') != 'fridge':
                 st.markdown("""
                    <p class="text-center text-gray-500 italic mt-8">
                        Malzeme fotoğrafınız yüklendikten ve analiz edildikten sonra burada 3 adet yaratıcı yemek fikri ve eksik listesi görünecektir.
                        <br><br>
                        *Hemen Mutfağa!*
                    </p>
                    """, unsafe_allow_html=True)

# --- 3. Tarif Uyarlama Alanı (YENİ ÖZELLİK) ---
with tab_adapt:
    st.header("Tarif Uyarlama ve Değiştirme")
    st.markdown("Mevcut bir tarifi (yazılı metin olarak) yapay zekaya verin ve beslenme tercihlerinize veya elinizdeki malzemelere göre uyarlamasını isteyin.")
    
    # Giriş Alanları
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

    if st.button("♻️ Tarifi Uyarlama", key="adapt_recipe_btn", disabled=not is_adapt_ready, use_container_width=True):
        if is_adapt_ready:
            try:
                system_prompt_adapt = "Sen yaratıcı bir şef ve beslenme uzmanısısın. Görevin, verilen tarifi, kullanıcının isteği doğrultusunda mantıklı ve uygulanabilir bir şekilde değiştirmek ve yeni tarifi TAMAMEN Türkçe olarak sunmaktır. Sadece yeni, güncellenmiş tarifi, malzeme ve yapılış aşamalarını Markdown formatında döndür. Giriş/giriş kısmı olmadan doğrudan tarife başla."
                
                user_query_adapt = f"Aşağıdaki tarifi, şu isteğe göre uyarlar mısın: '{adaptation_request}'.\n\n--- Orijinal Tarif ---\n{recipe_to_adapt}"
                
                # call_gemini_api'ye geçirilen parça listesi (sadece metin)
                parts_list_adapt = [
                    {"text": user_query_adapt}
                ]

                # API Çağrısı
                result_text_adapt = call_gemini_api(parts_list_adapt, system_prompt_adapt, api_key)

                st.subheader("✅ Uyarlanmış Yeni Tarif")
                if result_text_adapt:
                    st.markdown(result_text_adapt)
                else:
                    st.error("Uyarlama başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                        
            except Exception as e:
                st.error(f"Genel Hata: {e}")
        else:
            st.info("Lütfen hem tarifi hem de değişiklik isteğinizi girin.")
