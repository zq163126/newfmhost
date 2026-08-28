import json
import time

def click_discord_confirm_robust(page):
    """终极诊断与多维强制触发版"""
    print("-> 正在执行 Discord 按钮终极强制触发...")

    try:
        # 1. 确保弹窗可见
        dialog = page.locator('div[role="dialog"]').first
        dialog.wait_for(state="visible", timeout=10000)
        page.wait_for_timeout(800)

        # 2. 通过 JS 进行红黄高亮，并直接在 DOM 元素上深度触发全套点击事件
        debug_info = page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('div[role="dialog"] button[type="button"]'));
                const allTexts = buttons.map((b, i) => `[${i}] -> ${b.textContent.trim().replace(/\\s+/g, ' ')}`);

                const targetBtn = buttons.find(b => {
                    const text = b.textContent || '';
                    return text.includes('Discord Boosted renewal');
                });

                if (!targetBtn) return { found: false, allTexts: allTexts };

                // 加上红黄高亮框
                targetBtn.style.border = '4px solid #ff0000';
                targetBtn.style.backgroundColor = '#ffff00';
                targetBtn.style.boxShadow = '0 0 20px #ff0000';
                targetBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });

                // 核心大招：直接在 JS 层面分发标准鼠标事件序列（能绕过绝大多数前端框架限制）
                try {
                    targetBtn.focus();
                    
                    // 依次触发 mousedown, mouseup, click
                    ['mousedown', 'mouseup', 'click'].forEach(eventType => {
                        const evt = new MouseEvent(eventType, {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            buttons: 1
                        });
                        targetBtn.dispatchEvent(evt);
                    });
                    
                    // 如果框架用的是 React 内部合成事件，尝试直接调用其 click 方法
                    targetBtn.click();
                    
                    return { found: true, allTexts: allTexts, dispatched: true };
                } catch (err) {
                    return { found: true, allTexts: allTexts, dispatched: false, error: err.toString() };
                }
            }
        """)

        print(f"-> 🔍 元素核验与 JS 派发结果: {debug_info}")

        # 3. 截取带有高亮标记的画面发到 TG
        debug_screenshot_path = "click_debug.png"
        page.screenshot(path=debug_screenshot_path, full_page=True)
        
        send_telegram_message(
            f"📍 **按钮定位与强制点击诊断**:\n"
            f"🎯 状态: `已尝试 JS 深度强制触发`\n"
            f"📋 按钮列表:\n```\n{json.dumps(debug_info.get('allTexts', []), indent=2, ensure_ascii=False)}```",
            debug_screenshot_path,
        )

        if not debug_info['found']:
            raise RuntimeError("未能在弹窗中找到 Discord Boosted renewal 按钮")
            
        print("-> 🚀 JS 强制触发指令已执行完毕，等待页面响应...")

    except Exception as e:
        raise RuntimeError(f"点击 Discord 按钮失败: {e}")
