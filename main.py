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
    """优化版去广告函数：向左向下调整后的安全空白点 + JS 向上查找 button 强行触发"""
    # 1. 在右上角无功能按钮的纯空白安全区域 (width - 250, 200) 点击以触发弹窗遮罩层关闭
    try:
        viewport = page.viewport_size or {"width": 1280, "height": 800}
        safe_x = viewport["width"] - 250
        safe_y = 200
        mark_click_point(page, safe_x, safe_y)
        page.mouse.click(safe_x, safe_y)
        page.wait_for_timeout(300)
    except Exception:
        pass

    # 2. 注入 JS：精准搜寻带有 lucide-x 的 svg，并找到其最近的 button 父级节点触发点击
    js_close_script = """
    () => {
        // 查找包含 Close 或 class 为 lucide-x 的 SVG/元素
        const closeIcons = Array.from(document.querySelectorAll('svg.lucide-x, #dismiss-button'));
        for (const icon of closeIcons) {
            const btn = icon.closest('button') || icon;
            if (btn && typeof btn.click === 'function') {
                btn.click();
            }
        }
        // 额外查找包含 sr-only 且文本为 Close 的 span 节点的父级按钮
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

    # 3. Playwright 备用常规定位点击
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
                    if el.is_visible(timeout=300):
                        print(f"-> 检测到弹窗/广告 ({selector})，正在尝试关闭...")
                        try:
                            box = el.bounding_box()
                            if box:
                                mark_click_point(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            el.click(force=True, timeout=1000)
                        except Exception:
                            el.dispatch_event("click")
                        page.wait_for_timeout(300)
            except Exception:
                pass


def human_mouse_click(page, locator):
    """定位元素并在对应位置打红点后，使用模拟真实鼠标轨迹移动点击"""
    locator.wait_for(state="attached", timeout=10000)

    # 确保元素进入视图
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    box = locator.bounding_box()
    if not box:
        # 如果获取不到坐标，降级使用常规 click 触发
        locator.click(force=True)
        return

    # 计算目标中心点并加微小的随机偏移，模仿真人点击
    target_x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
    target_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)

    # 随机产生一个起始点坐标
    start_x = random.randint(100, 500)
    start_y = random.randint(100, 500)

    # 步进式模拟鼠标移动轨迹
    steps = random.randint(10, 25)
    for i in range(1, steps + 1):
        curr_x = start_x + (target_x - start_x) * (i / steps)
        curr_y = start_y + (target_y - start_y) * (i / steps)
        page.mouse.move(curr_x, curr_y)
        time.sleep(random.uniform(0.005, 0.015))

    page.wait_for_timeout(random.randint(100, 200))
    
    # 点击前在真实点击位置打红点（供截图查看）
    mark_click_point(page, target_x, target_y)
    page.mouse.click(target_x, target_y)


def get_remaining_time(page):
    """获取当前的剩余续期时间"""
    # 使用 role="timer" 定位 (使用 .first 确保精准匹配第一个计时器节点)
    timer_element = page.locator('div[role="timer"]').first
    timer_element.wait_for(state="visible", timeout=15000)

    # 提取 aria-label 属性值
    aria_label = timer_element.get_attribute("aria-label")
    if aria_label:
        return aria_label

    # 如果属性获取不到，尝试提取子元素的文本拼接
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
        # 设置窗口大小以防截图显示不全
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
            dismiss_ads(page)
            signin_btn = page.locator('button[type="submit"]:has-text("Sign in")')
            box = signin_btn.bounding_box()
            if box:
                mark_click_point(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            signin_btn.click()

            # --- 判断是否成功登录并跳转至系统后台 URL ---
            print("4. 正在验证登录状态（等待页面跳转至后台）...")
            try:
                # 等待 URL 匹配到包含 /app 的控制台页面，超时设为 15 秒
                page.wait_for_url("**/app**", timeout=15000, wait_until="networkidle")
                print("-> 成功检测到后台特征 URL，登录验证通过！")
            except Exception as url_err:
                # 如果超时未跳转，说明大概率停留在登录页，直接抛出定制错误
                raise RuntimeError(
                    f"登录状态验证失败。页面未按预期跳转到后台系统 (当前 URL: {page.url})。可能存在验证码拦截或凭据错误。"
                )

            print("5. 正在跳转至指定的目标服务器面板页面...")
            # 登录确认成功后，直接跳转至指定的具体服务器 URL
            page.goto(
                "https://new.freemchost.com/app/servers/7aa14245-4754-47ba-9bf9-d76da413761d",
                wait_until="networkidle",
            )
            dismiss_ads(page)

            print("6. 正在寻找并点击 Manage 标签页...")
            # 使用 role="tab" 并匹配文本 "Manage"，不依赖任何动态 ID
            manage_tab = page.locator('button[role="tab"]:has-text("Manage")')
            manage_tab.wait_for(state="visible", timeout=15000)
            box = manage_tab.bounding_box()
            if box:
                mark_click_point(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            manage_tab.click()

            # 等待计时器组件刷新渲染
            page.wait_for_timeout(2000)
            dismiss_ads(page)

            print("7. 正在获取 Renew 操作前的时间...")
            time_before = get_remaining_time(page)
            print(f"-> 续期前时间: {time_before}")

            print("8. 正在点击 Renew now 按钮...")
            dismiss_ads(page)
            # 定位包含 "Renew now" 文本的按钮 (使用 .first 规避多按钮时的 strict mode 报错)
            renew_btn = page.locator('button:has-text("Renew now")').first
            box = renew_btn.bounding_box()
            if box:
                mark_click_point(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            renew_btn.click()

            # --- 应对网站最新改版：等待弹窗并使用模拟轨迹点击 72 hours 续期选项按钮 ---
            print("9. 正在定位并点击 72 hours 续期选项按钮...")
            dismiss_ads(page)

            # 使用高鲁棒性的组合定位策略：匹配包含 72 hours 文本的按钮容器
            option_btn_72h = page.locator('button:has-text("72 hours")').first

            # 采用平滑移动与物理模拟点击
            human_mouse_click(page, option_btn_72h)

            # 等待续期操作响应以及数据刷新
            print("10. 等待数据更新...")
            page.wait_for_timeout(5000)
            dismiss_ads(page)

            print("11. 正在获取 Renew 操作后的时间...")
            time_after = get_remaining_time(page)
            print(f"-> 续期后时间: {time_after}")

            # 成功操作后截图保存
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
            # 发生错误时尝试抓取当前屏幕（如登录失败处的画面），以便推送到 Telegram 供你排查
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
