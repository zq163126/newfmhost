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
    """辅助函数：打日志、截图并即时发送 Telegram 进度"""
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
        "button:has(svg.lucide-x)",
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

    raise RuntimeError(
        f"未能成功点击目标元素 ({locator})，当前页面 URL: {page.url}"
    )


def click_renew_now_robust(page):
    """全方位穿透式点击 Renew now 按钮"""
    dismiss_ads(page)
    print("-> 正在强力触发 Renew now...")
    
    result = page.evaluate("""
        () => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const targetBtn = buttons.find(b => b.textContent && b.textContent.includes('Renew now'));

            if (!targetBtn) return { success: false, reason: 'No Renew now button found' };

            targetBtn.removeAttribute('disabled');
            targetBtn.style.pointerEvents = 'auto';

            const mouseEvents = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
            mouseEvents.forEach(eventType => {
                const event = new MouseEvent(eventType, {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                targetBtn.dispatchEvent(event);
            });

            if (typeof targetBtn.click === 'function') {
                targetBtn.click();
            }

            return { success: true };
        }
    """)
    print(f"-> Renew now 点击结果: {result}")


def click_discord_confirm_robust(page):
    """完美融合版：利用之前百分百能定位文字的逻辑获取按钮，再通过物理坐标精准点击"""
    dismiss_ads(page)
    print("-> 正在弹窗内部寻找 Discord 续期按钮...")

    # 1. 优先等待弹窗（dialog）出现
    dialog = page.locator('div[role="dialog"]').first
    try:
        dialog.wait_for(state="visible", timeout=5000)
        page.wait_for_timeout(600)  # 等待弹窗动画完全结束，确保元素稳定
        print("-> 已检测到确认弹窗展开")
    except Exception:
        print("-> 未检测到标准的 dialog 弹窗，尝试全局搜索...")

    # 2. 使用之前验证过成功的 JS 逻辑来查找按钮并获取其坐标
    coord_result = page.evaluate("""
        () => {
            const dialog = document.querySelector('div[role="dialog"]') || document;
            const buttons = Array.from(dialog.querySelectorAll('button'));
            
            const allTexts = buttons.map(b => b.textContent.replace(/\\s+/g, ' ').trim());
            console.log("弹窗内找到的所有按钮文本:", allTexts);

            // 只通过 Discord 关键字进行匹配
            const targetBtn = buttons.find(b => {
                const text = b.textContent.replace(/\\s+/g, ' ').trim();
                return text.includes('Discord');
            });

            if (!targetBtn) {
                return { success: false, allTexts: allTexts };
            }

            // 获取该按钮在视口中的精确位置
            const rect = targetBtn.getBoundingClientRect();
            return {
                success: true,
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                clickedText: targetBtn.textContent.replace(/\\s+/g, ' ').trim()
            };
        }
    """)

    if isinstance(coord_result, dict) and coord_result.get("success"):
        x = coord_result.get("x")
        y = coord_result.get("y")
        clicked_text = coord_result.get("clickedText")
        print(f"-> 成功定位 Discord 按钮，文本: [{clicked_text[:30]}...]，坐标: X={x:.1f}, Y={y:.1f}")
        
        try:
            # 采用 Playwright 真实物理鼠标点击
            page.mouse.click(x, y)
            print("-> 成功通过物理坐标点击 Discord 确认按钮")
            return
        except Exception as e:
            print(f"-> 物理坐标点击异常，尝试使用内置事件派发兜底: {e}")

    # 3. 如果坐标点击有意外，执行原本的事件派发兜底
    print("-> 正在执行内置事件派发兜底...")
    success = page.evaluate("""
        () => {
            const dialog = document.querySelector('div[role="dialog"]') || document;
            const buttons = Array.from(dialog.querySelectorAll('button'));
            const targetBtn = buttons.find(b => b.textContent && b.textContent.includes('Discord'));
            
            if (!targetBtn) return false;

            targetBtn.removeAttribute('disabled');
            targetBtn.style.pointerEvents = 'auto';

            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(eventType => {
                targetBtn.dispatchEvent(new MouseEvent(eventType, {
                    bubbles: true,
                    cancelable: true,
                    view: window
                }));
            });

            if (typeof targetBtn.click === 'function') {
                targetBtn.click();
            }
            return true;
        }
    """)

    if success:
        print("-> 成功通过事件派发机制触发点击")
        return

    # 4. 终极 Playwright 文本过滤兜底
    print("-> 尝试使用 Playwright 文本强行定位点击...")
    try:
        target_locator = page.locator('div[role="dialog"] button').filter(has_text=re.compile("Discord", re.IGNORECASE)).first
        target_locator.wait_for(state="visible", timeout=3000)
        target_locator.click(force=True)
        print("-> 通过 Playwright 文本过滤器成功点击")
        return
    except Exception as e:
        raise RuntimeError(f"未能成功点击弹窗内的 Discord 续期确认按钮: {e}")


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
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]
        browser = p.chromium.launch(headless=True, args=launch_args)

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
            dismiss_ads(page)

            print("2. 正在输入凭据...")
            page.locator("#email").fill(EMAIL)
            page.locator("#password").fill(PASSWORD)

            print("3. 点击 Sign in...")
            signin_btn = page.locator(
                'button[type="submit"]:has-text("Sign in")'
            )
            wait_and_click(page, signin_btn)

            print("4. 正在验证登录状态（等待页面跳转至后台）...")
            try:
                page.wait_for_url(
                    "**/app**", timeout=15000, wait_until="networkidle"
                )
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

            print("6. 正在寻找并点击 Manage 标签页（共点击 2 次，间隔 2 秒）...")
            manage_tab = page.locator(
                'button[role="tab"]:has-text("Manage"), button:has-text("Manage")'
            )

            print("-> 第一次点击 Manage...")
            wait_and_click(page, manage_tab, max_attempts=12)
            page.wait_for_timeout(2000)

            print("-> 第二次点击 Manage...")
            wait_and_click(page, manage_tab, max_attempts=12)
            page.wait_for_timeout(2000)

            capture_step(page, "步骤 6: 已完成 2 次 Manage 标签页点击")

            print("7. 正在获取 Renew 操作前的时间并进行判断...")
            time_before = get_remaining_time(page)
            total_hours = parse_total_hours(time_before)
            print(
                f"-> 当前剩余续期时间: {time_before} (折合 {total_hours} 小时)"
            )
            capture_step(
                page,
                f"步骤 7: 已读取续期前时间 ({time_before}, {total_hours}h)",
            )

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

            print("8. 剩余时间小于等于 36 小时，正在执行 Renew now 全套事件派发点击...")
            click_renew_now_robust(page)
            page.wait_for_timeout(3000)

            capture_step(page, "步骤 8: 已完成 Renew now 按钮点击")

            print("9. 正在尝试检测并点击弹窗内的 Discord 续期按钮...")
            click_discord_confirm_robust(page)
            capture_step(page, "步骤 9: 检查完毕")

            print("10. 等待数据更新...")
            page.wait_for_timeout(5000)
            dismiss_ads(page)
            capture_step(page, "步骤 10: 续期等待完成，准备读取最新时间")

            print("11. 正在获取 Renew 操作后的时间...")
            time_after = get_remaining_time(page)
            total_hours_after = parse_total_hours(time_after)
            print(
                f"-> 续期后时间: {time_after} (折合 {total_hours_after} 小时)"
            )
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
