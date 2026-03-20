import sys
import os
import asyncio

# Ensure we can import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from filter_logic import process_attachment, is_known_meme, add_to_meme_cache
import db_manager

class MockAttachment:
    """Mocks a discord.Attachment object for unit testing."""
    def __init__(self, filename, size, content=b"fake_image_bytes"):
        self.filename = filename
        self.size = size
        self.content = content
        
    async def read(self):
        return self.content

async def run_tests():
    print("--- Starting Automated Self-Annealing Logic Tests ---")
    
    # Ensure database is mapped
    db_manager.setup_database()
    
    # Test 1: GIF Rule
    gif = MockAttachment("funny.gif", 500000, b"gif_bytes")
    action, _ = await process_attachment(gif)
    assert action == "DISCARD", f"GIF should be DISCARD, got {action}"
    print("[PASS] GIF Quick-Discard Filter")

    # Test 2: Video Rule
    vid = MockAttachment("hangout.mp4", 10000000, b"vid_bytes")
    action, _ = await process_attachment(vid)
    assert action == "REVIEW", f"Video should be REVIEW, got {action}"
    print("[PASS] Video Fallback Filter")

    # Test 3: Heuristic > 500KB (High-Res Photo)
    photo = MockAttachment("IMG_1234.jpg", 600000, b"large_image_bytes")
    action, _ = await process_attachment(photo)
    assert action == "SAVE", f"Large JPG (>500KB) should be SAVE, got {action}"
    print("[PASS] High-Res Photo Filter")

    import uuid
    # Test 4: Heuristic < 500KB (Meme/Screenshot) -> Routes to Queue
    meme = MockAttachment("meme.png", 200000, f"small_image_bytes_{uuid.uuid4()}".encode())
    action, hsh = await process_attachment(meme)
    assert action == "REVIEW", f"Small PNG (<500KB) should be REVIEW, got {action}"
    assert len(hsh) == 64, "Expected a valid SHA256 string"
    print("[PASS] Small File Filter -> Admin Queue")

    # Test 5: Meme Cache Blacklisting
    add_to_meme_cache(hsh) # Simulate admin clicking 'Discard & Blacklist'
    assert is_known_meme(hsh) == True
    
    # Try processing the exact same meme again
    action2, _ = await process_attachment(meme)
    assert action2 == "DISCARD", f"Cached Meme should now be DISCARD, got {action2}"
    print("[PASS] SQL Meme Blacklisting Cache")

    print(f"--- All Core Filtering and Database Tests Passed! ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
