# -*- coding: utf-8 -*-
"""
Created on Wed Oct 29 2025

LinkedIn post stats scraper: logs in, opens recent shares, scrolls, extracts
likes/comments/views, computes trend lines and saves CSVs and PNGs.

Note: Automating LinkedIn may violate their Terms of Service. Use responsibly.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import numpy as np
import pandas as pd
import pyperclip
import matplotlib.pyplot as plt
import os
import base64


# Config flags
SAVE_FULL_HTML = False
SAVE_SCREENSHOT = False

@dataclass
class UserInput:
    username: str
    password: str
    profile_slug: str
    num_posts: int


def prompt_user_input() -> UserInput:
    print("Please enter the exact LinkedIn username you use to login (email/phone?):")
    username_string = str(input()).strip()
    print()
    print("Please enter the exact LinkedIn password:")
    password_string = str(input()).strip()
    print()
    print("Please enter your username exactly as in your profile link (after '/in/'):")
    profile_slug = str(input()).strip().strip('/')
    print()
    # Default number of posts to analyze (no user prompt)
    number_of_posts = 10
    return UserInput(username_string, password_string, profile_slug, number_of_posts)


def build_driver(headless: bool = False) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,900")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def login_linkedin(driver: webdriver.Chrome, username: str, password: str) -> None:
    driver.get("https://www.linkedin.com/login")
    wait = WebDriverWait(driver, 20)
    user_el = wait.until(EC.presence_of_element_located((By.ID, "username")))
    pass_el = wait.until(EC.presence_of_element_located((By.ID, "password")))
    user_el.clear(); user_el.send_keys(username)
    pass_el.clear(); pass_el.send_keys(password)
    pass_el.submit()
    # Wait for redirection or global nav
    wait.until(lambda d: "/login" not in d.current_url)


def open_creator_analytics_content(driver: webdriver.Chrome) -> None:
    # Navigate to LinkedIn Creator Analytics - Content tab
    analytics_url = "https://www.linkedin.com/analytics/creator/content/"
    driver.get(analytics_url)
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    WebDriverWait(driver, 30).until(lambda d: "analytics/creator/content" in d.current_url)
    # tiny settle time
    time.sleep(0.5)


def wait_for_analytics_ready(driver: webdriver.Chrome, timeout: int = 20) -> None:
    """Wait until analytics content appears stable and present."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if "analytics/creator/content" not in driver.current_url:
                time.sleep(0.3)
                continue
            txt = driver.execute_script("return document.body.innerText || '';") or ""
            # require some content and one of these keywords
            if len(txt) > 500 and ("Analytics" in txt or "Analisi" in txt or "Content" in txt or "Contenuti" in txt):
                return
        except Exception:
            pass
        time.sleep(0.4)
    # proceed anyway after timeout
    return


def scroll_for_posts(driver: webdriver.Chrome, num_posts: int, posts_per_scroll: int = 5) -> None:
    number_of_scrolls = -(-num_posts // posts_per_scroll)
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(number_of_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3.5)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def extract_int_list(pattern_matches: List[str]) -> List[int]:
    result: List[int] = []
    for s in pattern_matches:
        last_string = s.replace(',', '')
        try:
            result.append(int(last_string))
        except Exception:
            continue
    return result


def parse_stats_from_html(html: str):
    soup = BeautifulSoup(html, features="lxml")

    # Attempt 1: old class names (may still work)
    likes_tags = soup.find_all("span", attrs={"class": "v-align-middle social-details-social-counts__reactions-count"})
    comments_tags = soup.find_all("li", attrs={"class": "social-details-social-counts__item social-details-social-counts__comments"})
    views_tags = soup.find_all("span", attrs={"class": "icon-and-text-container t-14 t-black--light t-normal"})

    likes: List[int] = []
    comments: List[int] = []
    views: List[int] = []

    number_pattern = re.compile(r"[,0-9]+")

    for tag in likes_tags:
        matches = number_pattern.findall(str(tag))
        if matches:
            likes.extend(extract_int_list([matches[-1]]))

    for tag in comments_tags:
        matches = number_pattern.findall(str(tag))
        if matches:
            comments.extend(extract_int_list([matches[-1]]))

    for tag in views_tags:
        matches = number_pattern.findall(str(tag))
        if matches:
            views.extend(extract_int_list([matches[-1]]))

    # Fallback heuristic: look for localized labels nearby
    if not likes or not comments or not views:
        text = soup.get_text(" ", strip=True)
        # This fallback is very rough and may over/under count.
        likes_guess = [m.group(0) for m in re.finditer(r"(?i)(?:mi piace|like|reazioni)\D*([0-9][0-9.,]*)", text)]
        comments_guess = [m.group(0) for m in re.finditer(r"(?i)(?:commenti|comments)\D*([0-9][0-9.,]*)", text)]
        views_guess = [m.group(0) for m in re.finditer(r"(?i)(?:visualizzazioni|views)\D*([0-9][0-9.,]*)", text)]
        if not likes:
            likes = extract_int_list([re.findall(r"[0-9][0-9.,]*", s)[-1] for s in likes_guess if re.findall(r"[0-9][0-9.,]*", s)])
        if not comments:
            comments = extract_int_list([re.findall(r"[0-9][0-9.,]*", s)[-1] for s in comments_guess if re.findall(r"[0-9][0-9.,]*", s)])
        if not views:
            views = extract_int_list([re.findall(r"[0-9][0-9.,]*", s)[-1] for s in views_guess if re.findall(r"[0-9][0-9.,]*", s)])

    return likes, comments, views


def extract_hashtags_from_html(html: str):
    # Extract hashtags like #keyword, with unicode word chars
    text = BeautifulSoup(html, features="lxml").get_text(" ", strip=True)
    tags = re.findall(r"#[\wÀ-ÖØ-öø-ÿ0-9_]+", text)
    # Normalize: lowercase and deduplicate while preserving order
    seen = set()
    ordered = []
    for t in tags:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def _to_number(value_str: str) -> float:
    s = value_str.strip().lower().replace('\u202f', '').replace(' ', '')
    # Replace thousand separators
    s = s.replace(',', '')
    # Handle compact notations
    multiplier = 1
    if s.endswith('k'):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith('m'):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith('b'):
        multiplier = 1_000_000_000
        s = s[:-1]
    # Replace locale decimal comma
    s = s.replace('.', '').replace(',', '.') if s.count(',') == 1 and s.count('.') == 0 else s
    try:
        return float(s) * multiplier
    except Exception:
        # Fallback: take only the first contiguous digit group to avoid concatenations
        m = re.search(r"[0-9]+", s)
        if not m:
            return 0.0
        try:
            return float(m.group(0)) * multiplier
        except Exception:
            return 0.0


def parse_analytics_metrics(html: str):
    """Parse totals from LinkedIn Creator Analytics Content page.
    Tries IT/EN labels and returns dict {label: number}.
    """
    soup = BeautifulSoup(html, features="lxml")
    text = soup.get_text(" \n", strip=True)

    # Candidate labels (Italian/English)
    label_patterns = {
        'Impressions': r"(?i)(impressions?|visualizzazioni)",
        'Reactions': r"(?i)(reactions?|reazioni)",
        'Comments': r"(?i)(comments?|commenti)",
        'Reposts': r"(?i)(reposts?|condivisioni|repost)",
        'EngagementRate': r"(?i)(engagement\s*rate|tasso\s*di\s*coinvolgimento)",
        'Follows': r"(?i)(follows?|nuovi\s*followers?|seguaci|seguaci\s*nuovi)",
        'UniqueViewers': r"(?i)(unique\s*viewers|spettatori\s*unici|visualizzatori\s*unici)",
    }

    # For each label, search a nearby number (within same line or short window)
    metrics = {}
    lines = [ln for ln in text.split('\n') if ln.strip()]

    def candidates_from_window(window_lines):
        candidates = []
        for raw in window_lines:
            # Skip percentages entirely
            if '%' in raw:
                # remove percent pieces and still try numbers not tied to %
                cleaned = re.sub(r"[+\-]?[0-9][0-9\.,\u202f]*\s*%", " ", raw)
            else:
                cleaned = raw
            for m in re.finditer(r"([0-9][0-9\.,\u202f]*\s*[kmbKMB]?)", cleaned):
                tok = m.group(1)
                # Discard absurd tokens: very long digits without suffix
                digit_only = re.sub(r"[^0-9]", "", tok)
                if len(digit_only) > 9 and not re.search(r"[kmbKMB]$", tok):
                    continue
                num = _to_number(tok)
                # Filter implausibly large values
                if num > 1_000_000_000:  # >1B is unlikely in creator analytics totals
                    continue
                candidates.append(num)
        return candidates

    for label, pattern in label_patterns.items():
        for i, ln in enumerate(lines):
            if not re.search(pattern, ln):
                continue
            window = lines[i:i+3]  # label line + a couple following lines
            nums = candidates_from_window(window)
            if not nums:
                continue
            # Heuristics by label
            if label in ("Impressions", "Reactions", "Comments", "Reposts", "UniqueViewers"):
                # Pick the largest candidate in the small window to avoid grabbing small unrelated tokens
                val = max(nums)
            elif label == "Follows":
                # Prefer the first small-ish integer (avoid choosing a huge impressions-like number)
                small_ints = [n for n in nums if n.is_integer() and n <= 100000]
                val = small_ints[0] if small_ints else nums[0]
            else:
                val = nums[0]
            metrics[label] = float(val)
            break
    return metrics


def copy_full_page_text(driver: webdriver.Chrome) -> str:
    # Focus body and send Ctrl+A, Ctrl+C
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        body = driver.find_element(By.TAG_NAME, "body")
        body.click()
        body.send_keys(Keys.CONTROL, 'a')
        time.sleep(0.2)
        body.send_keys(Keys.CONTROL, 'c')
        time.sleep(0.3)
        txt = pyperclip.paste() or ""
        if txt.strip():
            return txt
    except Exception:
        pass
    # Fallback to JS innerText
    try:
        return driver.execute_script("return document.body.innerText || '';")
    except Exception:
        return ""


def print_page_to_pdf(driver: webdriver.Chrome, out_pdf_path: str) -> bool:
    """Use Chrome DevTools Protocol to print current page to PDF without dialogs."""
    try:
        result = driver.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": True,
            "landscape": False,
            "scale": 1.0,
        })
        data = result.get("data")
        if not data:
            return False
        pdf_bytes = base64.b64decode(data)
        with open(out_pdf_path, "wb") as f:
            f.write(pdf_bytes)
        return True
    except Exception:
        return False


def open_pdf_and_copy_text(driver: webdriver.Chrome, pdf_path: str) -> str:
    """Open a local PDF in Chrome, select all and copy, then return clipboard text."""
    try:
        abs_path = os.path.abspath(pdf_path)
        file_url = "file:///" + abs_path.replace("\\", "/")
        driver.get(file_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        body = driver.find_element(By.TAG_NAME, "body")
        body.click()
        time.sleep(0.3)
        body.send_keys(Keys.CONTROL, 'a')
        time.sleep(0.2)
        body.send_keys(Keys.CONTROL, 'c')
        time.sleep(0.5)
        txt = pyperclip.paste() or ""
        return txt
    except Exception:
        return ""

def extract_numbers_only(html: str):
    # Return list of numeric values parsed from HTML/text (handles K/M/B and %)
    soup = BeautifulSoup(html or "", features="lxml")
    text = soup.get_text("\n", strip=True)
    tokens = re.findall(r"[+\-]?\d[\d\.,\u202f]*\s*[kmbKMB]?%?", text)
    numbers = []
    for tok in tokens:
        t = tok.strip()
        is_percent = t.endswith('%')
        if is_percent:
            tnum = t[:-1]
        else:
            tnum = t
        try:
            val = _to_number(tnum)
        except Exception:
            continue
        # keep percent as numeric value too (no symbol)
        numbers.append(val)
    return numbers

def _normalize_lines(text: str):
    # Split and trim empty lines
    return [ln.strip() for ln in (text or "").split('\n') if ln and ln.strip()]

def parse_content_performance(text: str):
    """Parse 'Rendimento dei contenuti' / 'Content performance' summary.
    Returns { impressionsTotal, changePercent } if found.
    """
    lines = _normalize_lines(text)
    out = {}
    for i, ln in enumerate(lines):
        if re.search(r"(?i)rendimento\s+dei\s+contenuti|content\s+performance", ln):
            window = lines[i:i+8]
            # find first number and the word Impressioni/Impressions near it
            impressions = None
            change = None
            for w in window:
                if re.search(r"(?i)impressioni|impressions", w):
                    mnum = re.search(r"([0-9][0-9\.,\u202f]*\s*[kmbKMB]?)", w)
                    if mnum:
                        impressions = _to_number(mnum.group(1))
                if change is None:
                    # es: "16.900% rispetto ai precedenti 7 giorni" oppure "+12% vs previous 7 days"
                    mchg = re.search(r"([+\-]?[0-9][0-9\.,\u202f]*\s*%)", w)
                    if mchg:
                        change = mchg.group(1)
            if impressions is None:
                # try next line for the number
                if len(window) > 1:
                    mnum2 = re.search(r"([0-9][0-9\.,\u202f]*\s*[kmbKMB]?)", window[1])
                    if mnum2:
                        impressions = _to_number(mnum2.group(1))
            if impressions is not None:
                out["impressionsTotal"] = int(impressions) if float(impressions).is_integer() else float(impressions)
            if change:
                # strip % and convert
                pct_raw = change.replace('%', '').strip()
                try:
                    out["changePercent7d"] = float(pct_raw.replace(',', '.'))
                except Exception:
                    out["changePercent7d"] = None
            break
    return out

def parse_posts_blocks(text: str):
    """Parse per-post metrics from Analytics text. Returns list of posts with
    {relativeTime, impressions, likes, comments, textSnippet}.
    """
    lines = _normalize_lines(text)
    posts = []
    for i, ln in enumerate(lines):
        if re.search(r"(?i)ha\s+pubblicato\s+questo\s+post|published\s+this\s+post", ln):
            rel = None
            mrel = re.search(r"\u2022\s*([^•]+)$", ln)
            if mrel:
                rel = mrel.group(1).strip()
            # search within next ~12 lines for metrics
            window = lines[i:i+12]
            impressions = None
            likes = None
            comments = None
            snippet = None
            for w in window:
                if impressions is None and re.search(r"(?i)impressioni|impressions", w):
                    mnum = re.search(r"([0-9][0-9\.,\u202f]*\s*[kmbKMB]?)", w)
                    if mnum:
                        impressions = _to_number(mnum.group(1))
                if likes is None and re.search(r"(?i)like|mi\s+piace|reactions?", w):
                    mnum = re.search(r"\b([0-9][0-9\.,\u202f]*)\b", w)
                    if mnum:
                        likes = _to_number(mnum.group(1))
                if comments is None and re.search(r"(?i)commenti|comments", w):
                    mnum = re.search(r"\b([0-9][0-9\.,\u202f]*)\b", w)
                    if mnum:
                        comments = _to_number(mnum.group(1))
            # try to grab a text snippet around the post
            if i+1 < len(lines):
                snippet = (lines[i+1][:180] + '…') if len(lines[i+1]) > 180 else lines[i+1]
            posts.append({
                "relativeTime": rel,
                "impressions": int(impressions) if impressions is not None and float(impressions).is_integer() else (float(impressions) if impressions is not None else None),
                "likes": int(likes) if likes is not None and float(likes).is_integer() else (float(likes) if likes is not None else None),
                "comments": int(comments) if comments is not None and float(comments).is_integer() else (float(comments) if comments is not None else None),
                "textSnippet": snippet,
            })
    return posts


def parse_posts_from_analytics_html(html: str):
    """Parse per-post metrics from Analytics HTML structure.
    Looks for blocks like:
    <div class="member-analytics-addon__cta-item-with-secondary-metric">
      <span class="member-analytics-addon__cta-item-with-secondary-list-item-title">358</span>
      <div class="member-analytics-addon__cta-item-with-secondary-list-item-text">Impressioni</div>
    </div>
    Returns list of dicts like { 'impressions': int }.
    """
    soup = BeautifulSoup(html or "", features="lxml")
    blocks = soup.select("div.member-analytics-addon__cta-item-with-secondary-metric")
    posts = []
    for blk in blocks:
        title_el = blk.select_one(".member-analytics-addon__cta-item-with-secondary-list-item-title")
        label_el = blk.select_one(".member-analytics-addon__cta-item-with-secondary-list-item-text")
        if not title_el or not label_el:
            continue
        label_txt = (label_el.get_text(strip=True) or "").lower()
        # Only handle Impressioni/Impressions for now
        if not re.search(r"(?i)impressioni|impressions", label_txt):
            continue
        title_txt = title_el.get_text(" ", strip=True) if title_el else ""
        mnum = re.search(r"([0-9][0-9\.,\u202f]*\s*[kmbKMB]?)", title_txt)
        if not mnum:
            continue
        val = _to_number(mnum.group(1))
        if val and val < 1_000_000_000:
            posts.append({
                "impressions": int(val) if float(val).is_integer() else float(val)
            })
    return posts

def compute_and_return(profile_slug: str, num_posts: int, likes: List[int], comments: List[int], views: List[int]):
    # Reverse lists so earliest -> latest
    likes = list(reversed(likes))
    comments = list(reversed(comments))
    views = list(reversed(views))

    likes_df = pd.DataFrame(likes, columns=["Likes"])[:num_posts]
    comments_df = pd.DataFrame(comments, columns=["Comments"])[:num_posts]
    views_df = pd.DataFrame(views, columns=["Views"])[:num_posts]

    # Remove outliers (> 3 std dev from median)
    likes_no = likes_df.copy()
    comments_no = comments_df.copy()
    views_no = views_df.copy()

    likes_no = likes_no[np.abs(likes_no - likes_no.median()) <= (3 * likes_no.std())]
    comments_no = comments_no[np.abs(comments_no - comments_no.median()) <= (3 * comments_no.std())]
    views_no = views_no[np.abs(views_no - views_no.median()) <= (3 * views_no.std())]

    # Avoid chained assignment warnings
    likes_no.loc[:, "Likes"] = likes_no["Likes"].fillna(likes_no["Likes"].median())
    comments_no.loc[:, "Comments"] = comments_no["Comments"].fillna(comments_no["Comments"].median())
    views_no.loc[:, "Views"] = views_no["Views"].fillna(views_no["Views"].median())

    def _clean_series(series: pd.Series) -> pd.Series:
        s = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        return s

    def trend_and_plot(series: pd.Series, title: str, y_label: str, out_png: str):
        s = _clean_series(series)
        print("**************************")
        print(f"***** {y_label.upper()} *****")
        print("**************************")
        if len(s) < 2 or s.nunique() == 1:
            print("Not enough valid data points for trend line. Plotting raw series only.")
            # Not enough data for trend; return minimal stats
            return {"slope": None, "nrmse": None, "series": s.tolist() if len(s) else []}

        x = np.arange(len(s))
        try:
            coeffs, residuals, *_ = np.polyfit(x, s.values.flatten(), 1, full=True)
            slope = coeffs[0]
            mse = (residuals[0] / len(s)) if len(residuals) else 0.0
            denom = (s.max() - s.min()) if (s.max() - s.min()) != 0 else 1
            nrmse = (np.sqrt(mse)) / denom
            return {"slope": float(slope), "nrmse": float(nrmse), "series": s.tolist(), "trend": [float(slope * xi + coeffs[1]) for xi in x]}
        except Exception as e:
            return {"slope": None, "nrmse": None, "series": s.tolist()}

    # Simple raw lists output only
    return {
        "likes": likes_no["Likes"].dropna().astype(int).tolist(),
        "comments": comments_no["Comments"].dropna().astype(int).tolist(),
        "views": views_no["Views"].dropna().astype(int).tolist(),
    }


def main():
    user_input = prompt_user_input()
    driver = build_driver(headless=False)
    try:
        login_linkedin(driver, user_input.username, user_input.password)
        open_creator_analytics_content(driver)
        # Optionally scroll to load more analytics cards/entries
        scroll_for_posts(driver, user_input.num_posts)
        # Ensure the analytics page is fully loaded before copying
        wait_for_analytics_ready(driver)
        # NON navigare altrove: cattura subito l'HTML completo (documento + iframes)
        full_text = ""
        if SAVE_SCREENSHOT:
            try:
                driver.save_screenshot("analytics.png")
            except Exception:
                pass
        # Get HTML (document + all iframes) e restituisci subito l'intero contenuto
        def _get_outer_html(drv):
            try:
                return drv.execute_script("return document.documentElement.outerHTML;")
            except Exception:
                return drv.page_source

        full_parts = []
        # Main document
        main_html = _get_outer_html(driver) or ""
        full_parts.append("<!-- MAIN DOCUMENT START -->\n" + main_html + "\n<!-- MAIN DOCUMENT END -->")
        # Iframes
        from selenium.common.exceptions import NoSuchFrameException
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for idx, fr in enumerate(frames):
            try:
                driver.switch_to.frame(fr)
                frame_html = _get_outer_html(driver) or ""
                full_parts.append(f"<!-- IFRAME {idx} START -->\n" + frame_html + f"\n<!-- IFRAME {idx} END -->")
            except NoSuchFrameException:
                continue
            except Exception:
                continue
            finally:
                driver.switch_to.default_content()

        combined_html = "\n\n".join(full_parts)
        try:
            with open("analytics_page.html", "w", encoding="utf-8") as f:
                f.write(combined_html)
        except Exception:
            pass
        try:
            print(combined_html)
        except Exception:
            print(combined_html.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))
        return
        # Save focused snippet for per-post analytics blocks
        try:
            soup_for_save = BeautifulSoup(html or "", features="lxml")
            blocks_for_save = soup_for_save.select("div.member-analytics-addon__cta-item-with-secondary-metric")
            if blocks_for_save:
                snippet_html = "\n".join(str(b) for b in blocks_for_save)
                with open("analytics_posts_blocks.html", "w", encoding="utf-8") as f:
                    f.write("<html><body>\n" + snippet_html + "\n</body></html>")
        except Exception:
            pass
        analytics = parse_analytics_metrics(html)
        if not analytics and full_text:
            analytics = parse_content_performance(full_text)

        impressions = analytics.get('Impressions') if analytics else None
        unique_viewers = analytics.get('UniqueViewers') if analytics else None

        # Prefer HTML-structured per-post impressions sum if page-total is missing or implausible
        html_posts_for_sum = parse_posts_from_analytics_html(html)
        sum_post_impressions = None
        if html_posts_for_sum:
            try:
                sum_post_impressions = sum(int(p.get('impressions') or 0) for p in html_posts_for_sum)
            except Exception:
                sum_post_impressions = None
        # Prefer the computed sum when available; still report the page total separately
        safe_impressions = float(sum_post_impressions) if sum_post_impressions is not None else impressions

        print("\n=================== Riepilogo LinkedIn Analytics ===================")
        print(f"Impressioni totali (usate): {int(safe_impressions) if safe_impressions else 'ND'}")
        if impressions is not None:
            print(f"Impressioni totali (pagina): {int(impressions) if float(impressions).is_integer() else impressions}")
        if sum_post_impressions is not None:
            print(f"Impressioni totali (somma per post): {sum_post_impressions}")
        print(f"Utenti raggiunti (spettatori unici): {int(unique_viewers) if unique_viewers else 'ND'}")
        print("====================================================================\n")
        print("File salvati: analytics.pdf, analytics_text_from_pdf.txt, analytics_posts_blocks.html (se presenti blocchi)")

        try:
            # CSV minimale richiesto
            df = pd.DataFrame([{ 'Impressioni': safe_impressions, 'UtentiRaggiunti': unique_viewers }])
            df.to_csv("analytics_impressioni_utenti.csv", index=False, encoding="utf-8")

            # CSV esteso con tutte le metriche trovate
            extended_row = {
                'Impressions': safe_impressions,
                'UniqueViewers': analytics.get('UniqueViewers') if analytics else None,
                'Reactions': analytics.get('Reactions') if analytics else None,
                'Comments': analytics.get('Comments') if analytics else None,
                'Reposts': analytics.get('Reposts') if analytics else None,
                'Follows': analytics.get('Follows') if analytics else None,
                'EngagementRate': analytics.get('EngagementRate') if analytics else None,
            }
            pd.DataFrame([extended_row]).to_csv("analytics_totals.csv", index=False, encoding="utf-8")
        except Exception:
            pass

        # If you still want the old verbose section below, keep it; otherwise return here
        # return
        hashtags = extract_hashtags_from_html(html)

        if analytics:
            # Prefer analytics metrics if available
            print("\n================ LinkedIn Analytics - Riepilogo ================")
            print(f"Profilo: {user_input.profile_slug}")
            print("\nMetriche totali (pagina Analytics):")
            for k, v in analytics.items():
                print(f"- {k}: {int(v) if v.is_integer() else round(v, 2)}")
            # Per-post details (giornaliero/relativo)
            # Prefer HTML-structured per-post impressions when available
            html_posts = parse_posts_from_analytics_html(html)
            if html_posts:
                print("\nDettagli post (impressioni per post):")
                for idx, p in enumerate(html_posts[:50], start=1):
                    print(f"• Post {idx}: Impressioni: {p.get('impressions')}")
            elif full_text:
                posts = parse_posts_blocks(full_text)
                if posts:
                    print("\nDettagli post (tempo relativo, impressioni, likes, commenti):")
                    for p in posts[:20]:
                        rt = p.get('relativeTime') or '-'
                        im = p.get('impressions')
                        lk = p.get('likes')
                        cm = p.get('comments')
                        print(f"• {rt} | Impressioni: {im} | Likes: {lk} | Commenti: {cm}")
            if hashtags:
                print("\nHashtag trovati:")
                print(", ".join(hashtags[:20]))
            print("===============================================================\n")
        else:
            # Fallback disabilitato quando stampiamo HTML e ritorniamo prima
            pass
    finally:
        driver.quit()


if __name__ == "__main__":
    main()


