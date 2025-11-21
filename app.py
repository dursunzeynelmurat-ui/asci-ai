import streamlit as st
import requests
import base64
import io
import json

# --- API Sabitleri ve Yapılandırma ---
# Gemini API URL'si
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"
MODEL_NAME = "gemini-2.5-flash-preview-09-2025"

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

def call_gemini_api(contents, system_instruction, api_key):
    """
    Gemini API'ye istek gönderir ve yanıtı işler.
    
    401 yetkilendirme hatasını özellikle ele alır.
    """
    if not api_key:
        raise ValueError("Lütfen Gemini API Anahtarınızı girin.")

    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
    }

    headers = {
        'Content-Type': 'application/json'
    }

    # API Anahtarını doğrudan URL'ye ekliyoruz
    full_url = f"{GEMINI_API_URL}?key={api_key}"

    st.info("API çağrısı yapılıyor, lütfen bekleyin...")
    
    try:
        # İsteği gönder
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
            st.warning("Lütfen girdiğiniz API anahtarının doğru ve aktif olduğundan emin olun.")
        elif status_code == 400:
             st.error("❌ API Hatası 400 (Geçersiz İstek)")
             st.warning("Yüklediğiniz dosya türü veya formatı desteklenmiyor olabilir ya da istek formatı hatalıdır.")
        else:
            st.error(f"❌ HTTP Hatası {status_code}: İstek başarısız oldu.")
        
        # Hata detaylarını göster
        error_details = response.text
        st.error(f"Detaylar: {error_details[:200]}...") 
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
    }
    </style>
""", unsafe_allow_html=True)

st.title("🍲 Akıllı Mutfak Asistanı")
st.markdown("Yapay Zeka ile Yemek Tarifleri Keşfedin ve Dolabınızı Yönetin.")

# API Anahtarı Girişi 
api_key = st.text_input(
    "Gemini API Anahtarınızı Girin:", 
    type="password", 
    help="Yetkilendirme için kendi Gemini API anahtarınızı girin. Bu, 401 yetkilendirme sorununu çözecektir."
)

# Sekmeler
tab_recipe, tab_fridge = st.tabs(["🍽️ Tarif Keşfet", "🧊 Dolap Şefi"])

# --- 1. Tarif Keşfetme Alanı ---
with tab_recipe:
    st.header("Yemek Fotoğrafından Tarif Analizi")
    st.markdown("Yaptığınız veya gördüğünüz yemeğin fotoğrafını yükleyin. AI tarifi, besin değerlerini ve alışveriş listesini çıkarsın.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        uploaded_file = st.file_uploader("📸 Yemeğin Fotoğrafını Yükle/Çek", type=['png', 'jpg', 'jpeg'], key="recipe_upload")
        
        if uploaded_file is not None:
            st.image(uploaded_file, caption='Yemek Önizleme', use_column_width=True)
            
            if st.button("Tarif ve Besin Değerlerini Çıkar", key="generate_recipe_btn", disabled=not api_key):
                if api_key:
                    try:
                        # Gerekli girdileri hazırla
                        image_part, mime_type = file_to_generative_part(uploaded_file)
                        
                        system_prompt = "Sen profesyonel bir aşçı ve beslenme uzmanısın. Görev, resimdeki yemeği en ince ayrıntısına kadar analiz etmek ve TAMAMEN Türkçe olarak, aşağıda belirtilen formatta detaylı bilgi sağlamaktır."
                        
                        user_query = f"Bu pişmiş bir yemeğin fotoğrafı. Lütfen tam tarifi, gerekli malzemelerin alışveriş listesini (temel mutfak malzemeleri hariç, örneğin su, tuz, karabiber, sirke, temel yağlar gibi) ve tahmini besin değerlerini (Kalori, Yağ, Protein, Şeker, Tuz) **Markdown** formatında net başlıklarla ayırarak sağla. Besin değerleri bölümünde her bir öğeyi ayrı satırda ve sadece sayısal tahmini değerleri (örn: 500 kcal, 20g) belirterek listele."
                        
                        contents = [
                            image_part,
                            {"text": user_query}
                        ]

                        # API Çağrısı
                        result_text = call_gemini_api(contents, system_prompt, api_key)

                        with col2:
                            st.subheader("Çözümlenen Tarif ve Analiz")
                            if result_text:
                                st.markdown(result_text)
                            else:
                                st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                                
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")
                else:
                    st.warning("Lütfen API Anahtarınızı girin.")


    with col2:
        st.subheader("Sonuç Alanı")
        st.info("Sonuçlar burada görüntülenecektir.")


# --- 2. Dolap Şefi Alanı ---
with tab_fridge:
    st.header("Malzeme Fotoğrafından Yemek Önerileri")
    st.markdown("Buzdolabınızdaki malzemelerin fotoğrafını yükleyin. AI size o malzemelerle yapabileceğiniz yemekleri ve eksikleri söylesin.")
    
    col3, col4 = st.columns([1, 1])
    
    with col3:
        uploaded_file_fridge = st.file_uploader("🛒 Malzemelerin Fotoğrafını Yükle/Çek", type=['png', 'jpg', 'jpeg'], key="fridge_upload")
        
        if uploaded_file_fridge is not None:
            st.image(uploaded_file_fridge, caption='Malzeme Önizleme', use_column_width=True)
            
            if st.button("Yemek Önerileri Oluştur", key="generate_suggestions_btn", disabled=not api_key):
                if api_key:
                    try:
                        # Gerekli girdileri hazırla
                        image_part_fridge, mime_type_fridge = file_to_generative_part(uploaded_file_fridge)
                        
                        system_prompt_fridge = "Sen yaratıcı bir mutfak şefisin. Görevin, resimdeki malzemeleri en verimli şekilde kullanarak hazırlanabilecek 3 farklı yemek tarifi fikri sunmak. Tüm çıktı TAMAMEN Türkçe olmalıdır."
                        
                        user_query_fridge = f"Bu, buzdolabımdaki veya tezgahımdaki malzemelerin fotoğrafı. Lütfen bu malzemeleri kullanarak yapabileceğim 3 farklı yemek fikri sun. Her yemek için, yemeğin adını, hangi malzemelerin mevcut olduğunu ve tamamlamak için hangi eksik malzemelerin gerektiğini **Markdown** formatında listele."
                        
                        contents_fridge = [
                            image_part_fridge,
                            {"text": user_query_fridge}
                        ]

                        # API Çağrısı
                        result_text_fridge = call_gemini_api(contents_fridge, system_prompt_fridge, api_key)

                        with col4:
                            st.subheader("Önerilen Yemekler ve Eksikler")
                            if result_text_fridge:
                                st.markdown(result_text_fridge)
                            else:
                                st.error("Üretim başarısız oldu. Lütfen hata mesajlarını kontrol edin.")
                                
                    except Exception as e:
                        st.error(f"Genel Hata: {e}")
                else:
                    st.warning("Lütfen API Anahtarınızı girin.")


    with col4:
        st.subheader("Sonuç Alanı")
        st.info("Sonuçlar burada görüntülenecektir.")
