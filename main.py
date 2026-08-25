import os
import re
import time
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# 从环境变量中读取配置
EMAIL = os.environ.get("WEB_EMAIL")
PASSWORD = os.environ.get("WEB_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# 固定的目标服务器 ID
SERVER_ID = "2f12a6bd-a1c1-4cc1-bd32-8becf1925680"

# 2026 最新双接口链路
# 【接口 A】触发续期的 Action 路由
RENEW_ACTION_URL = "https://freemchost.com/_serverFn/798181797bd95a02dee916a26c18d3539a58152db8660e097ca48d7cdd8ee50c"
# 【接口 B】获取最终完整状态的 Detail 路由
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


def parse_action_response(res_json):
    """解析【接口 A】返回的数据，提取最新到期时间与操作状态码"""
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
                err_node_p = values[err_idx].get("p", {})
                err_keys = err_node_p.get("k", [])
                err_values = err_node_p.get("v", [])

                if "message" in err_keys:
                    msg_idx = err_keys.index("message")
                    if msg_idx < len(err_values):
                        action_info["error_msg"] = err_values[msg_idx].get("s")
                action_info["status_code"] = values[err_idx].get("s", "未知")
    except Exception as e:
        print(f"解析续期动作响应异常: {e}")
    return action_info


def parse_detail_response(res_json):
    """解析【接口 B】返回的数据，提取服务器名称与状态"""
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


def calculate_hours_left(expires_at_str):
    """计算剩余可运行小时数"""
    if not expires_at_str:
        return 0
    try:
        clean_str = expires_at_str.replace("Z", "+00:00")
        expire_time = datetime.fromisoformat(clean_str)
        if expire_time.tzinfo is None:
            expire_time = expire_time.replace(tzinfo=timezone.utc)
        now_time = datetime.now(timezone.utc)
        time_diff = expire_time - now_time
        return max(0, int(time_diff.total_seconds() / 3600))
    except Exception as e:
        print(f"计算剩余时间异常: {e}")
        return 0


def extract_auth_token_from_storage(page):
    """从 LocalStorage 提取 Access Token"""
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
            print("1. 正在登录获取 Access Token...")
            page.goto("https://freemchost.com/login", wait_until="networkidle")

            page.locator("#email").fill(EMAIL)
            page.locator("#password").fill(PASSWORD)
            page.locator('button[type="submit"]:has-text("Sign in")').click(force=True)

            try:
                page.wait_for_url("**/app**", timeout=15000, wait_until="networkidle")
                print(f"-> 登录成功，当前 URL: {page.url}")
            except Exception:
                raise RuntimeError(f"登录失败，未跳转至后台系统 (当前 URL: {page.url})")

            access_token = extract_auth_token_from_storage(page)
            if not access_token:
                raise RuntimeError("未能提取到有效的 Auth Access Token")
            print("✅ 成功抓取到 Access Token！")

            base_headers = {
                "accept": "application/x-tss-framed, application/x-ndjson, application/json",
                "authorization": f"Bearer {access_token}",
                "content-type": "application/json",
                "origin": "https://freemchost.com",
                "referer": f"https://freemchost.com/app/servers/{SERVER_ID}",
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
                },
                "f": 63,
                "m": [],
            }

            print("2. ⚡ [步骤 1/2] 正在向后端发送续期指令 (接口 A)...")
            action_res = page.request.post(
                RENEW_ACTION_URL, headers=base_headers, data=renew_payload
            )

            if action_res.status != 200:
                raise RuntimeError(
                    f"续期 Action 接口请求失败，HTTP 状态码: {action_res.status}"
                )

            action_info = parse_action_response(action_res.json())
            expires_at = action_info.get("expires_at")
            error_msg = action_info.get("error_msg")

            print("   📥 [接口 A 返回快照] ----------------------------")
            print(f"   执行状态码: {action_info['status_code']}")
            print(f"   捕获到期时间: {expires_at}")
            if error_msg:
                print(f"   错误信息反馈: {error_msg}")
            print("   ------------------------------------------------")

            if not expires_at:
                if error_msg:
                    raise RuntimeError(f"接口 A 响应成功但未完成续期: {error_msg}")
                else:
                    raise RuntimeError(
                        "接口 A 响应成功，但未能提取出新到期日期，可能尚未到可续期时间。"
                    )

            print("3. 🔍 [步骤 2/2] 续期指令已生效，正在拉取最终服务器状态 (接口 B)...")
            time.sleep(2)
            detail_res = page.request.post(
                RENEW_DETAIL_URL, headers=base_headers, data=renew_payload
            )

            server_name = "未知"
            server_status = "未知"
            if detail_res.status == 200:
                detail_info = parse_detail_response(detail_res.json())
                server_name = detail_info["name"]
                server_status = detail_info["status"]

            hours_left = calculate_hours_left(expires_at)
            page.screenshot(path=screenshot_path, full_page=True)

            report_msg = (
                f"🎉 **Freemchost 自动续期任务成功**\n\n"
                f"👤 **账号**: `{EMAIL}`\n"
                f"🖥️ **服务器**: `{server_name}`\n"
                f"🟢 **运行状态**: `{server_status}`\n"
                f"⏳ **最新到期时间**: `{expires_at}` (剩余约 {hours_left} 小时)\n"
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
