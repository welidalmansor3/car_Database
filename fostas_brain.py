import os
import re
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class FOSTASCore:
    """
    FOSTAS Core - Sadece GLM-5.2 Kullanır
    """

    def __init__(self):
        self.raw_game_html = ""
        self.project_memory = {
            "assets": [],
            "docs": ""
        }
        
        self.glm_key = os.getenv("NV_GLM_KEY")
        self.nv_base_url = "https://integrate.api.nvidia.com/v1"
        
        self.client = None
        self.status = {"glm": {"ok": False, "error": "Key .env dosyasında yok."}}
        
        if self.glm_key:
            try:
                self.client = OpenAI(base_url=self.nv_base_url, api_key=self.glm_key)
                self.status["glm"] = {"ok": True, "error": None}
            except Exception as e:
                self.status["glm"] = {"ok": False, "error": str(e)}

    def _glm_chat(self, prompt: str, max_tokens: int = 8000, temperature: float = 0.7) -> str:
        """Sadece GLM-5.2'ye istek atar."""
        if not self.client:
            return "ERROR: GLM Client bağlı değil."
        
        try:
            completion = self.client.chat.completions.create(
                model="z-ai/glm-5.2",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False
            )
            return completion.choices[0].message.content or ""
        except Exception as e:
            return "ERROR: " + str(e)

    def upload_document(self, text: str):
        self.project_memory["docs"] = text[:5000]

    def register_user_asset(self, filename: str, file_data: bytes):
        safe_name = filename.replace(" ", "_")
        encoded_data = base64.b64encode(file_data).decode('utf-8')
        
        existing = next((a for a in self.project_memory["assets"] if a["name"] == safe_name), None)
        if existing:
            existing["data"] = file_data
            existing["b64"] = encoded_data
        else:
            self.project_memory["assets"].append({
                "name": safe_name, 
                "path": "res://assets/" + safe_name,
                "data": file_data,
                "b64": encoded_data,
                "mime": self._guess_mime(filename)
            })
        return "res://assets/" + safe_name

    def _guess_mime(self, filename: str) -> str:
        ext = filename.lower().split('.')[-1]
        mime_map = {
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp"
        }
        return mime_map.get(ext, "application/octet-stream")

    def _clean_html(self, code: str) -> str:
        code = code.strip()
        code = re.sub(r"^```(html|javascript|js)?\n?", "", code)
        code = re.sub(r"\n?```$", "", code)
        code = re.sub(r"```", "", code)
        return code.strip()

    def _inject_user_asset(self, code: str) -> str:
        if not self.project_memory["assets"]:
            return code
        
        asset = self.project_memory["assets"][0]
        b64 = asset["b64"]
        mime = asset["mime"]
        data_uri = "data:" + mime + ";base64," + b64
        
        code = code.replace("{{USER_IMAGE}}", data_uri)
        code = code.replace("{{ASSET}}", data_uri)
        code = code.replace("USER_ASSET", data_uri)
        code = code.replace("{{LOGO}}", data_uri)
        
        if mime.startswith("image/"):
            code = re.sub(r'src=["\']USER_[^"\']*["\']', 'src="' + data_uri + '"', code)
            code = re.sub(r'src=["\']ASSET["\']', 'src="' + data_uri + '"', code)
        
        return code

    def _create_fallback_html(self, prompt: str) -> str:
        title = prompt[:40] if len(prompt) < 40 else prompt[:37] + "..."
        return """<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>FOSTAS</title>
<style>body{font-family:sans-serif;background:#111;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.box{background:#222;padding:40px;border-radius:15px;text-align:center;border:1px solid #444}
button{background:#ff4b4b;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;margin-top:20px;font-size:16px}</style>
</head><body><div class="box"><h1>⚠️ Üretim Başarısız</h1><p>GLM-5.2 kod üretemedi. Lütfen tekrar deneyin.</p><p><strong>Prompt:</strong> """ + title + """</p><button onclick="location.reload()">🔄 Yeniden Dene</button></div>
</body></html>"""

    def generate_app_from_doc(self):
        if not self.project_memory["docs"].strip():
            yield "⚠️ Önce bir döküman yükle."
            return
        
        doc_summary = self.project_memory["docs"][:500]
        prompt = "Yüklenen dökümana göre bir web uygulaması yap:\n\n" + doc_summary
        yield from self.generate_app(prompt)

    def generate_app(self, user_prompt: str):
        """Sadece GLM-5.2 ile Uygulama/Oyun Üretir"""
        doc_context = self.project_memory["docs"] if self.project_memory["docs"] else "None"
        
        yield "💻 GLM-5.2 kodu yazıyor..."
        
        asset_info = ""
        if self.project_memory["assets"]:
            asset_name = self.project_memory["assets"][0]["name"]
            asset_info = "\nUSER HAS UPLOADED: " + asset_name + "\nInclude it as {{USER_IMAGE}} placeholder in src attributes."
        
        glm_prompt = (
            "You are the world's best web developer. Write a SINGLE complete HTML file.\n"
            "REQUEST: \"" + user_prompt + "\"\n"
            "CONTEXT: \"" + doc_context + "\"\n"
            + asset_info + "\n\n"
            "CRITICAL RULES:\n"
            "1. Start with <!DOCTYPE html>\n"
            "2. Include all HTML, CSS, JavaScript in ONE file\n"
            "3. Responsive design (mobile-first)\n"
            "4. ALL buttons use onclick=\"functionName()\" - NO addEventListener\n"
            "5. All JavaScript functions are GLOBAL: window.functionName = function() { }\n"
            "6. If game: use HTML5 Canvas or DOM manipulation\n"
            "7. Use emoji as visual elements: 🎮 🚗 🎯 👾 💰 ❤️\n"
            "8. Create SVG shapes programmatically (no external files)\n"
            "9. For 3D: Use Three.js with procedural shapes (Cube, Sphere, etc.)\n"
            "10. NEVER call external APIs or CDN (no VPN issues)\n"
            "11. User images: use {{USER_IMAGE}} placeholder\n"
            "12. Modern gradients, smooth animations\n"
            "13. Make it visually stunning\n\n"
            "OUTPUT ONLY RAW HTML. NO MARKDOWN. START WITH <!DOCTYPE html>"
        )

        code = self._glm_chat(glm_prompt, max_tokens=8000, temperature=0.7)
        
        # Temizlik
        if code:
            code = self._clean_html(code)
        
        # Kullanıcı resmi varsa enjekte et
        if self.project_memory["assets"] and code:
            code = self._inject_user_asset(code)
        
        # Saf HTML Kaydet (Hiçbir ekstra Python/JS scripti eklemiyoruz!)
        if code and ("<!DOCTYPE" in code or "<html" in code):
            self.raw_game_html = code
            yield "✅ Üretim tamamlandı! 'Oyna / Uygulamayı Dene' sekmesine geçebilirsin."
        else:
            self.raw_game_html = self._create_fallback_html(user_prompt)
            yield "⚠️ Kod üretilemedi, sistem yedek şablonu kullandı."
