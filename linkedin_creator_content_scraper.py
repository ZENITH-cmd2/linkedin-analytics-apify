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
    # Split and
