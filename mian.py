import os
import random
import re
import time
from playwright.sync_api import sync_playwright
import requests

# 从环境变量中读取配置
EMAIL = os.environ.get("WEB_EMAIL")
PASSWORD = os.environ.get("WEB_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
PROXY_SOCKS5 = os.environ.get("PROXY_SOCKS5", "").strip()

TARGET_URL = "https://freemchost.com/app/servers/0ac36ad6-6dbe-4766-a92e-498d68866539"


def send_telegram_message(text, photo_path=None):
    """发送文字消息和截图到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置不完整，跳过发送消息。")
        return

    text_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    text_data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(text_url, json=text_data)
        print("Telegram 文本消息发送成功")
    except Exception as e:
        print(f"发送 Telegram 文本失败: {e}")

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
    """辅助函数：打日志,截图并即时发送 Telegram 进度"""
    print(f"📸 正在捕获过程截图: {step_name}")
    try:
        page.screenshot(path=screenshot_path, full_page=True)
        send_telegram_message(
            f"📍 **进度调试**: {step_name}\n🔗 当前 URL: `{page.url}`",
            screenshot_path,
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


def dismiss_maybe_later(page):
    """检测并点击 'Maybe later' 广告按钮"""
    try:
        btn = page.locator('button:has-text("Maybe later")')
        if btn.count() > 0 and btn.first.is_visible(timeout=500):
            print("-> 检测到 'Maybe later' 广告按钮，正在点击...")
            btn.first.click(force=True, timeout=1000)
            time.sleep(1)
    except Exception:
        pass


def wait_and_click(page, locator, max_attempts=10):
    """等待并强制点击元素"""
    for attempt in range(max_attempts):
        dismiss_ads(page)
        dismiss_maybe_later(page)

        try:
            locator.first.click(force=True, timeout=1500)
            print(f"-> 成功点击目标元素（第 {attempt + 1} 次尝试）")
            time.sleep(3)
            return True
        except Exception:
            time.sleep(1)

    raise RuntimeError(
        f"未能成功点击目标元素 ({locator})，当前页面 URL: {page.url}"
    )


def human_move_and_click(page, locator):
    """从随机起点模拟人工移动到元素内部随机坐标并点击"""
    box = locator.bounding_box()
    viewport = page.viewport_size or {'width': 1280, 'height': 800}
    
    # 随机起点（视口内随机一个坐标）
    start_x = random.uniform(50, viewport['width'] - 50)
    start_y = random.uniform(50, viewport['height'] - 50)
    page.mouse.move(start_x, start_y)
    time.sleep(random.uniform(0.1, 0.3))

    if box:
        pad_x = min(4, box['width'] * 0.2)
        pad_y = min(4, box['height'] * 0.2)
        target_x = box['x'] + random.uniform(pad_x, max(pad_x + 1, box['width'] - pad_x))
        target_y = box['y'] + random.uniform(pad_y, max(pad_y + 1, box['height'] - pad_y))
    else:
        target_x, target_y = viewport['width'] / 2, viewport['height'] / 2

    # 模拟多段抖动滑过去
    steps = random.randint(12, 22)
    for i in range(1, steps + 1):
        t = i / steps
        curr_x = start_x + (target_x - start_x) * t + random.uniform(-3, 3)
        curr_y = start_y + (target_y - start_y) * t + random.uniform(-3, 3)
        page.mouse.move(curr_x, curr_y)
        time.sleep(random.uniform(0.012, 0.03))

    # 精准到达目标随机点
    page.mouse.move(target_x, target_y)
    time.sleep(random.uniform(0.05, 0.15))
    page.mouse.down()
    time.sleep(random.uniform(0.06, 0.14))
    page.mouse.up()


def click_renew_now_robust(page):
    """点击页面上的 Renew now 按钮"""
    dismiss_maybe_later(page)
    dismiss_ads(page)
    print("-> 寻找并点击页面 Renew now 按钮...")
    renew_btn = page.locator('button:has-text("Renew now")').first
    renew_btn.wait_for(state="visible", timeout=10000)
    
    page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const target = btns.find(b => b.textContent && b.textContent.includes('Renew now'));
        if (target) {
            target.removeAttribute('disabled');
            target.style.pointerEvents = 'auto';
            target.click();
        }
    }""")
    time.sleep(3)


def click_discord_boost_renewal(page):
    """在弹出的 Dialog 中选择并点击 Discord Boosted renewal (60 hours)"""
    dismiss_maybe_later(page)
    print("-> 正在定位并点击 Discord Boosted renewal 选项...")
    try:
        dialog = page.locator('div[role="dialog"]').last
        dialog.wait_for(state="visible", timeout=10000)
        time.sleep(1.5)

        target_btn = dialog.locator('button:has-text("Discord Boosted renewal"), button:has-text("60 hours")').first
        target_btn.wait_for(state="visible", timeout=5000)

        target_btn.evaluate("""el => {
            el.style.border = '4px solid red';
            el.style.backgroundColor = 'yellow';
        }""")
        time.sleep(0.5)

        human_move_and_click(page, target_btn)
        print("-> 已完成 Discord Boosted renewal 选项的真人轨迹点击")
        time.sleep(4)

        debug_screenshot_path = "click_debug.png"
        page.screenshot(path=debug_screenshot_path, full_page=True)
        send_telegram_message(
            "📍 **弹窗交互调试**: 已点击 Discord Boosted renewal (60 hours)！",
            debug_screenshot_path,
        )
    except Exception as e:
        raise RuntimeError(f"点击 Discord Boosted renewal 失败: {e}")


def get_remaining_time(page):
    """获取当前的剩余续期时间"""
    dismiss_maybe_later(page)
    timer_element = page.locator('span[role="timer"], div[role="timer"]').first
    timer_element.wait_for(state="visible", timeout=15000)

    aria_label = timer_element.get_attribute("aria-label")
    if aria_label:
        return aria_label

    text_content = timer_element.inner_text()
    clean_text = re.sub(r"\s+", " ", text_content).strip()
    return clean_text if clean_text else "未知时间"


def parse_total_hours(time_str):
    """将类似 '2d 21h 32m 15s remaining' 的文本换算为总小时数"""
    days = 0
    hours = 0
    minutes = 0

    d_match = re.search(r"(\d+)\s*d", time_str, re.IGNORECASE)
    if d_match:
        days = int(d_match.group(1))

    h_match = re.search(r"(\d+)\s*h", time_str, re.IGNORECASE)
    if h_match:
        hours = int(h_match.group(1))

    m_match = re.search(r"(\d+)\s*m", time_str, re.IGNORECASE)
    if m_match:
        minutes = int(m_match.group(1))

    return days * 24 + hours + minutes / 60.0


def run():
    if not EMAIL or not PASSWORD:
        print("错误: 环境变量中未检测到 EMAIL 或 PASSWORD。")
        return

    screenshot_path = "result.png"

    with sync_playwright() as p:
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]
        # 有头模式 headless=False（结合 GitHub Actions 的 xvfb-run 运行）
        browser = p.chromium.launch(headless=False, args=launch_args)

        context_args = {"viewport": {"width": 1280, "height": 800}}
        if PROXY_SOCKS5:
            print(f"-> 成功绑定代理通道: {PROXY_SOCKS5}")
            context_args["proxy"] = {"server": PROXY_SOCKS5}
        else:
            print("-> 未检测到代理配置，使用直连模式。")

        context = browser.new_context(**context_args)
        page = context.new_page()

        try:
            print("1. 正在访问登录页面...")
            page.goto("https://freemchost.com/login", wait_until="networkidle")
            time.sleep(4)
            dismiss_ads(page)

            print("2. 正在输入凭据...")
            page.locator("#email").fill(EMAIL)
            time.sleep(1)
            page.locator("#password").fill(PASSWORD)
            time.sleep(1)

            print("3. 点击 Sign in...")
            signin_btn = page.locator('button[type="submit"]:has-text("Sign in")')
            wait_and_click(page, signin_btn)

            print("4. 正在验证登录状态并访问服务列表页...")
            page.wait_for_url("**/app**", timeout=15000, wait_until="networkidle")
            time.sleep(3)
            dismiss_maybe_later(page)
            page.goto("https://freemchost.com/app/servers", wait_until="networkidle")
            time.sleep(3)
            dismiss_ads(page)
            dismiss_maybe_later(page)
            capture_step(page, "步骤 4: 已访问服务总览页 /app/servers")

            print("5. 正在获取剩余续期时间并判断（<= 24小时阈值）...")
            time_before = get_remaining_time(page)
            total_hours = parse_total_hours(time_before)
            print(f"-> 当前剩余续期时间: {time_before} (约 {total_hours:.1f} 小时)")
            capture_step(page, f"步骤 5: 读取剩余时间 ({time_before})")

            if total_hours > 24:
                msg = (
                    f"ℹ️ **Freemchost 自动续期跳过**\n\n"
                    f"👤 **账号**: `{EMAIL}`\n"
                    f"⏳ **当前剩余时间**: {time_before} (约 {total_hours:.1f} 小时)\n"
                    f"💡 **提示**: 剩余时间大于 24 小时，无需续期，已自动退出任务。"
                )
                print(f"-> {msg}")
                send_telegram_message(msg, "step_temp.png")
                return

            print("6. 剩余时间 <= 24 小时，正在访问目标服务器面板页面...")
            dismiss_maybe_later(page)
            page.goto(TARGET_URL, wait_until="networkidle")
            time.sleep(4)
            dismiss_ads(page)
            dismiss_maybe_later(page)
            capture_step(page, "步骤 6: 已跳转到目标服务器页面")

            print("6.1. 查找并点击 Billing 标签页...")
            dismiss_maybe_later(page)
            billing_tab = page.locator('button[role="tab"]:has-text("Billing")').first
            billing_tab.wait_for(state="visible", timeout=10000)
            billing_tab.click(force=True)
            time.sleep(2)

            print("7. 执行 Renew now...")
            click_renew_now_robust(page)
            capture_step(page, "步骤 7: 已点击 Renew now 按钮")

            print("8. 在弹出窗口中选择 Discord Boosted renewal (60 hours)...")
            click_discord_boost_renewal(page)

            print("9. 等待后端处理并刷新验证结果...")
            time.sleep(8)
            dismiss_ads(page)
            dismiss_maybe_later(page)

            print("10. 返回服务列表页获取续期后最新时间...")
            page.goto("https://freemchost.com/app/servers", wait_until="networkidle")
            time.sleep(4)
            dismiss_ads(page)
            dismiss_maybe_later(page)
            time_after = get_remaining_time(page)
            total_hours_after = parse_total_hours(time_after)
            print(f"-> 续期后时间: {time_after} (约 {total_hours_after:.1f} 小时)")
            capture_step(page, f"步骤 10: 续期结束，最新时间: {time_after}")

            page.screenshot(path=screenshot_path, full_page=True)

            report_msg = (
                f"🎉 **Freemchost 自动续期任务全部成功**\n\n"
                f"👤 **账号**: `{EMAIL}`\n"
                f"⏳ **续期前剩余**: {time_before}\n"
                f"⏳ **续期后剩余**: {time_after}\n"
                f"⏰ **执行时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            send_telegram_message(report_msg, screenshot_path)

        except Exception as e:
            print(f"❌ 运行过程中发生错误: {e}")
            try:
                dismiss_ads(page)
                dismiss_maybe_later(page)
                page.screenshot(path=screenshot_path, full_page=True)
                error_msg = f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}`"
                send_telegram_message(error_msg, screenshot_path)
            except Exception:
                send_telegram_message(
                    f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}` (未能截取画面)"
                )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
