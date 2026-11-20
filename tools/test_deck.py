#!/usr/bin/env python3
"""
test_deck.py — 演示模式交互自测（键盘导航 / 逐步揭示 / 总览 / 备注 / 深链 / 计数）

用法: python3 tools/test_deck.py
退出码 0 = 全部通过
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = (ROOT / "index.html").resolve().as_uri()

ok, fail = [], []


def check(name, cond, extra=""):
    (ok if cond else fail).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (f"   {extra}" if extra and not cond else ""))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL, wait_until="load")
        page.wait_for_timeout(1200)

        total = page.evaluate("() => window.__deck.total")
        print(f"\n总屏数 {total}\n")

        # --- 1. 初始状态 ---
        check("初始在第 1 屏", page.evaluate("() => window.__deck.index") == 0)
        check("第 1 屏为 is-active",
              page.evaluate("() => document.querySelector('.slide').classList.contains('is-active')"))
        check("页脚自动注入", page.evaluate("""() =>
          [...document.querySelectorAll('.slide:not([data-nofoot])')]
            .every(slide => slide.querySelector(':scope > .foot'))
        """))
        check("进度条段数 = 屏数",
              page.evaluate("() => document.querySelectorAll('.chrome__progress i').length") == total)
        check("总览卡片数 = 屏数",
              page.evaluate("() => document.querySelectorAll('.ov-card').length") == total)

        # --- 2. 键盘下一屏 ---
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(600)
        check("→ 进入第 2 屏", page.evaluate("() => window.__deck.index") == 1)
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(600)
        check("← 回到第 1 屏", page.evaluate("() => window.__deck.index") == 0)

        # --- 3. End / Home ---
        page.keyboard.press("End")
        page.wait_for_timeout(600)
        check("End 跳到最后一屏", page.evaluate("() => window.__deck.index") == total - 1)
        page.keyboard.press("Home")
        page.wait_for_timeout(600)
        check("Home 回到第一屏", page.evaluate("() => window.__deck.index") == 0)

        # --- 4. 数字滚动落值 ---
        counter = page.locator(".slide [data-count]").first
        if counter.count():
            expected = counter.evaluate("""el => {
              const { count, dec = 0, prefix = '', suffix = '' } = el.dataset;
              const slide = el.closest('.slide');
              window.__deck.go([...document.querySelectorAll('.slide')].indexOf(slide));
              return prefix + Number(count).toLocaleString('en-US', {
                minimumFractionDigits: Number(dec), maximumFractionDigits: Number(dec)
              }) + suffix;
            }""")
            page.wait_for_timeout(1800)
            actual = counter.inner_text().strip()
            check("计数器显示目标值", actual == expected.strip(), f"got {actual!r}, expected {expected!r}")

        # --- 5. 总览 ---
        page.keyboard.press("g")
        page.wait_for_timeout(500)
        check("G 打开总览", page.evaluate("() => document.querySelector('.overview').classList.contains('is-open')"))
        page.evaluate("() => document.querySelectorAll('.ov-card')[7].click()")
        page.wait_for_timeout(600)
        check("点总览卡片跳转", page.evaluate("() => window.__deck.index") == 7)
        check("跳转后总览关闭", not page.evaluate("() => document.querySelector('.overview').classList.contains('is-open')"))

        # --- 6. 备注 ---
        page.keyboard.press("n")
        page.wait_for_timeout(500)
        check("N 打开备注", page.evaluate("() => document.querySelector('.notebar').classList.contains('is-open')"))
        has_note = page.evaluate("() => document.querySelector('.notebar__body').textContent.trim().length > 4")
        check("备注有内容", has_note)
        page.keyboard.press("n")
        page.wait_for_timeout(400)

        # --- 7. 深链 ---
        page.goto(URL + "#s5", wait_until="load")
        page.wait_for_timeout(900)
        check("#s5 深链进入第 5 屏", page.evaluate("() => window.__deck.index") == 4)

        # --- 8. 缩放自适应 ---
        for w, h in [(1440, 900), (1024, 700), (390, 844)]:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(600)   # 等缩放过渡落定
            scale = page.evaluate("() => window.__deck.scale")
            fits = page.evaluate("""() => {
              const r = document.querySelector('.stage').getBoundingClientRect();
              return r.width <= window.innerWidth + 1 && r.height <= window.innerHeight + 1;
            }""")
            check(f"{w}×{h} 舞台不超出视口", fits, f"scale={scale:.3f}")

        # --- 9. 图标是 SVG 不是 emoji ---
        emoji = page.evaluate("""() => {
          const re = /[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u;
          return [...document.querySelectorAll('.slide *')].filter(el =>
            [...el.childNodes].some(n => n.nodeType === 3 && re.test(n.textContent))).length;
        }""")
        check("画面内无 emoji 图标", emoji == 0, f"found {emoji}")

        # --- 10. 图片全部加载 ---
        broken = page.evaluate("""() => [...document.querySelectorAll('.slide img')]
            .filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src'))""")
        check("图片全部加载", len(broken) == 0, str(broken))

        # --- 11. 缺字风险：字体族 ---
        check("标题使用衬线字体栈",
              page.evaluate("() => getComputedStyle(document.querySelector('.title, .cover__title')).fontFamily.includes('Songti')"))

        if errors:
            print("\n页面异常:")
            for e in errors[:5]:
                print("  !", e[:200])

        browser.close()

    print(f"\n通过 {len(ok)} / {len(ok) + len(fail)}")
    if fail:
        print("失败：" + "、".join(fail))
    sys.exit(1 if (fail or errors) else 0)


if __name__ == "__main__":
    main()
