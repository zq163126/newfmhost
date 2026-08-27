def click_discord_confirm_robust(page):
    """终极强效点击版：结合坐标红点与 DOM 元素深度事件派发"""
    print("-> 正在执行 Discord 确认按钮的强效点击...")

    target_x = 640
    target_y = 590

    try:
        # 1. 先画个红点方便你在截图里看位置
        page.evaluate(f"""
            () => {{
                const existing = document.getElementById('debug-click-dot');
                if (existing) existing.remove();

                const dot = document.createElement('div');
                dot.id = 'debug-click-dot';
                dot.style.position = 'fixed';
                dot.style.left = '{target_x}px';
                dot.style.top = '{target_y}px';
                dot.style.width = '24px';
                dot.style.height = '24px';
                dot.style.backgroundColor = '#ff0000';
                dot.style.border = '3px solid #ffffff';
                dot.style.borderRadius = '50%';
                dot.style.transform = 'translate(-50%, -50%)';
                dot.style.zIndex = '9999999';
                dot.style.pointerEvents = 'none';
                dot.style.boxShadow = '0 0 10px rgba(0,0,0,0.8)';
                document.body.appendChild(dot);
            }}
        """)
        page.wait_for_timeout(300)

        # 2. 截图保存当前状态
        debug_screenshot_path = "click_debug.png"
        page.screenshot(path=debug_screenshot_path, full_page=True)

        # 3. 双保险核心：先用 JS 在该坐标直接精准打击底层元素，再配合物理鼠标点击
        page.evaluate(f"""
            () => {{
                // 获取当前坐标最上层的元素
                const elem = document.elementFromPoint({target_x}, {target_y});
                if (elem) {{
                    console.log("找到坐标对应的元素:", elem);
                    // 强制派发全套鼠标事件
                    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(eventType => {{
                        elem.dispatchEvent(new MouseEvent(eventType, {{
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            clientX: {target_x},
                            clientY: {target_y}
                        }}));
                    }});
                    // 如果元素本身有 click 方法，也直接调用
                    if (typeof elem.click === 'function') {{
                        elem.click();
                    }}
                }}
            }}
        """)

        # 4. 物理点击补刀
        page.mouse.move(target_x, target_y)
        page.mouse.down()
        page.wait_for_timeout(100)
        page.mouse.up()
        print("-> JS 深度事件派发与物理点击补刀已全部完成")

        send_telegram_message(
            f"📍 **强效点击调试**: 坐标 `({target_x}, {target_y})`\n已执行组合拳点击，请观察下一次截图弹窗是否消失！",
            debug_screenshot_path,
        )

    except Exception as e:
        raise RuntimeError(f"点击 Discord 续期确认按钮失败: {e}")
