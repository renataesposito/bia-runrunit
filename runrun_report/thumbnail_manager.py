import os
import time
import subprocess
import requests
import tempfile
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_path

import api_client
import database

# Extensions that are supported for thumbnail generation
SUPPORTED_EXTENSIONS = {
    "image": ["jpg", "jpeg", "png", "gif", "webp"],
    "pdf": ["pdf"],
    "office": ["xls", "xlsx", "doc", "docx", "ppt", "pptx"],
    "video": ["mp4"]
}

THUMBNAILS_DIR = os.path.join(os.path.dirname(__file__), "data", "thumbnails")

# Ensure the directory exists
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

def standardize_image(img: Image.Image, target_size=(800, 600), bg_color=(255, 255, 255)) -> Image.Image:
    """
    Resizes an image proportionally to fit within target_size and pads the rest with bg_color.
    This guarantees every thumbnail has exactly target_size dimensions.
    """
    # Convert to RGB if it's RGBA or P
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    target_w, target_h = target_size
    orig_w, orig_h = img.size

    # Calculate scale to fit inside target_size
    ratio = min(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * ratio)
    new_h = int(orig_h * ratio)

    # Resize the image
    if (new_w, new_h) != (orig_w, orig_h):
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Create a new image with the target size and background color
    new_img = Image.new("RGB", target_size, bg_color)
    
    # Paste the resized image into the center of the new image
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    new_img.paste(img, (offset_x, offset_y))

    return new_img

def download_file(url: str, dest_path: str) -> bool:
    """Downloads a file from URL to dest_path."""
    try:
        headers = api_client._HEADERS if "runrun.it" in url else None
        response = requests.get(url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()
        
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Erro ao baixar arquivo de {url}: {e}")
        return False

def convert_pdf_to_image(pdf_path: str) -> Image.Image:
    """Extracts the first page of a PDF as an Image."""
    images = convert_from_path(pdf_path, first_page_only=True, dpi=150)
    if images:
        return images[0]
    raise Exception("PDF não contém páginas.")

def convert_office_to_pdf(office_path: str, out_dir: str) -> str:
    """Converts an Office document to PDF using LibreOffice headless."""
    # Process runs libreoffice --headless --convert-to pdf <file> --outdir <dir>
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        office_path,
        "--outdir",
        out_dir
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    # The output PDF has the same name as the office file but with .pdf extension
    base_name = os.path.splitext(os.path.basename(office_path))[0]
    pdf_path = os.path.join(out_dir, f"{base_name}.pdf")
    if os.path.exists(pdf_path):
        return pdf_path
    raise Exception("Falha ao converter documento Office para PDF.")

def extract_video_frame(video_path: str, thumb_path: str):
    """Extracts a frame from a video at 1 second mark using FFmpeg."""
    cmd = [
        "ffmpeg",
        "-y",               # Overwrite
        "-i", video_path,
        "-ss", "00:00:01.000",
        "-vframes", "1",
        thumb_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if not os.path.exists(thumb_path):
        raise Exception("Falha ao extrair frame do vídeo.")

def get_or_create_thumbnail(anexo_id: int, url: str, extension: str) -> str:
    """
    Returns the path to the cached thumbnail. If it doesn't exist, downloads and creates it.
    """
    thumb_path = os.path.join(THUMBNAILS_DIR, f"{anexo_id}.jpg")
    if os.path.exists(thumb_path):
        return thumb_path

    ext = extension.lower()
    
    # Find the category of the extension
    category = None
    for cat, exts in SUPPORTED_EXTENSIONS.items():
        if ext in exts:
            category = cat
            break
            
    if not category:
        return None # Unsupported extension

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Download the file
        temp_file = os.path.join(tmpdir, f"file_{anexo_id}.{ext}")
        if not download_file(url, temp_file):
            return None

        img = None
        try:
            # Step 2: Convert to PIL Image
            if category == "image":
                img = Image.open(temp_file)
            elif category == "pdf":
                img = convert_pdf_to_image(temp_file)
            elif category == "office":
                pdf_file = convert_office_to_pdf(temp_file, tmpdir)
                img = convert_pdf_to_image(pdf_file)
            elif category == "video":
                temp_thumb = os.path.join(tmpdir, f"thumb_{anexo_id}.jpg")
                extract_video_frame(temp_file, temp_thumb)
                img = Image.open(temp_thumb)
                
            # Step 3: Standardize and save
            if img:
                std_img = standardize_image(img, target_size=(800, 600))
                std_img.save(thumb_path, "JPEG", quality=90, optimize=True)
                return thumb_path
        except Exception as e:
            print(f"Erro ao processar thumbnail do anexo {anexo_id} ({ext}): {e}")
            return None
            
    return None

def sync_all_thumbnails():
    """
    Runs as a background job to download and cache thumbnails for all approved attachments.
    """
    print("Iniciando sincronização de thumbnails em background...")
    start_time = time.time()
    
    try:
        anexos = database.load_all_anexos()
        
        count_processed = 0
        count_skipped = 0
        count_errors = 0
        
        for anexo in anexos:
            anexo_id = anexo.get("id")
            ext = str(anexo.get("file_extension", "")).lower()
            
            # Check if supported
            is_supported = any(ext in exts for exts in SUPPORTED_EXTENSIONS.values())
            if not is_supported or not anexo_id:
                count_skipped += 1
                continue
                
            # Construct URL
            url = f"https://runrun.it/api/v1.0/documents/{anexo_id}/download"
            
            # get_or_create_thumbnail will only download if it doesn't exist
            thumb_path = get_or_create_thumbnail(anexo_id, url, ext)
            if thumb_path:
                count_processed += 1
            else:
                count_errors += 1
                
        duration = time.time() - start_time
        print(f"Sincronização de thumbnails concluída em {duration:.1f}s. "
              f"Processados: {count_processed}, Ignorados: {count_skipped}, Erros: {count_errors}")
              
    except Exception as e:
        print(f"Erro durante sincronização de thumbnails: {e}")

if __name__ == "__main__":
    # Test script if executed directly
    pass