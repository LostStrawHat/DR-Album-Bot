import os
import asyncio
import aiohttp

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CACHE_DIR = os.path.join(WORKSPACE_ROOT, 'execution', 'cache')
THUMB_DIR = os.path.join(WORKSPACE_ROOT, 'execution', 'cache', 'thumbnails')

for d in [CACHE_DIR, THUMB_DIR]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def generate_thumbnail_sync(cache_path: str, thumb_path: str, is_video: bool) -> bool:
    """Generates a compressed thumbnail for a cached media file."""
    if os.path.exists(thumb_path):
        return True
    try:
        if is_video:
            import cv2
            cap = cv2.VideoCapture(cache_path)
            cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
            success, frame = cap.read()
            if not success:
                cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                success, frame = cap.read()
            cap.release()
            
            if success:
                height, width = frame.shape[:2]
                scale = 300.0 / max(height, width)
                if scale < 1.0:
                    frame = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
                cv2.imwrite(thumb_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                return True
            else:
                return False
        else:
            from PIL import Image
            with Image.open(cache_path) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                img.save(thumb_path, "JPEG", quality=65, optimize=True)
                return True
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
        return False

async def process_media_eagerly(attachment_input, message_id: str):
    """Downloads the file from Discord immediately and queues thumbnail generation."""
    try:
        cache_path = os.path.join(CACHE_DIR, message_id)
        thumb_path = os.path.join(THUMB_DIR, f"{message_id}.jpg")
        
        # 1. Download natively via Discord library immediately!
        if hasattr(attachment_input, 'save'):
            await attachment_input.save(cache_path)
            filename = getattr(attachment_input, 'filename', '').lower()
        else:
            # Fallback if we just have a URL (e.g. from web approval or reactions)
            url = str(attachment_input)
            filename = url.split("?")[0].split("/")[-1].lower()
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open(cache_path, 'wb') as f:
                            f.write(await resp.read())
                    else:
                        print(f"Failed to fetch {url} - Status: {resp.status}")
                        return
        
        # 2. Extract extension/type
        is_video = filename.endswith(('.mp4', '.mov'))
        
        # 3. Offload CPU-bound thumbnail encode to another thread to avoid blocking bot loop
        await asyncio.to_thread(generate_thumbnail_sync, cache_path, thumb_path, is_video)
        print(f"✅ Executed Eager Background Cache & Thumbnail for {message_id}")
    except Exception as e:
        print(f"Eager caching failed for {message_id}: {e}")
