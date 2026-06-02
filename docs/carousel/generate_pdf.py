"""
Generate LinkedIn carousel PDF from carousel.html using Playwright.

Usage:
    python docs/carousel/generate_pdf.py

Output:
    docs/carousel/telecom_call_intelligence_carousel.pdf

LinkedIn upload:
    Go to "Create a post" → "Add a document" → select the PDF.
    LinkedIn renders each page as a swipeable carousel slide.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
HTML = HERE / "carousel.html"
OUT  = HERE / "telecom_call_intelligence_carousel.pdf"


def generate() -> None:
    print(f"  Source : {HTML}")
    print(f"  Output : {OUT}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\nPlaywright not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page    = browser.new_page()

        page.goto(f"file://{HTML}", wait_until="networkidle")
        page.wait_for_timeout(2000)   # let Google Fonts load

        page.pdf(
            path=str(OUT),
            width="1080px",
            height="1080px",
            print_background=True,
        )
        browser.close()

    size_kb = OUT.stat().st_size // 1024
    print(f"\n  PDF generated: {OUT.name} ({size_kb} KB, 18 pages)")
    print("\n  Upload to LinkedIn:")
    print("    1. Click 'Start a post'")
    print("    2. Click the document icon (📄)")
    print("    3. Select telecom_call_intelligence_carousel.pdf")
    print("    4. Add title: 'Every agentic AI principle — implemented'")
    print("    5. Post!\n")


if __name__ == "__main__":
    generate()
