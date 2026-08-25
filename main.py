import os
import sys
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ==================== 🔧 配置区 ====================
EMAIL = os.environ.get("WEB_EMAIL")
PASSWORD = os.environ.get("WEB_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# 服务器 ID
SERVER_ID = "2f12a6bd-a1c1-4cc1-bd32-8becf1925680"

# 接口路由
RENEW_ACTION_URL = "https://freemchost.com/_serverFn/798181797bd95a02dee916a26c18d3539a58152db8660e097ca48d7cdd8ee50c"
RENEW_DETAIL_URL = "https://freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"


def send_telegram_message(text, photo_path=None):
    """发送 Telegram 消息和截图"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置不完整，跳过发送消息。")
        return

    text_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    text_data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(text_url, json=text_data, timeout=10)
        print("Telegram 文本消息发送成功")
    except Exception as e:
        print(f"发送 Telegram 文本失败: {e}")

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


def parse_action_response(res_json):
    """【复用提供代码的续期解析逻辑】解析接口 A 返回包"""
    action_info = {"expires_at": None, "status_code": "未知"}
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
                action_info["status_code"] = values[err_idx].get("s", "未知")
    except Exception as e:
        print(f"解析续期动作响应异常: {e}")
    return action_info


def parse_detail_response(res_json):
    """【复用提供代码的详情解析逻辑】解析接口 B 返回包"""
    info = {"name": "未知", "status": "未知"}
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
    except Exception as e:
        print(f"解析最终详情响应异常: {e}")
    return info


def extract_auth_token_from_storage(page):
    """【保留原有登录提取逻辑】从 LocalStorage 中读取 Token"""
    token = page.evaluate("""
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
    """)
    return token


def run():
    if not EMAIL or not PASSWORD:
        print("错误: 环境变量中未检测到 WEB_EMAIL 或 WEB_PASSWORD。")
        return

    screenshot_path = "result.png"

    with sync_playwright() as p:
        # 使用我们的 Playwright 模拟浏览器登录环境
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            print("1. 🔑 正在登录获取 Access Token...")
            page.goto("https://freemchost.com/login", wait_until="networkidle")

            page.locator('#email').fill(EMAIL)
            page.locator('#password').fill(PASSWORD)
            page.locator('button[type="submit"]:has-text("Sign in")').click(force=True)

            page.wait_for_url("**/app**", timeout=15000, wait_until="networkidle")
            
            access_token = extract_auth_token_from_storage(page)
            if not access_token:
                raise RuntimeError("未能提取到有效的 Auth Access Token")
            print("✅ 成功提取 Token！")

            base_headers = {
                "accept": "application/x-tss-framed, application/x-ndjson, application/json",
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
                "origin": "https://freemchost.com",
                "referer": f"https://freemchost.com/app/servers/{SERVER_ID}",
                "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "x-tsr-serverfn": "true"
            }

            # 【使用被替换的绝对准确续期 Payload】
            renew_payload = {
                "t": {
                    "t": 10,
                    "i": 0,
                    "p": {
                        "k": ["data"],
                        "v": [{
                            "t": 10,
                            "i": 1,
                            "p": {
                                "k": ["id"],
                                "v": [{"t": 1, "s": SERVER_ID}]
                            },
                            "o": 0
                        }]
                    }
                },
                "f": 63,
                "m": []
            }

            # 2. 发送【接口 A】请求：触发续期动作
            print("2. ⚡ 步骤 1/2: 正在向后端发送续期指令 (接口 A)...")
            action_res = page.request.post(RENEW_ACTION_URL, headers=base_headers, data=renew_payload)

            if action_res.status != 200:
                raise RuntimeError(f"续期 Action 接口请求失败，HTTP 状态码: {action_res.status}")

            action_info = parse_action_response(action_res.json())
            expires_at = action_info.get("expires_at")
            status_code = action_info.get("status_code")

            print("   📥 [接口A 返回快照] ----------------------------")
            print(f"   动作执行状态码 (Error Code) : {status_code}")
            print(f"   捕获动作到期时间 (Expires At): {expires_at}")
            print("   ------------------------------------------------")

            if not expires_at:
                raise RuntimeError("⚠️ 接口 A 响应成功，但未能提取出新到期日期。")

            # 3. 发送【接口 B】请求：拉取最终服务器完整状态
            print("3. 🔍 步骤 2/2: 正在拉取最终服务器完整状态确认 (接口 B)...")
            detail_res = page.request.post(RENEW_DETAIL_URL, headers=base_headers, data=renew_payload)
            
            server_name = "未知"
            server_status = "未知"
            if detail_res.status == 200:
                server_info = parse_detail_response(detail_res.json())
                server_name = server_info.get("name", "未知")
                server_status = server_info.get("status", "未知")

            page.screenshot(path=screenshot_path, full_page=True)

            report_msg = (
                f"🎉 **Freemchost 自动续期成功**\n\n"
                f"👤 **账号**: `{EMAIL}`\n"
                f"🖥️ **服务器**: `{server_name}`\n"
                f"🟢 **运行状态**: `{server_status}`\n"
                f"⏳ **最新到期时间**: `{expires_at}`\n"
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
                send_telegram_message(f"❌ **Freemchost 自动续期任务失败**\n\n**错误原因**: `{str(e)}` (未能截取画面)")
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    run()
