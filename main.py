import os
import re
import time
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


def get_remaining_time(page):
    """鲁棒性更强的剩余时间获取函数"""
    # 优先等待带 role="timer" 的元素在 DOM 中附加并可见
    timer_element = page.locator('div[role="timer"]').first
    timer_element.wait_for(state="visible", timeout=15000)

    # 尝试从 aria-label 属性直接提取时间字符串 (如 "0d 6h 36m 8s remaining")
    aria_label = timer_element.get_attribute("aria-label")
    if aria_label:
        return aria_label

    # 如果无法提取 aria-label，备选方案：拼接子元素中的文本 (如 "00 d 06 h 36 m 08 s")
    text_content = timer_element.inner_text()
    clean_text = re.sub(r"\s+", " ", text_content).strip()
    return clean_text if clean_text else "未知时间"


def run():
    if not EMAIL or not PASSWORD:
        print("错误: 环境变量中未检测到 EMAIL 或 PASSWORD。")
        return

    screenshot_path = "result.png"

    with sync_playwright() as p:
        # 使用无头模式启动浏览器
        browser = p.chromium.launch(headless=True)
        # 设置窗口大小
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            print("1. 正在访问登录页面...")
            page.goto("https://new.freemchost.com/login", wait_until="networkidle")

            print("2. 正在输入凭据...")
            page.locator("#email").fill(EMAIL)
            page.locator("#password").fill(PASSWORD)

            print("3. 点击 Sign in...")
            page.locator('button[type="submit"]:has-text("Sign in")').click()

            # 验证登录状态
            print("4. 正在验证登录状态（等待页面跳转至后台）...")
            try:
                page.wait_for_url("**/app**", timeout=15000, wait_until="networkidle")
                print("-> 成功检测到后台特征 URL，登录验证通过！")
            except Exception as url_err:
                raise RuntimeError(
                    f"登录状态验证失败。页面未按预期跳转到后台系统 (当前 URL: {page.url})。"
                )

            print("5. 正在跳转至指定的目标服务器面板页面...")
            page.goto(
                "https://new.freemchost.com/app/servers/7aa14245-4754-47ba-9bf9-d76da413761d",
                wait_until="networkidle",
            )

            print("6. 正在寻找并点击 Manage 标签页...")
            manage_tab = page.locator('button[role="tab"]:has-text("Manage")')
            manage_tab.wait_for(state="visible", timeout=15000)
            manage_tab.click()

            # 等待 Manage 内容区域刷新完毕
            page.wait_for_timeout(2000)

            print("7. 正在获取 Renew 操作前的时间...")
            time_before = get_remaining_time(page)
            print(f"-> 续期前时间: {time_before}")

            print("8. 正在点击 Renew now 主按钮...")
            renew_btn = page.locator('button:has-text("Renew now")')
            renew_btn.click()

            print("9. 等待弹窗出现，准备点击 48 hours 续期选项...")
            # 优先精准定位包含 "48 hours" 的按钮
            option_btn = page.locator('button:has-text("48 hours")')

            # 容错后备：如果匹配不到 "48 hours"，尝试通过描述语 "Quick top-up" 来匹配
            if option_btn.count() == 0:
                option_btn = page.locator('button:has-text("Quick top-up")')

            option_btn.wait_for(state="visible", timeout=10000)
            option_btn.click()

            # 等待续期请求完成及页面重新渲染
            print("10. 等待数据更新与弹窗关闭...")
            page.wait_for_timeout(5000)

            print("11. 正在获取 Renew 操作后的时间...")
            time_after = get_remaining_time(page)
            print(f"-> 续期后时间: {time_after}")

            # 截取全屏结果
            page.screenshot(path=screenshot_path, full_page=True)

            # 组装通知信息
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
                page.screenshot(path=screenshot_path, full_page=True)
                error_msg = f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}`"
                send_telegram_message(error_msg, screenshot_path)
            except:
                send_telegram_message(
                    f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}` (未能截取到画面)"
                )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    run()
