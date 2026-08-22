import os
import re
import time
import random
import requests
from playwright.sync_api import sync_playwright

# 从环境变量中读取配置
EMAIL = os.environ.get("WEB_EMAIL")
PASSWORD = os.environ.get("WEB_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")


def send_telegram_message(text, photo_path=None):
    """发送文字消息和截图到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置不完整，跳过发送消息。")
        return

    # 发送文本
    text_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    text_data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(text_url, json=text_data)
        print("Telegram 文本消息发送成功")
    except Exception as e:
        print(f"发送 Telegram 文本失败: {e}")

    # 发送图片
    if photo_path and os.path.exists(photo_path):
        photo_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
        try:
            with open(photo_path, "rb") as photo:
                files = {"photo": photo}
                data = {"chat_id": TG_CHAT_ID}
                requests.post(photo_url, data=data, files=files)
            print("Telegram 截图发送成功")
        except Exception as e:
            print(f"发送 Telegram 截图失败: {e}")


def capture_step(page, step_name, screenshot_path="step_temp.png"):
    """辅助函数：打日志、截图并即时发送 Telegram 进度"""
    print(f"📸 正在捕获过程截图: {step_name}")
    try:
        page.screenshot(path=screenshot_path, full_page=True)
        send_telegram_message(
            f"📍 **进度调试**: {step_name}\n🔗 当前 URL: `{page.url}`", screenshot_path
        )
    except Exception as e:
        print(f"捕获或发送过程截图失败: {e}")


def dismiss_ads(page):
    """纯 DOM/CSS 级去广告函数"""
    try:
        page.add_style_tag(
            content="""
            iframe[src*="google"], iframe[src*="ad"], 
            [id*="google_ads"], [class*="ad-container"],
            div[class*="backdrop"]:not([role="dialog"]) {
                display: none !important;
                pointer-events: none !important;
            }
        """
        )
    except Exception:
        pass

    js_close_script = """
    () => {
        const closeIcons = Array.from(document.querySelectorAll('svg.lucide-x, #dismiss-button'));
        for (const icon of closeIcons) {
            const btn = icon.closest('button') || icon;
            if (btn && typeof btn.click === 'function') {
                btn.click();
            }
        }
        const srCloses = Array.from(document.querySelectorAll('span.sr-only'));
        for (const span of srCloses) {
            if (span.textContent.trim() === 'Close') {
                const btn = span.closest('button');
                if (btn) btn.click();
            }
        }
    }
    """

    frames = [page] + page.frames
    for frame in frames:
        try:
            frame.evaluate(js_close_script)
        except Exception:
            pass

    ad_selectors = [
        'button:has(svg.lucide-x)',
        'button:has-text("Close")',
        'button:has(span:has-text("Close"))',
        '//*[@id="dismiss-button"]',
        'button[aria-label="Close"]',
    ]

    for frame in frames:
        for selector in ad_selectors:
            try:
                elements = frame.locator(selector)
                count = elements.count()
                for i in range(count):
                    el = elements.nth(i)
                    if el.is_visible(timeout=200):
                        try:
                            el.click(force=True, timeout=500)
                        except Exception:
                            el.dispatch_event("click")
            except Exception:
                pass


def wait_and_click(page, locator, max_attempts=10):
    """等待并强制点击元素"""
    for attempt in range(max_attempts):
        dismiss_ads(page)

        try:
            locator.first.click(force=True, timeout=1500)
            print(f"-> 成功点击目标元素（第 {attempt + 1} 次尝试）")
            return True
        except Exception:
            page.wait_for_timeout(1000)

    raise RuntimeError(f"未能成功点击目标元素 ({locator})，当前页面 URL: {page.url}")


def human_mouse_click(page, locator):
    """定位元素并使用模拟真实鼠标轨迹移动点击"""
    locator.wait_for(state="attached", timeout=10000)

    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    box = locator.bounding_box()
    if not box:
        locator.click(force=True)
        return

    target_x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
    target_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)

    start_x = random.randint(100, 500)
    start_y = random.randint(100, 500)

    steps = random.randint(10, 25)
    for i in range(1, steps + 1):
        curr_x = start_x + (target_x - start_x) * (i / steps)
        curr_y = start_y + (target_y - start_y) * (i / steps)
        page.mouse.move(curr_x, curr_y)
        time.sleep(random.uniform(0.005, 0.015))

    page.wait_for_timeout(random.randint(100, 200))
    page.mouse.click(target_x, target_y)


def get_remaining_time(page):
    """获取当前的剩余续期时间"""
    timer_element = page.locator('div[role="timer"]').first
    timer_element.wait_for(state="visible", timeout=15000)

    aria_label = timer_element.get_attribute("aria-label")
    if aria_label:
        return aria_label

    text_content = timer_element.inner_text()
    clean_text = re.sub(r"\s+", " ", text_content).strip()
    return clean_text if clean_text else "未知时间"


def parse_total_hours(time_str):
    """将时间文本统一换算为总小时数"""
    days = 0
    hours = 0

    d_match = re.search(r"(\d+)\s*(?:d|day)", time_str, re.IGNORECASE)
    if d_match:
        days = int(d_match.group(1))

    h_match = re.search(r"(\d+)\s*(?:h|hour)", time_str, re.IGNORECASE)
    if h_match:
        hours = int(h_match.group(1))

    return days * 24 + hours


def run():
    if not EMAIL or not PASSWORD:
        print("错误: 环境变量中未检测到 EMAIL 或 PASSWORD。")
        return

    screenshot_path = "result.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            print("1. 正在访问登录页面...")
            page.goto("https://freemchost.com/login", wait_until="networkidle")
            dismiss_ads(page)

            print("2. 正在输入凭据...")
            page.locator("#email").fill(EMAIL)
            page.locator("#password").fill(PASSWORD)

            print("3. 点击 Sign in...")
            signin_btn = page.locator('button[type="submit"]:has-text("Sign in")')
            wait_and_click(page, signin_btn)

            print("4. 正在验证登录状态（等待页面跳转至后台）...")
            try:
                page.wait_for_url("**/app**", timeout=15000, wait_until="networkidle")
                print(f"-> 成功检测到后台特征 URL，当前位置: {page.url}")
            except Exception:
                raise RuntimeError(
                    f"登录状态验证失败。页面未按预期跳转到后台系统 (当前 URL: {page.url})。"
                )

            print("5. 正在跳转至指定的目标服务器面板页面...")
            page.goto(
                "https://freemchost.com/app/servers/2f12a6bd-a1c1-4cc1-bd32-8becf1925680",
                wait_until="networkidle",
            )
            page.wait_for_timeout(2000)
            dismiss_ads(page)
            capture_step(page, "步骤 5: 已跳转到目标服务器页面")

            print("6. 正在寻找并点击 Manage 标签页...")
            manage_tab = page.locator(
                'button[role="tab"]:has-text("Manage"), button:has-text("Manage")'
            )
            wait_and_click(page, manage_tab, max_attempts=12)
            page.wait_for_timeout(2000)
            capture_step(page, "步骤 6: 已点击 Manage 标签页")

            print("7. 正在获取 Renew 操作前的时间并进行判断...")
            time_before = get_remaining_time(page)
            total_hours = parse_total_hours(time_before)
            print(f"-> 当前剩余续期时间: {time_before} (折合 {total_hours} 小时)")
            capture_step(page, f"步骤 7: 已读取续期前时间 ({time_before}, {total_hours}h)")

            # 统一按小时判断：若大于 36 小时则无需续期直接退出
            if total_hours > 36:
                msg = (
                    f"ℹ️ **Freemchost 自动续期跳过**\n\n"
                    f"👤 **账号**: `{EMAIL}`\n"
                    f"⏳ **当前剩余时间**: {time_before} (约 {total_hours} 小时)\n"
                    f"💡 **提示**: 剩余时间大于 36 小时，无需续期，已自动退出任务。"
                )
                print(f"-> {msg}")
                send_telegram_message(msg, "step_temp.png")
                return

            print("8. 剩余时间小于等于 36 小时，正在点击 Renew now 按钮...")
            renew_btn = page.locator('button:has-text("Renew now")')
            wait_and_click(page, renew_btn, max_attempts=8)
            capture_step(page, "步骤 8: 已点击 Renew now 按钮")

            print("9. 基于 Discord Boost 固定文本定位并点击续期确认按钮...")
            dismiss_ads(page)

            discord_section = page.locator(
                'div:has-text("Discord Boosted renewal — your linked Discord account gives you extra free time.")'
            ).last
            option_btn = discord_section.locator('button').first

            human_mouse_click(page, option_btn)
            capture_step(page, "步骤 9: 已点击基于 Discord Boost 锚点定位的续期按钮")

            print("10. 等待数据更新...")
            page.wait_for_timeout(5000)
            dismiss_ads(page)
            capture_step(page, "步骤 10: 续期等待完成，准备读取最新时间")

            print("11. 正在获取 Renew 操作后的时间...")
            time_after = get_remaining_time(page)
            total_hours_after = parse_total_hours(time_after)
            print(f"-> 续期后时间: {time_after} (折合 {total_hours_after} 小时)")
            capture_step(page, f"步骤 11: 续期结束，最新时间: {time_after}")

            page.screenshot(path=screenshot_path, full_page=True)

            report_msg = (
                f"🎉 **Freemchost 自动续期任务全部成功**\n\n"
                f"👤 **账号**: `{EMAIL}`\n"
                f"⏳ **续期前剩余**: {time_before} ({total_hours}h)\n"
                f"⏳ **续期后剩余**: {time_after} ({total_hours_after}h)\n"
                f"⏰ **执行时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            send_telegram_message(report_msg, screenshot_path)

        except Exception as e:
            print(f"❌ 运行过程中发生错误: {e}")
            try:
                dismiss_ads(page)
                page.screenshot(path=screenshot_path, full_page=True)
                error_msg = f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}`"
                send_telegram_message(error_msg, screenshot_path)
            except Exception:
                send_telegram_message(
                    f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}` (未能截取到画面)"
                )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
