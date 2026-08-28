import os
import random
import re
import time
import json
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


def wait_and_click(page, locator, max_attempts=10):
    """等待并强制点击元素"""
    for attempt in range(max_attempts):
        dismiss_ads(page)

        try:
            locator.first.click(force=True, timeout=1500)
            print(f"-> 成功点击目标元素（第 {attempt + 1} 次尝试）")
            time.sleep(4)  # 严格 4 秒延时
            return True
        except Exception:
            time.sleep(1)

    raise RuntimeError(
        f"未能成功点击目标元素 ({locator})，当前页面 URL: {page.url}"
    )


def click_renew_now_robust(page):
    """全方位穿透式点击 Renew now 按钮，附带严格延时"""
    dismiss_ads(page)
    print("-> 正在强力触发 Renew now...")

    page.evaluate("""
        () => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const targetBtn = buttons.find(b => b.textContent && b.textContent.includes('Renew now'));

            if (!targetBtn) return;

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
        }
    """)
    time.sleep(4)  # 点击后严格延时 4 秒等待弹窗完全展开


def click_discord_confirm_robust(page):
    """完美拟真鼠标轨迹版：加入严格的 4 秒前后缓冲延时"""
    print("-> 正在执行严格缓冲的真人鼠标轨迹点击...")

    try:
        # 1. 确保弹窗可见并稳定
        dialog = page.locator('div[role="dialog"]').first
        dialog.wait_for(state="visible", timeout=10000)
        time.sleep(4)  # 弹窗展开后强制等待 4 秒，确保动画和事件绑定完全就绪

        # 2. 定位到索引 [2] 的那个 Discord 按钮并获取坐标
        target_btn = page.locator('div[role="dialog"] button').nth(2)
        target_btn.scroll_into_view_if_needed()
        time.sleep(1)

        box = target_btn.bounding_box()
        if not box:
            raise RuntimeError("未能获取到 Discord 按钮的坐标信息")

        target_x = box["x"] + box["width"] / 2
        target_y = box["y"] + box["height"] / 2

        print(f"-> 目标按钮中心坐标: X={target_x}, Y={target_y}")

        # 3. 模拟人类习惯：鼠标先从页面上方的随机空白处出发
        start_x = random.randint(100, 300)
        start_y = random.randint(50, 150)
        page.mouse.move(start_x, start_y)
        time.sleep(1)

        print(f"-> 模拟鼠标从 ({start_x}, {start_y}) 出发，平滑移动到目标按钮...")

        # 4. 密集平滑移动轨迹
        page.mouse.move(target_x, target_y, steps=25)
        time.sleep(1)  # 悬停停顿 1 秒

        # 5. 执行物理按下与释放
        page.mouse.down(button="left")
        time.sleep(0.3)
        page.mouse.up(button="left")

        print("-> 真人轨迹物理点击动作已完成")
        
        # 6. 点击后严格延时 4 秒，等待后端接收请求
        time.sleep(4)

        # 7. 截图发送到 TG 观察效果
        debug_screenshot_path = "click_debug.png"
        page.screenshot(path=debug_screenshot_path, full_page=True)
        send_telegram_message(
            f"📍 **4秒缓冲轨迹点击调试**: 已完成滑动点击并等待响应！",
            debug_screenshot_path,
        )

    except Exception as e:
        raise RuntimeError(f"真人轨迹点击失败: {e}")


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
            time.sleep(4)
            dismiss_ads(page)

            print("2. 正在输入凭据...")
            page.locator("#email").fill(EMAIL)
            time.sleep(1)
            page.locator("#password").fill(PASSWORD)
            time.sleep(1)

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
                time.sleep(4)
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
            time.sleep(4)
            dismiss_ads(page)
            capture_step(page, "步骤 5: 已跳转到目标服务器页面")

            print("6. 正在寻找并点击 Manage 标签页...")
            manage_tab = page.locator(
                'button[role="tab"]:has-text("Manage"), button:has-text("Manage")'
            )

            print("-> 第一次点击 Manage...")
            wait_and_click(page, manage_tab, max_attempts=12)
            time.sleep(4)

            print("-> 第二次点击 Manage...")
            wait_and_click(page, manage_tab, max_attempts=12)
            time.sleep(4)

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
            time.sleep(4)

            capture_step(page, "步骤 8: 已完成 Renew now 按钮点击")

            print("9. 正在执行严格缓冲的真人轨迹点击 Discord 续期确认按钮...")
            click_discord_confirm_robust(page)

            print("10. 等待后端处理续期并刷新数据（保持 8 秒延时）...")
            time.sleep(8)  # 确保后端处理完毕并刷新页面
            dismiss_ads(page)
            capture_step(page, "步骤 10: 续期等待完成，准备读取最新时间")

            print("11. 正在获取 Renew 操作后的时间...")
            time_after = get_remaining_time(page)
            total_hours_after = parse_total_hours(time_after)
            print(
                f"-> 续期后时间: {time_after} (折合 {total_hours_after} 小时)"
            )
            capture_step(page, "步骤 11: 续期结束，最新时间: {time_after}")

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
