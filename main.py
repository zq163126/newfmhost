import os
import sys
from datetime import datetime
import json
import requests

# ==================== 🔧 核心配置区 ====================
# 1. 登录配置（完全从 GitHub Secrets 读取，不留任何默认值兜底）
LOGIN_URL = "https://laehfeigoiycigkfknfn.supabase.co/auth/v1/token?grant_type=password"
EMAIL = os.getenv("MY_EMAIL")
PASSWORD = os.getenv("MY_PASSWORD")

# 2. 网页前端固定死公钥（完全从 GitHub Secrets 读取）
SUPABASE_ANON_KEY = os.getenv("ANON_KEY")

# 3. 路由配置 (2026-06-05 最新双接口链路)
# 【接口 A】触发续期的 Action 路由
RENEW_ACTION_URL = "https://freemchost.com/_serverFn/798181797bd95a02dee916a26c18d3539a58152db8660e097ca48d7cdd8ee50c"
# 【接口 B】获取最终完整状态的 Detail 路由
RENEW_DETAIL_URL = "https://freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"

SERVER_ID = "c1487010-5680-43b7-932b-f6b6de2d893c"

# 4. 消息推送配置（从 GitHub Secrets 读取）
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# 🚨 安全校验：如果必备的环境变量为空，直接中断运行并报错提示，使 GitHub Actions 显式失败
if not all([EMAIL, PASSWORD, SUPABASE_ANON_KEY]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 🛑 错误: 未能在环境中检测到必要的凭证 (MY_EMAIL, MY_PASSWORD 或 ANON_KEY)。")
    print(f"[{now}] 请检查你的 GitHub Repository -> Settings -> Secrets and variables -> Actions 是否配置正确！")
    sys.exit(1)
# =====================================================

def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")

def notify(title, content, photo_path=None):
    """发送 Telegram 通知 (支持发送文本和可选文件/截图)"""
    if TG_BOT_TOKEN and TG_CHAT_ID:
        try:
            message_text = f"<b>{title}</b>\n\n{content}"
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
                with open(photo_path, 'rb') as photo:
                    requests.post(
                        url, 
                        data={"chat_id": TG_CHAT_ID, "caption": message_text, "parse_mode": "HTML"}, 
                        files={"photo": photo}, 
                        timeout=15
                    )
            else:
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                requests.post(
                    url, 
                    data={"chat_id": TG_CHAT_ID, "text": message_text, "parse_mode": "HTML"}, 
                    timeout=15
                )
        except Exception as e:
            log(f"🔔 推送通知失败: {e}")

def parse_action_response(res_json):
    """解析【接口 A】返回的轻量级压缩包，同时提取最新到期时间、操作状态码"""
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
        log(f"解析续期动作响应异常: {e}")
    return action_info

def parse_detail_response(res_json):
    """解析【接口 B】返回的完整数据包，动态提取服务器名称、运行状态等元数据"""
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
        log(f"解析最终详情响应异常: {e}")
    return info

def get_new_token():
    """通过 Supabase API 发送 POST 账号密码直接登录，换取 Access Token"""
    log("🔑 正在尝试模拟登录以获取个人 Token...")

    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "origin": "https://freemchost.com",
        "referer": "https://freemchost.com/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }

    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "gotrue_meta_security": {}
    }

    try:
        response = requests.post(LOGIN_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            token = response.json().get("access_token")
            if token:
                log("✅ 成功模拟登录，已捕获最新专属 Token！")
                return token
        log(f"❌ 登录失败，状态码: {response.status_code}")
    except Exception as e:
        log(f"💥 登录请求引发异常: {e}")
    return None

def run_auto_renew():
    log("▶️ 开始全自动登录 + 链式续期确认流程...")

    # 1. 获取专属 Token
    token = get_new_token()
    if not token:
        log("🛑 未能取得有效 Token，流程被迫中断。")
        notify("服务器自动续期失败", "模拟登录未成功获取 Token，请查看 Actions 运行日志。")
        sys.exit(1)

    base_headers = {
        "accept": "application/x-tss-framed, application/x-ndjson, application/json",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://freemchost.com",
        "referer": f"https://freemchost.com/app/servers/{SERVER_ID}",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-tsr-serverfn": "true"
    }

    renew_payload = {
        "t": {"t": 10, "i": 0, "p": {"k": ["data"], "v": [{"t": 10, "i": 1, "p": {"k": ["id"], "v": [{"t": 1, "s": SERVER_ID}]}, "o": 0}]}}, "f": 63, "m": []
    }

    # 2. 发送【接口 A】请求：触发续期动作
    log("⚡ 步骤 1/2: 正在向后端发送续期指令...")
    expires_at = None
    try:
        action_res = requests.post(RENEW_ACTION_URL, headers=base_headers, json=renew_payload, timeout=15)
        if action_res.status_code == 200:
            action_info = parse_action_response(action_res.json())
            expires_at = action_info["expires_at"]
            
            log("   📥 [接口A 返回快照] ----------------------------")
            log(f"   动作执行状态码 (Error Code) : {action_info['status_code']} (注: 1通常代表无异常)")
            log(f"   捕获动作到期时间 (Expires At): {expires_at}")
            log("   ------------------------------------------------")
        else:
            log(f"❌ 续期动作请求失败，状态码: {action_res.status_code}")
            notify("服务器自动续期失败", f"续期 Action 接口返回异常状态码: {action_res.status_code}")
            sys.exit(1)
    except Exception as e:
        log(f"💥 续期动作接口引发异常: {e}")
        notify("服务器自动续期异常", f"Action 阶段异常: {e}")
        sys.exit(1)

    if not expires_at:
        log("⚠️ 接口 A 响应成功，但未能提取出新到期日期，流程中断。")
        notify("服务器自动续期失败", "接口 A 响应成功，但未能提取出新到期日期，流程中断。")
        sys.exit(1)

    # 3. 发送【接口 B】请求：拉取续期后的最终详情状态
    log("🔍 步骤 2/2: 续期指令已生效，正在拉取最终服务器完整状态确认...")
    server_name = "未知"
    server_status = "未知"
    try:
        detail_res = requests.post(RENEW_DETAIL_URL, headers=base_headers, json=renew_payload, timeout=15)
        if detail_res.status_code == 200:
            server_info = parse_detail_response(detail_res.json())
            server_name = server_info["name"]
            server_status = server_info["status"]
        else:
            log(f"⚠️ 详情刷新接口返回状态码 {detail_res.status_code}，将使用原缺省值打印日志。")
    except Exception as e:
        log(f"⚠️ 刷新最终详情时发生非致命异常: {e}")

    # 4. 打印最终完美闭环结果并推送
    log("🎉【全链路全自动续期成功】-----------------------")
    log(f" 服务器名称: {server_name}")
    log(f" 当前状态  : {server_status}")
    log(f" 新到期时间: {expires_at}")
    log("--------------------------------------------------")
    
    notify(
        "服务器自动续期成功", 
        f"服务器 [{server_name}] 续期成功！\n"
        f"当前运行状态：{server_status}\n"
        f"最新到期时间：{expires_at}"
    )

if __name__ == "__main__":
    run_auto_renew()
