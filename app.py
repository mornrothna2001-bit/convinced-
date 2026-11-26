import io
import os
import re
import zipfile
from flask import Flask, render_template_string, request, send_file
from PIL import Image
import UnityPy
from UnityPy.enums import BuildTarget, TextureFormat
from UnityPy.files import SerializedFile

try:
    import astc_encoder
    HAS_ASTC_ENC = True
except ImportError:
    HAS_ASTC_ENC = False

app = Flask(__name__)

ASTC_INFO = {
    "4": (TextureFormat.ASTC_RGBA_4x4, 4, 4),
    "6": (TextureFormat.ASTC_RGBA_6x6, 6, 6),
    "8": (TextureFormat.ASTC_RGBA_8x8, 8, 8),
    "12": (TextureFormat.ASTC_RGBA_12x12, 12, 12),
}

SKIP_FORMATS = {
    TextureFormat.ASTC_RGBA_4x4, TextureFormat.ASTC_RGBA_5x5,
    TextureFormat.ASTC_RGBA_6x6, TextureFormat.ASTC_RGBA_8x8,
    TextureFormat.ASTC_RGBA_10x10, TextureFormat.ASTC_RGBA_12x12,
    TextureFormat.ASTC_RGB_4x4, TextureFormat.ASTC_RGB_6x6,
    TextureFormat.ASTC_RGB_8x8, TextureFormat.ASTC_RGB_12x12,
    TextureFormat.PVRTC_RGB2, TextureFormat.PVRTC_RGBA2,
    TextureFormat.PVRTC_RGB4, TextureFormat.PVRTC_RGBA4,
}

UNCOMPRESSED_FORMATS = {
    TextureFormat.RGBA32, TextureFormat.ARGB32,
    TextureFormat.RGB24, TextureFormat.Alpha8,
}

HTML_PAGE = """
<!DOCTYPE html>
<html lang="km">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLBB Android ➔ iOS Converter</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #050814;
    color: #f8fafc;
    min-height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 20px;
    overflow-x: hidden;
    position: relative;
  }
  .glow-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    background:
      radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.25), transparent 45%),
      radial-gradient(circle at 80% 80%, rgba(168, 85, 247, 0.25), transparent 45%),
      radial-gradient(circle at 50% 50%, rgba(14, 165, 233, 0.15), transparent 60%);
    animation: pulseGlow 4s ease-in-out infinite alternate;
  }
  .sparkles {
    position: fixed;
    inset: 0;
    z-index: 0;
    background-image:
      radial-gradient(2px 2px at 15% 25%, #fff, transparent),
      radial-gradient(2px 2px at 75% 15%, #38bdf8, transparent),
      radial-gradient(3px 3px at 45% 75%, #c084fc, transparent),
      radial-gradient(2px 2px at 85% 65%, #fff, transparent),
      radial-gradient(2px 2px at 25% 85%, #38bdf8, transparent),
      radial-gradient(3px 3px at 60% 35%, #fff, transparent);
    background-size: 250px 250px;
    animation: twinkle 2.2s linear infinite alternate;
  }
  @keyframes pulseGlow {
    0% { opacity: 0.6; transform: scale(1); }
    100% { opacity: 1; transform: scale(1.06); }
  }
  @keyframes twinkle {
    0% { opacity: 0.25; }
    50% { opacity: 0.95; }
    100% { opacity: 0.35; }
  }
  .card {
    position: relative;
    z-index: 1;
    background: rgba(15, 23, 42, 0.78);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(56, 189, 248, 0.35);
    box-shadow: 0 0 35px rgba(56, 189, 248, 0.2), inset 0 0 20px rgba(168, 85, 247, 0.1);
    border-radius: 20px;
    padding: 28px;
    width: 100%;
    max-width: 440px;
  }
  h1 {
    font-size: 22px;
    text-align: center;
    background: linear-gradient(90deg, #38bdf8, #c084fc, #38bdf8);
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shineText 3s linear infinite;
    margin-bottom: 6px;
  }
  @keyframes shineText {
    to { background-position: 200% center; }
  }
  p.sub {
    text-align: center;
    font-size: 13px;
    color: #94a3b8;
    margin-bottom: 22px;
  }
  label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: #cbd5e1;
    margin-bottom: 6px;
  }
  input[type="file"], select {
    width: 100%;
    padding: 12px;
    border-radius: 10px;
    border: 1px solid rgba(56, 189, 248, 0.3);
    background: rgba(2, 6, 23, 0.85);
    color: #f8fafc;
    font-size: 14px;
    margin-bottom: 16px;
  }
  .check-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    font-size: 14px;
    color: #e2e8f0;
  }
  input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: #38bdf8;
  }
  button {
    width: 100%;
    padding: 14px;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    font-weight: bold;
    color: #fff;
    background: linear-gradient(135deg, #0284c7, #7e22ce);
    box-shadow: 0 0 20px rgba(56, 189, 248, 0.45);
    cursor: pointer;
    margin-top: 8px;
    transition: transform 0.15s, box-shadow 0.15s;
  }
  button:hover {
    transform: translateY(-1px);
    box-shadow: 0 0 28px rgba(192, 132, 252, 0.7);
  }
</style>
</head>
<body>
  <div class="glow-bg"></div>
  <div class="sparkles"></div>
  <div class="card">
    <h1>Android ➔ iOS Converter</h1>
    <p class="sub">បំប្លែង Script Skin MLBB តាមរូបមន្ត ASTC (Anti-Crash)</p>
    <form method="POST" enctype="multipart/form-data">
      <label>១. ជ្រើសរើសឯកសារ (.zip ឬ .unity3d)</label>
      <input type="file" name="files" multiple required>

      <label>២. កម្រិតគុណភាព Texture (ASTC)</label>
      <select name="astc_block">
        <option value="4">4x4 (ច្បាស់បំផុត)</option>
        <option value="6" selected>6x6 (ស្តង់ដារ - ណែនាំ)</option>
        <option value="8">8x8 (ទំហំតូច)</option>
        <option value="12">12x12 (ទំហំតូចបំផុត)</option>
      </select>

      <div class="check-row">
        <input type="checkbox" id="rename_dirs" name="rename_dirs" value="true" checked>
        <label for="rename_dirs" style="margin:0;">ប្តូរឈ្មោះ Folder android ➔ ios</label>
      </div>

      <div class="check-row">
        <input type="checkbox" id="aggressive" name="aggressive" value="true">
        <label for="aggressive" style="margin:0;">Aggressive (បំប្លែងរូបភាពមិនទាន់បង្រួម)</label>
      </div>

      <button type="submit">⚡ ចាប់ផ្តើមបំប្លែងទៅ iOS</button>
    </form>
  </div>
</body>
</html>
"""

def rename_android_dir(path_str: str) -> str:
    return re.sub(r'(?<![a-zA-Z0-9])android(?![a-zA-Z0-9])', 'ios', path_str, flags=re.IGNORECASE)

def encode_astc_with_mips(pil_img: Image.Image, bx: int, by: int, mip_count: int) -> bytes:
    img = pil_img.convert("RGBA")
    w, h = img.size
    config = astc_encoder.ASTCConfig(
        astc_encoder.ASTCProfile.LDR_SRGB, bx, by, 1,
        quality=astc_encoder.ASTCQuality.MEDIUM
    )
    context = astc_encoder.ASTCContext(config)
    swizzle = astc_encoder.ASTCSwizzle.from_str("RGBA")

    out_chunks = bytearray()
    cur_w, cur_h = w, h
    for level in range(max(1, mip_count)):
        mip_img = img if level == 0 else img.resize((cur_w, cur_h), Image.Resampling.BILINEAR)
        astc_img = astc_encoder.ASTCImage(astc_encoder.ASTCType.U8, cur_w, cur_h, 1, data=mip_img.tobytes())
        out_chunks.extend(context.compress(astc_img, swizzle))
        if cur_w == 1 and cur_h == 1:
            break
        cur_w = max(1, cur_w // 2)
        cur_h = max(1, cur_h // 2)
    return bytes(out_chunks)

def get_original_packer(env) -> str:
    try:
        comp = getattr(env.file, "flags", 0) & 0x3F
        if comp == 1:
            return "lzma"
    except Exception:
        pass
    return "lz4"

def convert_bytes(raw_bytes: bytes, astc_block: str = "6", rename_dirs: bool = True, aggressive: bool = False) -> bytes:
    try:
        env = UnityPy.load(raw_bytes)
    except Exception:
        return raw_bytes
    if not env.objects:
        return raw_bytes

    target_fmt, bx, by = ASTC_INFO.get(astc_block, (TextureFormat.ASTC_RGBA_6x6, 6, 6))

    for f in env.files.values():
        if isinstance(f, SerializedFile):
            f.target_platform = BuildTarget.iOS
            if rename_dirs and hasattr(f, "externals"):
                for ext in f.externals:
                    if getattr(ext, "path", None):
                        ext.path = rename_android_dir(ext.path)
        elif hasattr(f, "files"):
            for sub in f.files.values():
                if isinstance(sub, SerializedFile):
                    sub.target_platform = BuildTarget.iOS
                    if rename_dirs and hasattr(sub, "externals"):
                        for ext in sub.externals:
                            if getattr(ext, "path", None):
                                ext.path = rename_android_dir(ext.path)

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            try:
                tex = obj.read()
                if tex.m_Width <= 0 or tex.m_Height <= 0 or tex.m_TextureFormat in SKIP_FORMATS:
                    continue
                if not aggressive and tex.m_TextureFormat in UNCOMPRESSED_FORMATS:
                    continue

                pil_img = tex.image
                mip_cnt = getattr(tex, "m_MipCount", 1) or 1

                if HAS_ASTC_ENC:
                    astc_bytes = encode_astc_with_mips(pil_img, bx, by, mip_cnt)
                    tex.m_TextureFormat = target_fmt
                    tex.m_CompleteImageSize = len(astc_bytes)
                    tex.image_data = astc_bytes
                else:
                    tex.set_image(pil_img, target_format=target_fmt)

                if hasattr(tex, "m_StreamData") and tex.m_StreamData:
                    tex.m_StreamData.offset = 0
                    tex.m_StreamData.size = 0
                    tex.m_StreamData.path = ""
                tex.save()
            except Exception:
                pass

    try:
        return env.file.save(packer=get_original_packer(env))
    except Exception:
        return raw_bytes

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded = [f for f in request.files.getlist("files") if f.filename]
        if not uploaded:
            return "សូមជ្រើសរើសឯកសារ!", 400

        astc_block = request.form.get("astc_block", "6")
        rename_dirs = request.form.get("rename_dirs") == "true"
        aggressive = request.form.get("aggressive") == "true"

        if len(uploaded) == 1 and uploaded[0].filename.lower().endswith(".zip"):
            in_buf = io.BytesIO(uploaded[0].read())
            out_buf = io.BytesIO()
            with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if not item.filename.endswith("/"):
                        new_name = rename_android_dir(item.filename) if rename_dirs else item.filename
                        zout.writestr(new_name, convert_bytes(zin.read(item.filename), astc_block, rename_dirs, aggressive))
            out_buf.seek(0)
            base = os.path.splitext(uploaded[0].filename)[0]
            return send_file(out_buf, as_attachment=True, download_name=f"{base}_iOS.zip")

        if len(uploaded) == 1:
            f = uploaded[0]
            out_name = rename_android_dir(f.filename) if rename_dirs else f.filename
            return send_file(io.BytesIO(convert_bytes(f.read(), astc_block, rename_dirs, aggressive)), as_attachment=True, download_name=out_name)

        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for f in uploaded:
                out_name = rename_android_dir(f.filename) if rename_dirs else f.filename
                zout.writestr(out_name, convert_bytes(f.read(), astc_block, rename_dirs, aggressive))
        out_buf.seek(0)
        return send_file(out_buf, as_attachment=True, download_name="MLBB_Script_iOS.zip")

    return render_template_string(HTML_PAGE)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
