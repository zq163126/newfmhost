import os
import re
import time
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
import requests

# 从环境变量中读取配置
EMAIL = os.environ.get("WEB_EMAIL")
PASSWORD = os.environ.get("WEB_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# 固定的目标服务器 ID
SERVER_ID = "2f12a6bd-a1c1-4cc1-bd32-8becf1925680"

# 接口 A (触发续期) & 接口 B (获取服务器完整详情)
RENEW_ACTION_URL = "https://freemchost.com/_serverFn/798181797bd95a02dee916a26c18d3539a58152db8660e097ca48d7cdd8ee50c"
RENEW_DETAIL_URL = "https://freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"


def send_telegram_message(text, photo_path=None):
    """发送文字消息和截图到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置不完整，跳过发送消息。")
        return

    # 发送文本
    text_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    text_data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(text_url, json=text_data, timeout=10)
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
                requests.post(photo_url, data=data, files=files, timeout=15)
            print("Telegram 截图发送成功")
        except Exception as e:
            print(f"发送 Telegram 截图失败: {e}")


def capture_step(page, step_name):
    """辅助函数：仅打控制台日志，不推送中间截图"""
    print(f"📍 [进度日志]: {step_name} | 当前 URL: {page.url}")


def wait_and_click(page, locator, max_attempts=10):
    """等待并强制点击元素"""
    for attempt in range(max_attempts):
        try:
            locator.first.click(force=True, timeout=1500)
            print(f"-> 成功点击目标元素（第 {attempt + 1} 次尝试）")
            return True
        except Exception:
            page.wait_for_timeout(1000)

    raise RuntimeError(
        f"未能成功点击目标元素 ({locator})，当前页面 URL: {page.url}"
    )


def parse_action_response(res_json):
    """解析【接口 A】返回的数据结构，提取最新到期时间、操作状态码或错误提示"""
    action_info = {"expires_at": None, "status_code": "未知", "error_msg": None}
    try:
        outer_p = res_json.get("p", {})
        keys = outer_p.get("k", [])
        values = outer_p.get("v", [])

        if "result" in keys:
            idx = keys.index("result")
            if idx < len(values):
                result_node_p = values[idx].get("p", {})
                sub_keys = result_node_p.get("k", [])
                sub_values = result_node_p.get("v", [])

                if "expires_at" in sub_keys:
                    sub_idx = sub_keys.index("expires_at")
                    if sub_idx < len(sub_values):
                        action_info["expires_at"] = sub_values[sub_idx].get("s")

        if "error" in keys:
            err_idx = keys.index("error")
            if err_idx < len(values):
                err_val = values[err_idx]
                action_info["status_code"] = err_val
                # 递归提取错误文字信息
                if isinstance(err_val, dict):
                    err_str = str(err_val)
                    if "message" in err_str:
                        action_info["error_msg"] = err_str
                    else:
                        action_info["error_msg"] = err_val.get(
                            "s", "未知错误"
                        )
    except Exception as e:
        print(f"解析续期动作响应异常: {e}")
    return action_info


def parse_detail_response(res_json):
    """解析【接口 B】返回的数据结构，动态提取服务器名称、运行状态等元数据"""
    info = {"name": "未知", "status": "未知", "expires_at": None}
    try:
        outer_v = res_json.get("p", {}).get("v", [])
        if not outer_v:
            return info

        mid_v = outer_v[0].get("p", {}).get("v", [])
        if not mid_v:
            return info

        server_node = mid_v[0]
        keys = server_node.get("p", {}).get("k", [])
        values = server_node.get("p", {}).get("v", [])

        if "name" in keys:
            info["name"] = values[keys.index("name")].get("s", "未知")
        if "status" in keys:
            info["status"] = values[keys.index("status")].get("s", "未知")
        if "expires_at" in keys:
            info["expires_at"] = values[keys.index("expires_at")].get(
                "s", None
            )
    except Exception as e:
        print(f"解析最终详情响应异常: {e}")
    return info


def calculate_hours_left(expires_at_str):
    """根据 ISO 格式的到期时间字符串精准计算剩余小时数 (统一致化为 UTC 时区相减)"""
    if not expires_at_str:
        return 0
    try:
        clean_str = expires_at_str.replace("Z", "+00:00")
        expire_time = datetime.fromisoformat(clean_str)

        # 统一转化为带 UTC 时区的 datetime 统一运算
        if expire_time.tzinfo is None:
            expire_time = expire_time.replace(tzinfo=timezone.utc)

        now_time = datetime.now(timezone.utc)
        time_diff = expire_time - now_time
        return max(0, int(time_diff.total_seconds() / 3600))
    except Exception as e:
        print(f"计算剩余时间引发异常: {e}")
        return 0


def extract_auth_token_from_storage(page):
    """从 LocalStorage 自动读取 Supabase 颁发的 Access Token"""
    token = page.evaluate(
        """
        () => {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key.includes('supabase.auth.token') || key.includes('sb-')) {
                    try {
                        const data = JSON.parse(localStorage.getItem(key));
                        if (data && data.access_token) return data.access_token;
                        if (data && data.currentSession) return data.currentSession.access_token;
                    } catch(e) {}
                }
            }
            return null;
        }
    """
    )
    return token


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

            # 先访问一次具体的服务器详情页面，建立正常的用户会话环境，防止被后端判定为恶意直连 API
            server_page_url = f"https://freemchost.com/app/servers/{SERVER_ID}"
            print(
                f"4.5. 导航至服务器管理页面以满足冷却规则: {server_page_url}"
            )
            page.goto(server_page_url, wait_until="networkidle")
            page.wait_for_timeout(3000)

            print("5. 正在从浏览器状态中提取专属 Access Token...")
            access_token = extract_auth_token_from_storage(page)
            if not access_token:
                raise RuntimeError("未能提取到有效的 Auth Access Token")
            print("✅ 成功提取 Token！")

            # 构建 POST 请求公共头
            base_headers = {
                "accept": "application/x-tss-framed, application/x-ndjson, application/json",
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
                "origin": "https://freemchost.com",
                "referer": server_page_url,
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "x-tsr-serverfn": "true",
            }

            renew_payload = {
                "t": {
                    "t": 10,
                    "i": 0,
                    "p": {
                        "k": ["data"],
                        "v": [
                            {
                                "t": 10,
                                "i": 1,
                                "p": {
                                    "k": ["id"],
                                    "v": [{"t": 1, "s": SERVER_ID}],
                                },
                                "o": 0,
                            }
                        ],
                    },
                    "o": 0,
                },
                "f": 63,
                "m": [],
            }

            print("6. 正在通过 POST 接口拉取服务器初始详情...")
            detail_res = page.request.post(
                RENEW_DETAIL_URL, headers=base_headers, data=renew_payload
            )

            if detail_res.status != 200:
                raise RuntimeError(
                    f"读取服务器详情接口失败，HTTP 状态码: {detail_res.status}"
                )

            initial_info = parse_detail_response(detail_res.json())
            server_name = initial_info["name"]
            server_status = initial_info["status"]
            expires_at_before = initial_info["expires_at"]

            hours_left = calculate_hours_left(expires_at_before)
            print(
                f"-> 服务器: {server_name} | 状态: {server_status} | 原始到期时间: {expires_at_before}"
            )
            print(f"-> 折算剩余约 {hours_left} 小时")
            capture_step(
                page,
                f"步骤 6: 接口获取信息成功 (剩余 {hours_left} 小时)",
            )

            # 判断是否符合续期标准
            if hours_left > 36:
                page.screenshot(path=screenshot_path, full_page=True)
                msg = (
                    f"ℹ️ **Freemchost 自动续期跳过**\n\n"
                    f"👤 **账号**: `{EMAIL}`\n"
                    f"🖥️ **服务器**: `{server_name}`\n"
                    f"⏳ **到期时间**: `{expires_at_before}` (剩余约 {hours_left} 小时)\n"
                    f"💡 **提示**: 剩余时间大于 36 小时，无需续期，已自动退出任务。"
                )
                print(f"-> {msg}")
                send_telegram_message(msg, screenshot_path)
                return

            print("7. 剩余时间 <= 36 小时，准备触发续期指令...")
            # 增加延迟避开冷却控制
            time.sleep(5)

            max_retries = 3
            action_info = None

            for attempt in range(1, max_retries + 1):
                print(f"-> 正在发送续期请求 (第 {attempt} 次尝试)...")
                action_res = page.request.post(
                    RENEW_ACTION_URL, headers=base_headers, data=renew_payload
                )

                if action_res.status != 200:
                    raise RuntimeError(
                        f"触发续期接口请求失败，HTTP 状态码: {action_res.status}"
                    )

                res_data = action_res.json()
                action_info = parse_action_response(res_data)

                # 检查是否存在冷却提示
                err_str = str(action_info.get("status_code", "")) + str(
                    action_info.get("error_msg", "")
                )
                if "Please take a moment" in err_str:
                    print(
                        f"⚠️ 触发冷却限制提示: {err_str}，等待 6 秒后重试..."
                    )
                    time.sleep(6)
                else:
                    break

            print(f"-> 动作响应状态: {action_info['status_code']}")

            print(
                "8. 正在拉取最新的服务器完整数据（确认续期结果）..."
            )
            page.wait_for_timeout(3000)

            detail_res_after = page.request.post(
                RENEW_DETAIL_URL, headers=base_headers, data=renew_payload
            )
            final_info = parse_detail_response(detail_res_after.json())

            expires_at_after = (
                action_info.get("expires_at")
                or final_info.get("expires_at")
                or "未知"
            )
            hours_left_after = calculate_hours_left(expires_at_after)

            capture_step(
                page,
                f"步骤 8: 续期更新完成，新到期时间: {expires_at_after}",
            )

            page.screenshot(path=screenshot_path, full_page=True)

            report_msg = (
                f"🎉 **Freemchost 自动续期任务成功**\n\n"
                f"👤 **账号**: `{EMAIL}`\n"
                f"🖥️ **服务器**: `{server_name}`\n"
                f"🟢 **运行状态**: `{final_info['status']}`\n"
                f"⏳ **原到期时间**: `{expires_at_before}`\n"
                f"⏳ **新到期时间**: `{expires_at_after}` (剩余约 {hours_left_after} 小时)\n"
                f"⏰ **执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            print(f"-> {report_msg}")
            send_telegram_message(report_msg, screenshot_path)

        except Exception as e:
            print(f"❌ 运行过程中发生错误: {e}")
            try:
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
