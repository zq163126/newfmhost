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


def mark_click_point(page, x, y):
    """在页面指定坐标绘制一个红点 marker，方便在截图中追踪点击位置"""
    try:
        page.evaluate(
            """
            ([x, y]) => {
                const dot = document.createElement('div');
                dot.style.position = 'fixed';
                dot.style.left = (x - 10) + 'px';
                dot.style.top = (y - 10) + 'px';
                dot.style.width = '20px';
                dot.style.height = '20px';
                dot.style.backgroundColor = 'rgba(255, 0, 0, 0.85)';
                dot.style.borderRadius = '50%';
                dot.style.border = '2px solid white';
                dot.style.boxShadow = '0 0 10px rgba(255, 0, 0, 0.8)';
                dot.style.zIndex = '999999';
                dot.style.pointerEvents = 'none'; // 确保标记点不阻挡后续点击
                document.body.appendChild(dot);
            }
            """,
            [x, y],
        )
    except Exception:
        pass


def dismiss_ads(page):
    """优化版去广告函数：最优先点击空白处（width - 250, 200）清理遮罩"""
    try:
        viewport = page.viewport_size or {"width": 1280, "height": 800}
        safe_x = viewport["width"] - 250
        safe_y = 200
        mark_click_point(page, safe_x, safe_y)
        page.mouse.click(safe_x, safe_y)
        page.wait_for_timeout(300)
    except Exception:
        pass

    # 注入 JS 关弹窗
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

    # Playwright 常规 Selector 清理
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
    """彻底跳过 is_visible 检查，采用：点空白处去广告 -> 强制点击目标 的重试循环"""
    for attempt in range(max_attempts):
        # 1. 强制点击空白处消灭可能的遮罩
        dismiss_ads(page)

        # 2. 尝试强制点击目标元素，避开 Playwright 严格的可见性检查
        try:
            locator.click(force=True, timeout=1500)
            print(f"-> 成功点击目标元素（第 {attempt + 1} 次尝试）")
            return True
        except Exception:
            # 没点击成功说明元素可能还在加载中，等待后继续重试
            page.wait_for_timeout(1000)

    # 超过最大尝试次数，抛出更清晰的提示
    raise RuntimeError(f"未能成功点击目标元素 ({locator})，即使已多次进行去广告重试。")


def human_mouse_click(page, locator):
    """定位元素并使用模拟真实鼠标轨迹移动点击"""
    locator.wait_for(state="attached", timeout=10000)

    # 确保元素进入视图
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    box = locator.bounding_box()
    if not box:
        locator.click(force=True)
        return

    # 计算目标中心点并加微小的随机偏移，模仿真人点击
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
            page.goto("https://new.freemchost.com/login", wait_until="networkidle")
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
                print("-> 成功检测到后台特征 URL，登录验证通过！")
            except Exception:
                raise RuntimeError(
                    f"登录状态验证失败。页面未按预期跳转到后台系统 (当前 URL: {page.url})。"
                )

            print("5. 正在跳转至指定的目标服务器面板页面...")
            page.goto(
                "https://new.freemchost.com/app/servers/7aa14245-4754-47ba-9bf9-d76da413761d",
                wait_until="networkidle",
            )
            # 跳转后第一时间清除全局广告遮罩
            dismiss_ads(page)

            print("6. 正在寻找并点击 Manage 标签页...")
            manage_tab = page.locator('button[role="tab"]:has-text("Manage")')
            # 采用全新的强行点击 + 去广告重试逻辑
            wait_and_click(page, manage_tab, max_attempts=12)

            page.wait_for_timeout(2000)

            print("7. 正在获取 Renew 操作前的时间...")
            time_before = get_remaining_time(page)
            print(f"-> 续期前时间: {time_before}")

            print("8. 正在点击 Renew now 按钮...")
            renew_btn = page.locator('button:has-text("Renew now")').first
            wait_and_click(page, renew_btn, max_attempts=8)

            print("9. 正在定位并点击 72 hours 续期选项按钮...")
            dismiss_ads(page)
            option_btn_72h = page.locator('button:has-text("72 hours")').first
            human_mouse_click(page, option_btn_72h)

            print("10. 等待数据更新...")
            page.wait_for_timeout(5000)
            dismiss_ads(page)

            print("11. 正在获取 Renew 操作后的时间...")
            time_after = get_remaining_time(page)
            print(f"-> 续期后时间: {time_after}")

            # 保存成功截图
            page.screenshot(path=screenshot_path, full_page=True)

            report_msg = (
                f"🎉 **Freemchost 自动续期任务执行成功**\n\n"
                f"👤 **账号**: `{EMAIL}`\n"
                f"⏳ **续期前剩余**: {time_before}\n"
                f"⏳ **续期后剩余**: {time_after}\n"
                f"⏰ **执行时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            send_telegram_message(report_msg, screenshot_path)

        except Exception as e:
            print(f"❌ 运行过程中发生错误: {e}")
            try:
                # 发生异常时，先去一次广告并抓取现场截图，确保发送的截图能真实反映异常时的页面
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
